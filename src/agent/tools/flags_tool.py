"""Tool de flags: normaliza y completa los metadatos de una pregunta."""
from __future__ import annotations

import re
import unicodedata

FORMATOS = ("multiple_choice", "semi_open", "open_ended")
AREA_DEFAULT = "Derecho general"
SUB_TAREA_DEFAULT = "respuesta_general"

_ALIAS_FORMATO = {
    "multiple_choice": "multiple_choice", "multiplechoice": "multiple_choice", "cerrada": "multiple_choice",
    "opcion_multiple": "multiple_choice", "mcq": "multiple_choice",
    "semi_open": "semi_open", "semiopen": "semi_open", "semiabierta": "semi_open",
    "open_ended": "open_ended", "openended": "open_ended", "abierta": "open_ended", "open": "open_ended",
}

# Inferencia básica de área por palabras clave (solo si `area` no viene).
_AREA_REGEX = [
    (r"constituci|tutela|acci[oó]n de grupo|derechos fundamentales", "Derecho constitucional"),
    (r"proceso|demanda|juez|competencia|recurso|caducidad", "Derecho procesal"),
    (r"contrato|obligaci[oó]n|propiedad|sucesi[oó]n|matrimonio", "Derecho civil"),
    (r"penal|delito|pena\b|fiscal[ií]a", "Derecho penal"),
    (r"trabajador|laboral|despido|cesant[ií]as|salario", "Derecho laboral"),
    (r"consumidor|competencia desleal|datos personales|propiedad intelectual|SIC\b", "Derecho de los mercados"),
    (r"administrativ|contencioso|entidad p[uú]blica|acto administrativo", "Derecho administrativo"),
]

# Sub-tarea inferida de la redacción de la pregunta (solo si `sub_tarea` no viene).
_SUBTAREA_REGEX = [
    (r"\bqu[eé] normativa|\bqu[eé] norma|\bqu[eé] ley|cu[aá]l es la norma", "identificacion_norma"),
    (r"\bdefin|\bqu[eé] es\b|\bqu[eé] se entiende", "definicion"),
    (r"\bplazo|\bt[eé]rmino|\bcu[aá]nto tiempo|\bcaduc|\bprescri", "plazo_termino"),
    (r"\bprocede|\bprocedencia|\bcu[aá]ndo", "procedencia"),
    (r"\bcompetente|\bcompetencia|\bqui[eé]n conoce", "competencia"),
    (r"\banaliz|\bexpl[ií]que|\bjustifiq|\bargument", "analisis"),
]


def _norm(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", txt.strip().lower())
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"[\s\-]+", "_", txt)


def _vacio(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _inferir_formato(raw: dict) -> str:
    opciones = raw.get("opciones")
    if isinstance(opciones, dict) and len(opciones) >= 2:
        return "multiple_choice"
    pregunta = str(raw.get("pregunta") or "")
    if len(pregunta.split()) > 60 or re.search(r"\banaliz|\bcaso\b|\bhechos\b", pregunta, re.I):
        return "open_ended"
    return "semi_open"


def extract_query_flags(raw_item: dict) -> dict:
    """Extrae `area`, `sub_tarea`, `complejidad`, `tema` y `formato` de un item crudo.

    Usa el valor explícito si existe; si no, infiere por regex básica o aplica
    un default. Siempre devuelve las cinco llaves con valores no vacíos.
    """
    pregunta = str(raw_item.get("pregunta") or "")

    formato = None
    if not _vacio(raw_item.get("formato")):
        formato = _ALIAS_FORMATO.get(_norm(str(raw_item["formato"])))
    if formato is None:
        formato = _inferir_formato(raw_item)

    area = raw_item.get("area")
    if _vacio(area):
        area = next((a for rx, a in _AREA_REGEX if re.search(rx, pregunta, re.I)), AREA_DEFAULT)

    sub_tarea = raw_item.get("sub_tarea")
    if _vacio(sub_tarea):
        sub_tarea = next((s for rx, s in _SUBTAREA_REGEX if re.search(rx, pregunta, re.I)), SUB_TAREA_DEFAULT)

    complejidad = raw_item.get("complejidad")
    if _vacio(complejidad):
        n = len(pregunta.split())
        complejidad = "baja" if n < 20 else ("media" if n < 60 else "alta")

    tema = raw_item.get("tema")
    if _vacio(tema):
        tema = " ".join(pregunta.split()[:8]).strip("¿? ") or "sin_tema"

    return {
        "area": str(area).strip(),
        "sub_tarea": str(sub_tarea).strip(),
        "complejidad": str(complejidad).strip(),
        "tema": str(tema).strip(),
        "formato": formato,
    }
