"""Agrega documentos nuevos a un corpus ya indexado, sin tocar lo que ya está.

  python -m src.knowledge.agregar_chunks --nuevos <carpeta con chunks.jsonl> --device cuda

Los chunks nuevos salen de `python -m src.knowledge.chunking --md <md nuevos> --salida <carpeta>`.

1. Inserta los chunks nuevos en corpus/chunks/chunks.sqlite (un chunk_id que ya existe se salta) y
   actualiza resumen.json.
2. Embebe solo los chunks nuevos (mismo modelo, prefijo, recorte y fp16 que vector_store) y los agrega al
   final de los HNSW de todo y de normas (las normas, solo al de normas si no son sentencias), con sus ids
   al final de ids.json. Los vectores existentes no se recalculan ni se mueven. Un solo hilo de FAISS:
   la inserción es determinista.
3. Escribe corpus/chunks/chunks.jsonl (si no está, o le faltan los nuevos) en el orden de los ids del HNSW
   de todo, desde chunks.sqlite: es la entrada de bm25_store, y así BM25 y HNSW quedan con los mismos ids en
   el mismo orden (lo exige verify_indices).
Después: reconstruir BM25 de todo y de normas (necesita ~30-40 GB de RAM) y verificar.
Se puede relanzar: cada paso solo hace lo que falta.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import numpy as np

from .chunk_store import CHUNKS, INDICES, es_sentencia
from .embedding_variants import EMBEDDERS
from .vector_store import MAX_CHARS_EMBED, cargar_modelo, embeber


def agregar_a_la_base(nuevos: list[dict], chunks: Path) -> list[dict]:
    db = sqlite3.connect(chunks / "chunks.sqlite")
    existentes = {cid for (cid,) in db.execute(
        f"SELECT chunk_id FROM chunks WHERE chunk_id IN ({','.join('?' * len(nuevos))})",
        [c["chunk_id"] for c in nuevos])}
    faltan = [c for c in nuevos if c["chunk_id"] not in existentes]
    db.executemany("INSERT INTO chunks VALUES (?,?,?,?,?,?)",
                   [(c["chunk_id"], c["doc_id"], c.get("articulo_id"), c.get("seccion_id"), c["tipo_chunk"],
                     json.dumps(c, ensure_ascii=False)) for c in faltan])
    db.commit()
    db.close()
    resumen_path = chunks / "resumen.json"
    if faltan and resumen_path.exists():  # conteos de corpus/chunks/resumen.json al día
        r = json.loads(resumen_path.read_text(encoding="utf-8"))
        r["documentos"] = r.get("documentos", 0) + len({c["doc_id"] for c in faltan})
        r["total_chunks"] = r.get("total_chunks", 0) + len(faltan)
        for c in faltan:
            r.setdefault("chunks", {})[c["tipo_chunk"]] = r["chunks"].get(c["tipo_chunk"], 0) + 1
        r["chars"] = r.get("chars", 0) + sum(c.get("n_chars", len(c["texto"])) for c in faltan)
        r["tokens_aprox"] = int(r["chars"] / 4)
        r["agregados"] = r.get("agregados", []) + sorted({c["doc_id"] for c in faltan})
        resumen_path.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"== base: {len(faltan)} chunks nuevos ({len(existentes)} ya estaban)", flush=True)
    return faltan


def agregar_al_hnsw(nuevos: list[dict], carpeta: Path, clave: str, modelo_ref: list, dispositivo: str | None,
                    lote_gpu: int):
    """Agrega al final del HNSW los `nuevos` que aún no están en su ids.json."""
    import faiss
    ids = json.loads((carpeta / "ids.json").read_text(encoding="utf-8"))
    ya = set(ids)
    pendientes = [c for c in nuevos if c["chunk_id"] not in ya]
    if not pendientes:
        print(f"== {carpeta.name}: no falta ninguno ({len(ids)})", flush=True)
        return
    indice = faiss.read_index(str(carpeta / "hnsw.faiss"))
    assert indice.ntotal == len(ids), f"{carpeta.name}: hnsw con {indice.ntotal} vectores y {len(ids)} ids"
    e = EMBEDDERS[clave]
    if modelo_ref[0] is None:
        modelo_ref[0] = cargar_modelo(e, dispositivo)
    v = embeber(modelo_ref[0], [e.prefijo_pasaje + c["texto"][:MAX_CHARS_EMBED] for c in pendientes],
                lote_gpu).astype(np.float32)
    faiss.omp_set_num_threads(1)  # inserción determinista
    indice.add(v)
    ids += [c["chunk_id"] for c in pendientes]
    # Primero el índice y después ids.json: si se corta entre los dos, el assert de arriba lo detecta.
    tmp = carpeta / "hnsw.faiss.tmp"
    faiss.write_index(indice, str(tmp))
    tmp.replace(carpeta / "hnsw.faiss")
    (carpeta / "ids.json").write_text(json.dumps(ids), encoding="utf-8")
    info = json.loads((carpeta / "info.json").read_text(encoding="utf-8"))
    info["n"] = len(ids)
    info["agregados"] = info.get("agregados", 0) + len(pendientes)
    (carpeta / "info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    print(f"== {carpeta.name}: {len(pendientes)} vectores nuevos ({len(ids)} en total)", flush=True)


def escribir_jsonl(chunks: Path, orden: Path):
    """chunks.jsonl en el orden de `orden` (ids.json del HNSW de todo), leído de chunks.sqlite."""
    ids = json.loads(orden.read_text(encoding="utf-8"))
    destino = chunks / "chunks.jsonl"
    if destino.exists():
        with destino.open(encoding="utf-8") as f:
            n = sum(1 for _ in f)
        if n == len(ids):
            print(f"== chunks.jsonl ya está completo ({n})", flush=True)
            return
    db = sqlite3.connect(f"file:{chunks / 'chunks.sqlite'}?mode=ro", uri=True)
    tmp = destino.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for i in range(0, len(ids), 5000):
            lote = ids[i:i + 5000]
            datos = dict(db.execute(f"SELECT chunk_id, datos FROM chunks WHERE chunk_id IN "
                                    f"({','.join('?' * len(lote))})", lote))
            assert len(datos) == len(lote), "hay ids del HNSW que no están en chunks.sqlite"
            f.writelines(datos[c] + "\n" for c in lote)
            if i % 500_000 == 0:
                print(f"   chunks.jsonl {i}/{len(ids)}", flush=True)
    tmp.replace(destino)
    print(f"== chunks.jsonl: {len(ids)} chunks en el orden del HNSW", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nuevos", type=Path, required=True, help="carpeta con el chunks.jsonl de los documentos nuevos")
    ap.add_argument("--modelo", default="qwen3-emb-0.6b", choices=list(EMBEDDERS))
    ap.add_argument("--device", help="cuda, cuda:0, cpu")
    ap.add_argument("--lote-gpu", type=int, default=32)
    args = ap.parse_args()

    nuevos = [json.loads(l) for l in (args.nuevos / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l]
    agregar_a_la_base(nuevos, CHUNKS)
    modelo = [None]
    agregar_al_hnsw(nuevos, INDICES / f"{args.modelo}_todo", args.modelo, modelo, args.device, args.lote_gpu)
    agregar_al_hnsw([c for c in nuevos if not es_sentencia(c)], INDICES / f"{args.modelo}_normas", args.modelo,
                    modelo, args.device, args.lote_gpu)
    escribir_jsonl(CHUNKS, INDICES / f"{args.modelo}_todo" / "ids.json")
    print("\nFalta (en este orden):\n"
          "  python -m src.knowledge.bm25_store --seleccion todo\n"
          "  python -m src.knowledge.bm25_store --seleccion normas\n"
          "  python -m src.knowledge.verify_indices", flush=True)


if __name__ == "__main__":
    main()
