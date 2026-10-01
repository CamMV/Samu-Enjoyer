"""Empaqueta el entregable 5: corpus procesado + índice serializado + LICENSE en un .zip.

  python -m src.knowledge.package_index                 # -> ../samu_enjoyer_corpus_indice.zip
  python -m src.knowledge.package_index --simular       # solo lista lo que entraría

Todo va bajo corpus/: al descomprimir en la raíz del repo, los índices quedan donde el
código los busca. Incluye LEEME.md (contenido, configuración y uso) y SHA256SUMS.txt.
Los vectores por lotes (vec_*.npy) y chunks.jsonl no van: el HNSW y chunks.sqlite bastan
para buscar.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import time
import zipfile
from dataclasses import asdict
from pathlib import Path

from .chunk_store import CHUNKS, INDICES, ROOT
from .hybrid_search import Config

DENSO = "qwen3-emb-0.6b"
ARCHIVO = ROOT.parent / "Samu-Enjoyer-archivo"
BLOQUE = 16 << 20


def contenido(manifest: Path, auditoria: Path) -> list[tuple[Path, str]]:
    """(origen, ruta dentro del zip)."""
    out = [(ROOT / "entregables" / "LICENSE_corpus_indice.txt", "corpus/LICENSE"),
           (manifest, "corpus/corpus_manifest.json"),
           (auditoria, "corpus/auditoria_descarga.json"),
           (CHUNKS / "chunks.sqlite", "corpus/chunks/chunks.sqlite"),
           (CHUNKS / "resumen.json", "corpus/chunks/resumen.json")]
    for d in ("bm25_todo", "bm25_normas", f"{DENSO}_todo", f"{DENSO}_normas"):
        for p in sorted((INDICES / d).iterdir()):
            if p.is_file() and not p.name.startswith("vec_") and not p.name.endswith(".tmp"):
                out.append((p, f"corpus/indices/{d}/{p.name}"))
    return out


def leeme(hashes: dict[str, tuple[int, str]]) -> str:
    info = {d: json.loads((INDICES / d / "info.json").read_text(encoding="utf-8"))
            for d in ("bm25_todo", "bm25_normas", f"{DENSO}_todo", f"{DENSO}_normas")}
    cfg = asdict(Config())
    filas = "\n".join(f"| `{n}` | {t / 1e6:,.0f} MB | `{h[:16]}…` |" for n, (t, h) in sorted(hashes.items()))
    return f"""# Corpus e índice — Samu-Enjoyer (Hackathon IA Week 2026)

Empaquetado el {dt.date.today().isoformat()}. Licencia: CC BY 4.0 (`corpus/LICENSE`).

## Contenido

| Ruta | Qué es |
|---|---|
| `corpus/corpus_manifest.json` | Manifiesto de descarga: fuente oficial, URL y fecha de consulta de cada documento |
| `corpus/auditoria_descarga.json` | Auditoría de cobertura de la descarga |
| `corpus/chunks/chunks.sqlite` | Corpus enriquecido: {info['bm25_todo']['n']:,} pasajes con su texto y metadatos (norma, artículo, ruta jerárquica, vigencia, fuente) |
| `corpus/indices/bm25_todo/` | BM25 (bm25s) sobre todos los pasajes; vocabulario {info['bm25_todo']['vocab']:,}, con raíces (Snowball) |
| `corpus/indices/{DENSO}_todo/` | HNSW (FAISS `IndexHNSWSQ` 8 bits, M=32, efSearch=256) de Qwen/Qwen3-Embedding-0.6B, dim {info[f'{DENSO}_todo']['dim']} |
| `corpus/indices/bm25_normas/`, `corpus/indices/{DENSO}_normas/` | Los mismos índices solo sobre normas ({info['bm25_normas']['n']:,} pasajes): lista extra de la fusión |

## Uso

Descomprimir en la raíz del repositorio (crea `corpus/`) y verificar:

```bash
python -m src.knowledge.verify_indices
```

Recuperación (BM25 + HNSW + lista de normas → RRF → bge-reranker-v2-m3 → 10 pasajes):

```python
from src.knowledge.hybrid_search import Recuperador
from src.knowledge.chunk_store import INDICES
r = Recuperador(INDICES / "bm25_todo", INDICES / "{DENSO}_todo", "bge-reranker-v2-m3")
r.buscar("¿Qué establece el artículo 42 del Código General del Proceso?").pasajes
```

El índice está congelado: la búsqueda sobre estos archivos es determinista (FAISS con un hilo,
desempates por chunk_id).

## Configuración de búsqueda (`Config()` por defecto)

```json
{json.dumps(cfg, ensure_ascii=False, indent=1)}
```

## Archivos (SHA-256 completo en `corpus/SHA256SUMS.txt`)

| Archivo | Tamaño | SHA-256 |
|---|---|---|
{filas}
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, default=ROOT.parent / "samu_enjoyer_corpus_indice.zip")
    ap.add_argument("--manifest", type=Path, default=ARCHIVO / "raw" / "corpus_manifest.json")
    ap.add_argument("--auditoria", type=Path, default=ARCHIVO / "descarga" / "auditoria.json")
    ap.add_argument("--simular", action="store_true")
    args = ap.parse_args()

    archivos = contenido(args.manifest, args.auditoria)
    faltan = [str(o) for o, _ in archivos if not o.exists()]
    total = sum(o.stat().st_size for o, _ in archivos if o.exists())
    for o, n in archivos:
        print(f"  {n:70s} {o.stat().st_size / 1e6:>10,.0f} MB" if o.exists() else f"  FALTA {o}")
    print(f"== {len(archivos)} archivos, {total / 1e9:.1f} GB sin comprimir")
    if faltan:
        raise SystemExit(f"Faltan {len(faltan)} archivos")
    if args.simular:
        return

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.salida.with_suffix(".zip.tmp")
    hashes, t0, hecho = {}, time.time(), 0
    with zipfile.ZipFile(tmp, "w", allowZip64=True) as z:
        for origen, nombre in archivos:
            zi = zipfile.ZipInfo(nombre, date_time=time.localtime(origen.stat().st_mtime)[:6])
            # Lo ya comprimido se guarda tal cual; lo demás, deflate.
            zi.compress_type = zipfile.ZIP_STORED if origen.suffix == ".gz" else zipfile.ZIP_DEFLATED
            h = hashlib.sha256()
            with origen.open("rb") as f, z.open(zi, "w", force_zip64=True) as dst:
                while bloque := f.read(BLOQUE):
                    h.update(bloque)
                    dst.write(bloque)
                    hecho += len(bloque)
            hashes[nombre] = (origen.stat().st_size, h.hexdigest())
            print(f"   {hecho / total:5.1%}  {nombre}  ({time.time() - t0:.0f} s)", flush=True)
        z.writestr("corpus/SHA256SUMS.txt", "".join(f"{h}  {n}\n" for n, (_, h) in sorted(hashes.items())))
        z.writestr("corpus/LEEME.md", leeme(hashes))
    tmp.replace(args.salida)
    zh = hashlib.sha256()
    with args.salida.open("rb") as f:
        while bloque := f.read(BLOQUE):
            zh.update(bloque)
    print(f"== {args.salida} ({args.salida.stat().st_size / 1e9:.2f} GB) en {time.time() - t0:.0f} s")
    print(f"   SHA-256 del zip: {zh.hexdigest()}")


if __name__ == "__main__":
    main()
