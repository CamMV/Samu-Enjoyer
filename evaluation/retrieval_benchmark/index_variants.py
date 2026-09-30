"""Construye lo que cada brazo necesita: chunks, BM25 (con y sin raíces) y un HNSW por
embedder. Cada paso se salta si su salida ya existe (reanudable); --force lo rehace.
"""
from __future__ import annotations

import shutil
import subprocess
import sys

from evaluation.retrieval_benchmark.config import ROOT, dir_bm25, dir_denso
from src.knowledge import bm25_store, vector_store
from src.knowledge.chunk_store import CHUNKS


def chunks(procesos: int, force: bool = False):
    if (CHUNKS / "chunks.sqlite").exists() and (CHUNKS / "resumen.json").exists() and not force:
        print(f"[chunks] ya existen en {CHUNKS}")
        return
    subprocess.run([sys.executable, "-m", "src.knowledge.chunking", "--procesos", str(procesos)], cwd=ROOT, check=True)


def bm25(seleccion: str, raices: bool, force: bool = False):
    d = dir_bm25(seleccion, raices)
    if (d / "info.json").exists() and not force:
        print(f"[bm25] ya existe {d.name}")
        return
    shutil.rmtree(d, ignore_errors=True)
    bm25_store.construir(seleccion, d, raices=raices)


def denso(embedder: str, seleccion: str, dispositivo: str | None, lote_gpu: int, force: bool = False):
    d = dir_denso(embedder, seleccion)
    if (d / "hnsw.faiss").exists() and (d / "info.json").exists() and not force:
        print(f"[index] ya existe {d.name}")
        return
    if force:
        shutil.rmtree(d, ignore_errors=True)
    # Sin --force, los lotes de vectores ya guardados se reutilizan (checkpoint).
    vector_store.construir(embedder, seleccion, d, lote_gpu, None, False, dispositivo)
