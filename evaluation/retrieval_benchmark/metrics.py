"""Métricas de recuperación con varias normas relevantes por pregunta.

Una pregunta de la muestra tiene un `legal_basis` con una o varias normas. Se mide a
dos granularidades:

- citas: normas a nivel de cuerpo, como las compara el evaluador oficial
  (scripts/citations.py): ("ley", "1581", "2012"), ("codigo_civil", None, None).
  Una norma cuenta si aparece citada en el texto de los primeros k pasajes, que es
  lo que el evaluador llama "respaldada por la evidencia recuperada".
- documentos: doc_id del corpus al que corresponde cada norma del legal_basis.
"""
from __future__ import annotations

import math


def recall(relevantes: set, recuperados: set) -> float | None:
    return len(relevantes & recuperados) / len(relevantes) if relevantes else None


def reciprocal_rank(docs_en_orden: list[str], relevantes: set[str]) -> float:
    pos = next((i for i, d in enumerate(docs_en_orden, 1) if d in relevantes), None)
    return 1.0 / pos if pos else 0.0


def ndcg_at_k(docs_en_orden: list[str], relevantes: set[str], k: int) -> float:
    """nDCG@k binario: cada documento relevante cuenta una vez (su primera aparición)."""
    vistos, dcg = set(), 0.0
    for i, d in enumerate(docs_en_orden[:k], 1):
        if d in relevantes and d not in vistos:
            vistos.add(d)
            dcg += 1.0 / math.log2(i + 1)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevantes), k) + 1))
    return dcg / ideal if ideal else 0.0


def media(valores) -> float | None:
    v = [x for x in valores if x is not None]
    return round(sum(v) / len(v), 3) if v else None
