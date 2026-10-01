"""Tipos de cada campo del registro de submissions.jsonl, según el formato de la pregunta.

El LLM a veces devuelve un campo con otro tipo (la `justificacion` como lista, `palabras_clave`
como texto, la opción como "C. Ley 472 de 1998") o agrega llaves que no son del esquema. El
evaluador oficial (scripts/evaluate.py, el mismo del jurado) se cae con una lista donde espera
texto, así que antes de escribir el registro se deja cada campo con su tipo. Determinista.
"""
from __future__ import annotations

import re
from typing import Optional

TEXTO = {
    "multiple_choice": ("justificacion",),
    "semi_open": ("respuesta", "referencia_legal"),
    "open_ended": ("marco_normativo", "analisis", "jurisprudencia", "conclusion"),
}
CAMPOS = {
    "multiple_choice": ("respuesta_correcta", "justificacion", "descarte_opciones"),
    "semi_open": ("respuesta", "palabras_clave", "referencia_legal"),
    "open_ended": ("marco_normativo", "analisis", "jurisprudencia", "conclusion"),
}


def a_texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return " ".join(f"{k}: {a_texto(x)}" for k, x in v.items())
    if isinstance(v, (list, tuple)):
        return " ".join(a_texto(x) for x in v if a_texto(x))
    return str(v)


def _letra(v, opciones: Optional[dict]) -> Optional[str]:
    """La letra elegida: "C", "c", "C. Ley 472…", "Opción C" -> "C"; None si no hay una válida."""
    validas = sorted(opciones) if opciones else ["A", "B", "C", "D"]
    texto = a_texto(v).strip()
    if texto.upper() in validas:
        return texto.upper()
    # Solo formas inequívocas: "C.", "C)", "(C)", "C: …" al inicio, u "opción C". Una letra suelta en
    # medio del texto no sirve: "a", "y", "o", "e" son palabras.
    m = (re.match(r"^\(?([A-Za-z])[\).:\-]", texto)
         or re.search(r"\bopci[oó]n\s+\(?([A-Za-z])\b", texto, re.I))
    letra = m.group(1).upper() if m else None
    return letra if letra in validas else None


def normalizar(borrador: dict, formato: str, opciones: Optional[dict] = None) -> dict:
    """Solo los campos del esquema para `formato`, cada uno con su tipo."""
    out = {}
    for campo in CAMPOS.get(formato, ()):
        v = borrador.get(campo)
        if campo in TEXTO.get(formato, ()):
            out[campo] = a_texto(v)
        elif campo == "respuesta_correcta":
            out[campo] = _letra(v, opciones)
        elif campo == "descarte_opciones":
            out[campo] = {str(k): a_texto(x) for k, x in v.items()} if isinstance(v, dict) else {}
        elif campo == "palabras_clave":
            if isinstance(v, str):
                v = [t.strip() for t in re.split(r"[,;\n]", v)]
            out[campo] = [a_texto(t).strip() for t in (v or []) if a_texto(t).strip()]
    return out
