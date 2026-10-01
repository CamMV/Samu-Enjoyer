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

import os
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


# --- Texto que lee RAGAS ----------------------------------------------------------------------
# RAGAS (answer correctness) cuenta como error cada afirmación que no está en la respuesta esperada,
# aunque sea cierta: sobre v2, con las mismas respuestas, sacar las citas del texto de `respuesta`
# (pasan a `referencia_legal`, que lee el evaluador de citas y no RAGAS) subió 0,438 -> 0,456 y
# dejar además 3 oraciones, 0,462; citación y abstención, iguales.
MAX_ORACIONES_RESPUESTA = int(os.environ.get("MAX_ORACIONES_RESPUESTA", "3"))
_PAREN = re.compile(r"\s*\((?:[^()]|\([^()]*\))*\)")
_ES_CITA = re.compile(r"art[ií]culo|\bley\b|decreto|sentencia|c[oó]digo|constituci[oó]n|estatuto", re.I)
_ORACION = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡])")
# Encabezado de sección de una sentencia copiado de un pasaje: "› II. LA DEMANDA DE CASACIÓN (32/78)".
_SECCION = re.compile(r"\s*›[^›()\n;]*?\(\d+/\d+\)")


def sin_encabezados(borrador: dict) -> dict:
    """Quita de todos los textos los encabezados de sección de sentencias que el LLM copia de los pasajes."""
    def limpiar(v):
        if isinstance(v, str):
            return _SECCION.sub("", v)
        if isinstance(v, dict):
            return {k: limpiar(x) for k, x in v.items()}
        if isinstance(v, list):
            return [limpiar(x) for x in v]
        return v
    return limpiar(borrador)


def respuesta_concisa(borrador: dict, max_oraciones: int = None) -> dict:
    """Semiabiertas: las citas entre paréntesis de `respuesta` pasan a `referencia_legal` y la respuesta
    queda en sus primeras `max_oraciones` oraciones (el esquema pide de 3 a 5)."""
    n = MAX_ORACIONES_RESPUESTA if max_oraciones is None else max_oraciones
    texto = str(borrador.get("respuesta") or "")
    citas = [m.group(0).strip()[1:-1].strip() for m in _PAREN.finditer(texto) if _ES_CITA.search(m.group(0))]
    texto = _PAREN.sub(lambda m: "" if _ES_CITA.search(m.group(0)) else m.group(0), texto)
    texto = re.sub(r"\s+([.,;:])", r"\1", texto).strip()
    if n:
        texto = " ".join(_ORACION.split(texto)[:n]).strip()
    previa = str(borrador.get("referencia_legal") or "").strip()
    nuevas = [c for c in dict.fromkeys(citas) if c not in previa]
    referencia = "; ".join([x for x in [previa.rstrip(".;")] + nuevas if x])
    return {**borrador, "respuesta": texto, "referencia_legal": referencia}


# Campo donde van las normas consultadas: el que lee el extractor de citas del evaluador y que no
# entra en la corrección de texto libre (RAGAS). En las abiertas todos sus campos van a RAGAS:
# no se tocan.
_CAMPO_NORMAS = {"multiple_choice": "justificacion", "semi_open": "referencia_legal"}


def normas_consultadas(pasajes: List[CanonicalPassage]) -> List[str]:
    """Citas legibles de los pasajes de normas (no sentencias), en el orden de la recuperación."""
    out: List[str] = []
    for p in pasajes:
        nombre = nombre_documento(p)
        if nombre.lower().startswith(("corte", "consejo", "sentencia", "tribunal", "csj")):
            continue
        resto = p.id.split("/", 1)[1] if "/" in p.id else ""
        cita = _cita(nombre, resto)
        if cita not in out:
            out.append(cita)
    return out


def con_normas_consultadas(borrador: dict, formato: str, pasajes: List[CanonicalPassage]) -> dict:
    """Agrega al campo de fundamento ("justificacion" en cerradas, "referencia_legal" en
    semiabiertas) la lista de normas de los pasajes en que se basó la respuesta.

    La respuesta se redacta solo con esos pasajes, así que son su fundamento consultado; quedan
    nombradas con el encabezado de su propio pasaje (respaldadas) y salen de la recuperación
    determinista, no del LLM: la verificación en vivo las reproduce igual. Un escritor de 8B suele
    citar uno o dos pasajes aunque use más (en la muestra, 13 de las 49 normas de referencia
    estaban en los pasajes sin que la respuesta las nombrara)."""
    campo = _CAMPO_NORMAS.get(formato)
    normas = normas_consultadas(pasajes)
    if not campo or not normas:
        return borrador
    previo = str(borrador.get(campo) or "").strip()
    lista = "Normas de los pasajes consultados: " + "; ".join(normas) + "."
    return {**borrador, campo: f"{previo} {lista}".strip() if previo else lista}
