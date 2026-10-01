"""Embeddings de los chunks (GPU) e índice HNSW (FAISS) para la búsqueda densa.

  python -m src.knowledge.vector_store --modelo bge-m3                          # todo el corpus
  python -m src.knowledge.vector_store --modelo qwen3-emb-0.6b --seleccion normas_fichas
  python -m src.knowledge.vector_store --modelo bge-m3 --solo-hnsw              # rehace el HNSW con los vectores ya hechos
  python -m src.knowledge.vector_store --modelo qwen3-emb-0.6b --seleccion normas --subindice-de todo  # sin GPU

Salida en corpus/indices/<modelo>_<seleccion>/: vectores por lotes (vec_00000.npy, float16,
normalizados), ids.json, hnsw.faiss e info.json. Es reanudable: un lote ya guardado se
salta. El HNSW guarda los vectores en 8 bits (IndexHNSWSQ): ~1 GB por millón de chunks,
para que el portátil lo pueda cargar.

Determinismo: el índice se construye una vez (en la A40) y se copia; la búsqueda sobre el
mismo archivo, con el mismo efSearch, da lo mismo en cualquier máquina.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np

from .chunk_store import INDICES, SELECCIONES, leer_chunks
from .embedding_variants import EMBEDDERS, Embedder

LOTE = 50_000          # chunks por archivo de vectores (checkpoint)
MAX_CHARS_EMBED = 4000  # un chunk nunca pasa de ~3.600 caracteres; margen
M_HNSW, EF_CONSTRUCCION, EF_BUSQUEDA = 32, 200, 256


def cargar_modelo(e: Embedder, dispositivo: str | None = None):
    import torch
    from sentence_transformers import SentenceTransformer
    disp = dispositivo or ("cuda" if torch.cuda.is_available() else "cpu")
    m = SentenceTransformer(e.hf, device=disp, trust_remote_code=False)
    m.max_seq_length = e.max_tokens
    if disp.startswith("cuda"):
        m = m.half()
    return m


def embeber(modelo, textos: list[str], lote: int) -> np.ndarray:
    v = modelo.encode(textos, batch_size=lote, normalize_embeddings=True, convert_to_numpy=True,
                      show_progress_bar=False)
    return v.astype(np.float16)


def construir(clave: str, seleccion: str, salida: Path, lote_gpu: int, limite: int | None, solo_hnsw: bool,
              dispositivo: str | None = None, parte: int = 0, partes: int = 1):
    """Con partes > 1, este proceso solo calcula los lotes i con i % partes == parte: se lanzan
    `partes` procesos (uno por GPU) sobre la misma carpeta y el HNSW se arma cuando están todos."""
    e = EMBEDDERS[clave]
    salida.mkdir(parents=True, exist_ok=True)
    ids = [c["chunk_id"] for c in leer_chunks(seleccion, limite)]
    (salida / "ids.json").write_text(json.dumps(ids), encoding="utf-8")
    n_lotes = (len(ids) + LOTE - 1) // LOTE
    print(f"== {clave}: {len(ids)} chunks en {n_lotes} lotes -> {salida}", flush=True)

    if not solo_hnsw:
        modelo = None
        t0, hechos = time.time(), 0
        textos_lote, lote_i = [], 0
        for c in leer_chunks(seleccion, limite):
            textos_lote.append(e.prefijo_pasaje + c["texto"][:MAX_CHARS_EMBED])
            if len(textos_lote) == LOTE:
                lote_i = _guardar_lote(salida, lote_i, textos_lote, e, lote_gpu, modelo_ref := [modelo], dispositivo,
                                       hacer=lote_i % partes == parte)
                modelo = modelo_ref[0]
                textos_lote = []
                if (lote_i - 1) % partes != parte:
                    continue
                hechos += LOTE
                vel = hechos / (time.time() - t0)
                mios = len(ids) / partes
                print(f"   lote {lote_i}/{n_lotes} (parte {parte}/{partes})  {hechos}/{mios:.0f}  {vel:.0f} chunks/s  "
                      f"faltan ~{max(mios - hechos, 0) / max(vel, 1) / 60:.0f} min", flush=True)
        if textos_lote:
            _guardar_lote(salida, lote_i, textos_lote, e, lote_gpu, [modelo], dispositivo,
                          hacer=lote_i % partes == parte)

    faltan = [i for i in range(n_lotes) if not (salida / f"vec_{i:05d}.npy").exists()]
    if faltan:
        print(f"== parte {parte}/{partes} lista. Faltan {len(faltan)} lotes de las otras partes; cuando terminen: "
              f"python -m src.knowledge.vector_store --modelo {clave} --seleccion {seleccion} --solo-hnsw", flush=True)
        return
    vectores = np.concatenate([np.load(salida / f"vec_{i:05d}.npy") for i in range(n_lotes)]).astype(np.float32)
    assert len(vectores) == len(ids), f"{len(vectores)} vectores para {len(ids)} ids"
    construir_hnsw(vectores, salida)
    (salida / "info.json").write_text(json.dumps({
        "modelo": clave, "hf": e.hf, "dim": int(vectores.shape[1]), "n": len(ids), "seleccion": seleccion,
        "hnsw": {"M": M_HNSW, "efConstruction": EF_CONSTRUCCION, "efSearch": EF_BUSQUEDA, "cuantizacion": "SQ8"},
    }, indent=1), encoding="utf-8")


def subindice(clave: str, origen: Path, seleccion: str, salida: Path):
    """HNSW de una selección a partir de los vectores ya calculados en `origen` (sin GPU):
    los ids salen en el mismo orden de chunks.jsonl."""
    ids_origen = json.loads((origen / "ids.json").read_text(encoding="utf-8"))
    elegidos = {c["chunk_id"] for c in leer_chunks(seleccion)}
    mascara = np.fromiter((cid in elegidos for cid in ids_origen), dtype=bool, count=len(ids_origen))
    n_lotes = (len(ids_origen) + LOTE - 1) // LOTE
    vectores = np.concatenate([np.load(origen / f"vec_{i:05d}.npy")[mascara[i * LOTE:(i + 1) * LOTE]]
                               for i in range(n_lotes)]).astype(np.float32)
    ids = [cid for cid, m in zip(ids_origen, mascara) if m]
    assert len(vectores) == len(ids) == len(elegidos), f"{len(vectores)} vectores, {len(ids)} ids, {len(elegidos)}"
    print(f"== {clave}: subíndice {seleccion} con {len(ids)} de {len(ids_origen)} chunks -> {salida}", flush=True)
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "ids.json").write_text(json.dumps(ids), encoding="utf-8")
    construir_hnsw(vectores, salida)
    (salida / "info.json").write_text(json.dumps({
        "modelo": clave, "hf": EMBEDDERS[clave].hf, "dim": int(vectores.shape[1]), "n": len(ids),
        "seleccion": seleccion, "vectores_de": origen.name,
        "hnsw": {"M": M_HNSW, "efConstruction": EF_CONSTRUCCION, "efSearch": EF_BUSQUEDA, "cuantizacion": "SQ8"},
    }, indent=1), encoding="utf-8")


def _guardar_lote(salida: Path, i: int, textos: list[str], e: Embedder, lote_gpu: int, modelo_ref: list,
                  dispositivo: str | None = None, hacer: bool = True) -> int:
    destino = salida / f"vec_{i:05d}.npy"
    if hacer and not destino.exists():  # checkpoint: los lotes hechos se saltan; los de otra parte, también
        if modelo_ref[0] is None:
            modelo_ref[0] = cargar_modelo(e, dispositivo)
        tmp = destino.with_suffix(".tmp.npy")
        np.save(tmp, embeber(modelo_ref[0], textos, lote_gpu))
        tmp.replace(destino)
    return i + 1


def construir_hnsw(vectores: np.ndarray, salida: Path):
    import faiss
    t0 = time.time()
    d = vectores.shape[1]
    indice = faiss.IndexHNSWSQ(d, faiss.ScalarQuantizer.QT_8bit, M_HNSW, faiss.METRIC_INNER_PRODUCT)
    indice.hnsw.efConstruction = EF_CONSTRUCCION
    muestra = vectores[np.random.default_rng(0).choice(len(vectores), min(len(vectores), 200_000), replace=False)]
    indice.train(muestra)
    for i in range(0, len(vectores), 100_000):
        indice.add(vectores[i:i + 100_000])
        print(f"   HNSW {min(i + 100_000, len(vectores))}/{len(vectores)}  {time.time() - t0:.0f} s", flush=True)
    tmp = salida / f"hnsw.{os.getpid()}.tmp"  # si dos partes terminan a la vez, no se pisan
    faiss.write_index(indice, str(tmp))
    os.replace(tmp, salida / "hnsw.faiss")
    print(f"== HNSW listo en {time.time() - t0:.0f} s", flush=True)


class IndiceDenso:
    """Búsqueda en el HNSW. La consulta se embebe en float32 (en GPU o CPU da lo mismo
    hasta el redondeo; el orden final se desempata por chunk_id)."""

    def __init__(self, ruta: Path, dispositivo: str | None = None, modelo=None):
        import faiss
        self.info = json.loads((ruta / "info.json").read_text(encoding="utf-8"))
        self.e = EMBEDDERS[self.info["modelo"]]
        self.ids = json.loads((ruta / "ids.json").read_text(encoding="utf-8"))
        self.indice = faiss.read_index(str(ruta / "hnsw.faiss"))
        self.indice.hnsw.efSearch = EF_BUSQUEDA
        faiss.omp_set_num_threads(1)  # búsqueda reproducible
        self.modelo = modelo
        self.dispositivo = dispositivo

    def vector(self, consulta: str) -> np.ndarray:
        if self.modelo is None:
            self.modelo = cargar_modelo(self.e, self.dispositivo).float()
        v = self.modelo.encode([self.e.prefijo_consulta + consulta], normalize_embeddings=True,
                               convert_to_numpy=True, show_progress_bar=False)
        return np.round(v.astype(np.float32), 4)

    def buscar(self, consulta: str, k: int = 100) -> list[tuple[str, float]]:
        return self.buscar_vector(self.vector(consulta), k)

    def buscar_vector(self, v: np.ndarray, k: int = 100) -> list[tuple[str, float]]:
        scores, idx = self.indice.search(v, k)
        pares = [(self.ids[int(i)], float(s)) for i, s in zip(idx[0], scores[0]) if i >= 0]
        return sorted(pares, key=lambda p: (-round(p[1], 4), p[0]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modelo", required=True, choices=list(EMBEDDERS))
    ap.add_argument("--seleccion", default="todo", choices=list(SELECCIONES))
    ap.add_argument("--subindice-de", help="arma el HNSW de --seleccion con los vectores de esta selección "
                                           "ya calculada (p. ej. todo), sin GPU")
    ap.add_argument("--lote-gpu", type=int, default=64, help="batch de encode (A40: 64-128)")
    ap.add_argument("--limite", type=int, help="solo los primeros N chunks (prueba)")
    ap.add_argument("--solo-hnsw", action="store_true", help="rehace el HNSW desde los vectores guardados")
    ap.add_argument("--device", help="cuda, cuda:2, cpu (por defecto cuda si hay)")
    ap.add_argument("--parte", type=int, default=0, help="con --partes N: qué parte de los lotes hace este proceso")
    ap.add_argument("--partes", type=int, default=1, help="repartir los lotes entre N procesos (uno por GPU)")
    ap.add_argument("--salida", type=Path)
    args = ap.parse_args()
    if args.subindice_de:
        subindice(args.modelo, INDICES / f"{args.modelo}_{args.subindice_de}", args.seleccion,
                  args.salida or INDICES / f"{args.modelo}_{args.seleccion}")
        return
    construir(args.modelo, args.seleccion, args.salida or INDICES / f"{args.modelo}_{args.seleccion}",
              args.lote_gpu, args.limite, args.solo_hnsw, args.device, args.parte, args.partes)


if __name__ == "__main__":
    main()
