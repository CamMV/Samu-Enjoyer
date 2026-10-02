"""Expansión de la consulta para semiabiertas y abiertas (técnica admitida por el enunciado, 3.3).

El mismo Qwen3-8B local nombra las figuras jurídicas y las normas colombianas que probablemente
regulan la pregunta. Ese texto solo se usa para BUSCAR (una lista más en la fusión y, si nombra un
artículo, la cita expresa lo trae del corpus); la respuesta se sigue redactando únicamente con los
pasajes recuperados, y lo que el corpus no tenga no se puede citar.

Motivo: las preguntas en lenguaje natural o de caso no nombran la norma ("¿cuáles son los
elementos de validez de un contrato?" trae el contrato laboral del CST en vez del art. 1502 del
Código Civil). Temperatura 0, salida acotada por gramática: determinista en una misma máquina.

Configuración: EXPANDIR_CONSULTA=0 la apaga (por defecto encendida en semiabiertas y abiertas).
"""
from __future__ import annotations

import os
import sys

import requests

from src.agent.tools.writer_tool import _llamar_llm, _parsear_json

EXPANDIR_CONSULTA = os.environ.get("EXPANDIR_CONSULTA", "0") == "1"

_SYSTEM = (
    "Eres un abogado colombiano que prepara búsquedas en un corpus de normas y sentencias colombianas. "
    "No respondas la pregunta. Devuelve SOLO un objeto JSON con dos listas: \"figuras\" (de 2 a 6 "
    "instituciones, figuras o términos técnicos jurídicos que la pregunta involucra, como aparecerían en "
    "una norma) y \"normas\" (de 1 a 4 normas colombianas que probablemente la regulan: nombre, número y "
    "año, y el artículo si lo conoces, p. ej. 'Código Civil, artículo 1502' o 'Ley 472 de 1998')."
)
_ESQUEMA = {
    "type": "object",
    "properties": {"figuras": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
                   "normas": {"type": "array", "items": {"type": "string"}, "maxItems": 4}},
    "required": ["figuras", "normas"],
}


def expandir_consulta(pregunta: str, flags: dict | None = None) -> str:
    """Texto de búsqueda adicional: figuras jurídicas y normas candidatas. "" si falla o está apagada."""
    if not EXPANDIR_CONSULTA or not (pregunta or "").strip():
        return ""
    flags = flags or {}
    user = f"Área: {flags.get('area')} | Sub-tarea: {flags.get('sub_tarea')}\nPREGUNTA: {pregunta.strip()}"
    try:
        datos = _parsear_json(_llamar_llm(_SYSTEM, user, _ESQUEMA))
    except (requests.exceptions.RequestException, ValueError) as e:
        print(f"   AVISO: sin expansión de consulta ({type(e).__name__}: {e})", file=sys.stderr, flush=True)
        return ""
    partes = [str(x).strip() for x in (datos.get("figuras") or [])[:6] + (datos.get("normas") or [])[:4]
              if str(x).strip()]
    return "; ".join(partes)
