"""Convierte las citas con ID canónico del borrador en citas que reconoce el evaluador oficial.

El escritor cita con IDs entre corchetes (`[codigo_general_proceso/art_42]`) para que el validador
y el juez puedan comprobarlas contra los pasajes; pero `scripts/citations.py` (el extractor del
evaluador) no reconoce ese formato y esas citas valdrían 0. Al armar el registro de
submissions.jsonl cada ID se reescribe con el nombre que trae el encabezado del pasaje:

    [codigo_general_proceso/art_42] -> (artículo 42 del Código General del Proceso (Ley 1564 de 2012))
    [ley_1581_2012/art_5]           -> (artículo 5 de la Ley 1581 de 2012)
    [jurisprudencia_c-355_2006/ficha] -> (Corte Constitucional, Sentencia C-355 de 2006)
    ley_1581_2012/art_5 (suelto, p. ej. en referencia_legal) -> artículo 5 de la Ley 1581 de 2012

Como el nombre sale del mismo encabezado que lleva el pasaje, toda cita convertida queda
respaldada por la evidencia. Determinista, sin LLM.
"""
from __future__ import annotations

import re
from typing import List

from src.agent.schemas import CanonicalPassage

# ID canónico: <doc_id>/<resto>, entre corchetes o suelto (p. ej. en referencia_legal).
# \w (Unicode): las secciones de sentencias llevan tildes ("vi_fundamento_jurídico#4").
_ID_RE = re.compile(r"\[?\b([a-z0-9][\w.\-]*)/([\w.\-~#/]+)\]?", re.I)
_ART_RE = re.compile(r"^art_([0-9][0-9a-z.\-]*)", re.I)
# Nombres que piden "del" (masculinos); el resto, "de la".
_MASCULINOS = ("código", "codigo", "decreto", "estatuto", "acto legislativo", "acuerdo", "concepto", "auto",
               "reglamento", "régimen", "regimen")


def nombre_documento(p: CanonicalPassage) -> str:
    """Nombre citable del documento: la primera parte del encabezado del pasaje."""
    primera = (p.texto or "").split("\n", 1)[0]
    return primera.split(" › ", 1)[0].strip() or p.doc_id


def _cita(nombre: str, resto: str) -> str:
    m = _ART_RE.match(resto)
    # Sentencias, preámbulos, anexos o artículos sin número: se cita el documento.
    if not m or nombre.lower().startswith(("corte", "consejo", "sentencia", "tribunal")):
        return nombre
    prep = "del" if nombre.lower().startswith(_MASCULINOS) else "de la"
    if nombre.lower().startswith(("ley", "constitución", "constitucion", "resolución", "resolucion",
                                  "decisión", "decision", "circular", "directiva")):
        prep = "de la"
    return f"artículo {m.group(1).rstrip('.-')} {prep} {nombre}"


def citas_legibles(texto: str, nombres: dict[str, str]) -> str:
    """Reescribe en `texto` cada ID canónico de un documento conocido; deja intacto lo demás.
    Un ID entre corchetes de un documento que no está en los pasajes se quita (el validador ya
    debió suprimirlo; el evaluador no lo entendería y no tiene respaldo)."""
    def sustituir(m: re.Match) -> str:
        doc, resto = m.group(1).lower(), m.group(2)
        con_corchetes = m.group(0).startswith("[") and m.group(0).endswith("]")
        if doc in nombres:
            cita = _cita(nombres[doc], resto)
            # Entre corchetes va como referencia dentro de una oración: entre paréntesis se lee bien.
            return f"({cita})" if con_corchetes else cita
        return "" if con_corchetes else m.group(0)

    salida = _ID_RE.sub(sustituir, texto)
    return re.sub(r"[ \t]{2,}", " ", salida)


def borrador_con_citas_legibles(borrador: dict, pasajes: List[CanonicalPassage]) -> dict:
    """Copia del borrador con las citas convertidas en todos sus textos (incluidos los anidados)."""
    nombres: dict[str, str] = {}
    for p in pasajes:
        nombres.setdefault(p.doc_id.lower(), nombre_documento(p))

    def convertir(v):
        if isinstance(v, str):
            return citas_legibles(v, nombres)
        if isinstance(v, dict):
            return {k: convertir(x) for k, x in v.items()}
        if isinstance(v, list):
            return [convertir(x) for x in v]
        return v

    return convertir(borrador)
