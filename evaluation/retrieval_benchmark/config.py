"""Brazos del banco de pruebas de recuperación.

Se comparan, sobre el mismo corpus de chunks:
- embedders para el HNSW (src/knowledge/embedding_variants.py): bge-m3,
  Qwen3-Embedding-0.6B y multilingual-e5-large-instruct;
- BM25 con y sin raíces (stemming);
- rerankers: bge-reranker-v2-m3, Qwen3-Reranker-0.6B y sin reranker.

Primero sobre el subcorpus "normas_fichas" (normas completas + fichas de sentencias:
minutos por modelo en la A40); el ganador se indexa sobre "todo".
"""
from __future__ import annotations

from pathlib import Path

from src.knowledge.chunk_store import INDICES
from src.knowledge.embedding_variants import EMBEDDERS, RERANKERS

ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = ROOT / "evaluation" / "retrieval_benchmark" / "results"
MUESTRA = ROOT / "data" / "sample_50.jsonl"

EMBEDDERS_BANCO = list(EMBEDDERS)                    # los tres
RERANKERS_BANCO = [*RERANKERS, None]                 # los dos y sin reranker
BM25_BANCO = [True, False]                           # con raíces, sin raíces
K = 10


def dir_bm25(seleccion: str, raices: bool = True) -> Path:
    return INDICES / (f"bm25_{seleccion}" + ("" if raices else "_sin_raices"))


def dir_denso(embedder: str, seleccion: str) -> Path:
    return INDICES / f"{embedder}_{seleccion}"


def nombre_brazo(embedder: str | None, raices: bool, reranker: str | None, seleccion: str,
                 perfil: str = "base") -> str:
    partes = [seleccion, embedder or "sin_denso", "bm25" if raices else "bm25_sin_raices",
              reranker or "sin_reranker"]
    if perfil != "base":  # los resultados ya guardados del perfil base conservan su nombre
        partes.append(perfil)
    return "__".join(partes)
