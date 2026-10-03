"""Citas normativas de un texto -> documentos y chunks del corpus.

Usa el extractor del evaluador oficial (scripts/citations.py), así que reconoce
exactamente las mismas citas con que se califica: "artículo 42 del Código General
del Proceso", "Ley 1581 de 2012, art. 5", "Sentencia C-355 de 2006".
"""
from __future__ import annotations

import json
import re
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


# Sentencia de la Corte Constitucional con el año sin "de" ni separador ("sentencia C-076 2025"): el
# extractor oficial reconoce "C-076 de 2025", "C-076/25" y "C-076-2025", pero no esta forma (test, 430).
_SENTENCIA_SIN_DE = re.compile(r"\b(C|T|SU|A)-(\d{1,4})\s+((?:19|20)\d{2})\b")

# Sentencias del Consejo de Estado citadas por su número interno ("Exp. 25406", "sentencia 26644 de 2024
# del Consejo de Estado"): el extractor oficial solo reconoce el radicado completo.
_EXPEDIENTE = re.compile(r"\b(?:exp(?:ediente)?\.?|radicad[oa]|n[úu]mero interno)\s*(?:n(?:o|ro|úm)?\.?\s*[°º]?\s*)?"
                         r":?\s*(\d{4,6})\b", re.I)
_SENTENCIA_NUMERO = re.compile(r"\bsentencia\s+(?:n[o°º]\.?\s*)?(\d{4,6})\b", re.I)


@lru_cache(maxsize=1)
def expedientes_ce() -> dict[str, str]:
    """Número interno -> doc_id de las sentencias del Consejo de Estado (el número va entre paréntesis
    en la `norma` de corpus_targets: "radicado 11001-03-27-000-2020-00027-00 (25406)"). Solo los únicos."""
    docs = json.loads(TARGETS.read_text(encoding="utf-8"))["documentos"]
    vistos: dict[str, set] = {}
    for d in docs:
        if d["doc_id"].startswith("jurisprudencia_ce-"):
            for n in re.findall(r"\((\d{4,6})\)", d.get("norma", "")):
                vistos.setdefault(n, set()).add(d["doc_id"])
    return {n: next(iter(ds)) for n, ds in vistos.items() if len(ds) == 1}


def sentencias_por_expediente(texto: str) -> list[str]:
    """doc_id de las sentencias del Consejo de Estado que el texto cita por su número interno."""
    texto = texto or ""
    numeros = _EXPEDIENTE.findall(texto)
    if re.search(r"consejo de estado", texto, re.I):
        numeros += _SENTENCIA_NUMERO.findall(texto)
    mapa = expedientes_ce()
    return sorted({mapa[n] for n in numeros if n in mapa})


def documentos_citados(texto: str) -> dict[str, set[str | None]]:
    """doc_id -> artículos citados (None = la norma sin artículo)."""
    mapa = mapa_canonico()
    out: dict[str, set] = {}
    texto = _SENTENCIA_SIN_DE.sub(r"\1-\2 de \3", texto or "")
    for cuerpo, num, anio, art in citations.extract(texto):
        did = mapa.get((cuerpo, num, anio))
        if did:
            out.setdefault(did, set()).add(art)
    for did in sentencias_por_expediente(texto):
        out.setdefault(did, set()).add(None)
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
