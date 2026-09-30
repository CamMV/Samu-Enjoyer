"""Citas normativas de un texto -> documentos y chunks del corpus.

Usa el extractor del evaluador oficial (scripts/citations.py), así que reconoce
exactamente las mismas citas con que se califica: "artículo 42 del Código General
del Proceso", "Ley 1581 de 2012, art. 5", "Sentencia C-355 de 2006".
"""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import citations  # noqa: E402  (evaluador oficial, sin cambios)

TARGETS = ROOT / "data" / "corpus_targets.json"


@lru_cache(maxsize=1)
def mapa_canonico() -> dict[tuple, str]:
    """(cuerpo, número, año) del evaluador -> doc_id del corpus."""
    docs = json.loads(TARGETS.read_text(encoding="utf-8"))["documentos"]
    mapa = {}
    for d in docs:
        c = d.get("canonico")
        if c:
            mapa[tuple(None if x is None else str(x) for x in c[:3])] = d["doc_id"]
    return mapa


def cuerpos(texto: str) -> set[tuple]:
    """Normas citadas a nivel de cuerpo (así compara el evaluador)."""
    return citations.bodies(citations.extract(texto or ""))


def documentos_citados(texto: str) -> dict[str, set[str | None]]:
    """doc_id -> artículos citados (None = la norma sin artículo)."""
    mapa = mapa_canonico()
    out: dict[str, set] = {}
    for cuerpo, num, anio, art in citations.extract(texto or ""):
        did = mapa.get((cuerpo, num, anio))
        if did:
            out.setdefault(did, set()).add(art)
    return out


def chunks_citados(texto: str, almacen) -> list[str]:
    """chunk_id de lo que la pregunta cita expresamente: el artículo (todas sus partes)
    o, en una sentencia, su ficha. Una norma citada sin artículo no se trae entera."""
    ids = []
    for did, arts in sorted(documentos_citados(texto).items()):
        if did.startswith("jurisprudencia_"):
            ids.append(f"{did}/ficha")
            continue
        for art in sorted(a for a in arts if a):
            ids += [c["chunk_id"] for c in almacen.por("articulo_id", f"{did}/art_{art}")
                    if c["tipo_chunk"] in ("articulo", "parte_articulo")]
    return ids
