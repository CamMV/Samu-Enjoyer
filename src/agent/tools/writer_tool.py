"""Tool de escritura: redacta la respuesta jurídica con Qwen3-8B (temperature=0).

Usa un servidor OpenAI-compatible (vLLM, llama.cpp, Ollama...) configurable por
entorno: LLM_BASE_URL (default http://localhost:8000/v1), LLM_MODEL
(default Qwen/Qwen3-8B). Si no hay servidor, cae a un fallback determinista
(mock) que devuelve un JSON válido según submission.schema.json.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Optional

from src.agent.schemas import CanonicalPassage

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "Qwen/Qwen3-8B")
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "120"))

_SYSTEM_BASE = (
    "Eres un asistente jurídico colombiano. Responde EXCLUSIVAMENTE con la información de los "
    "PASAJES entregados; no uses conocimiento externo ni inventes normas. Cita cada norma con su "
    "ID canónico exactamente como aparece entre corchetes (ej. [ley_1564_2012/art_42]). No cites "
    "ningún ID que no esté en los pasajes. No presentes como vigente una norma marcada derogada o "
    "transitoria. Si los pasajes no bastan para responder, devuelve {\"abstencion\": true}. "
    "Responde SOLO con un objeto JSON válido, sin texto adicional."
)

_FORMATO_INSTRUCCIONES = {
    "multiple_choice": (
        'Devuelve JSON con las llaves: "respuesta_correcta" (una letra de las opciones), '
        '"justificacion" (citando IDs canónicos), "descarte_opciones" (objeto con la letra de cada '
        'opción incorrecta y una razón breve), "abstencion" (boolean).'
    ),
    "semi_open": (
        'Devuelve JSON con las llaves: "respuesta" (3 a 5 oraciones, máximo 150 palabras, citando '
        'IDs canónicos), "palabras_clave" (lista de strings), "referencia_legal" (IDs/normas citadas), '
        '"abstencion" (boolean).'
    ),
    "open_ended": (
        'Devuelve JSON con las llaves: "marco_normativo", "analisis" (5 a 8 oraciones citando IDs '
        'canónicos), "jurisprudencia" (solo la que esté en los pasajes; si no hay, dilo), '
        '"conclusion", "abstencion" (boolean).'
    ),
}


def build_prompts(pregunta: str, flags: dict, pasajes: list[CanonicalPassage],
                  opciones: Optional[dict] = None) -> tuple[str, str]:
    """Construye (system_prompt, user_prompt)."""
    system = f"{_SYSTEM_BASE}\n{_FORMATO_INSTRUCCIONES[flags['formato']]}"
    bloques = []
    for p in pasajes:
        vig = p.metadatos.get("vigencia", "desconocida")
        bloques.append(f"[{p.id}] (vigencia: {vig})\n{p.texto}")
    partes = [
        f"Área: {flags.get('area')} | Tema: {flags.get('tema')} | Sub-tarea: {flags.get('sub_tarea')}",
        "PASAJES:\n" + ("\n\n".join(bloques) if bloques else "(ninguno)"),
        f"PREGUNTA: {pregunta}",
    ]
    if opciones:
        partes.append("OPCIONES:\n" + "\n".join(f"{k}. {v}" for k, v in sorted(opciones.items())))
    return system, "\n\n".join(partes)


def _llamar_llm(system: str, user: str) -> str:
    payload = {
        "model": LLM_MODEL,
        "temperature": 0,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        f"{LLM_BASE_URL.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def _parsear_json(texto: str) -> dict:
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.S).strip()
    m = re.search(r"\{.*\}", texto, flags=re.S)
    if not m:
        raise ValueError("La salida del LLM no contiene JSON")
    return json.loads(m.group(0))


# --- Fallback / mock -------------------------------------------------------

_STOP = set("de la el los las un una y o en a que por con para del al se es su sus lo como más no".split())


def _tokens(txt: str) -> set[str]:
    return {t for t in re.findall(r"\w+", txt.lower()) if len(t) > 3 and t not in _STOP}


def _resumen(texto: str, n: int = 200) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= n else texto[:n].rsplit(" ", 1)[0] + "..."


def _abstencion(formato: str) -> dict:
    base = {"formato": formato, "abstencion": True}
    if formato == "multiple_choice":
        return {**base, "respuesta_correcta": None, "justificacion": "Sin fundamento suficiente en el corpus.",
                "descarte_opciones": {}}
    if formato == "semi_open":
        return {**base, "respuesta": "Sin fundamento suficiente en el corpus.", "palabras_clave": [],
                "referencia_legal": ""}
    return {**base, "marco_normativo": "", "analisis": "Sin fundamento suficiente en el corpus.",
            "jurisprudencia": "", "conclusion": "No es posible responder con el corpus disponible."}


def mock_write_legal_response(pregunta: str, flags: dict, pasajes: list[CanonicalPassage],
                              opciones: Optional[dict] = None) -> dict:
    """Fallback determinista sin LLM: elige por solapamiento léxico con los pasajes."""
    formato = flags["formato"]
    if not pasajes:
        return _abstencion(formato)
    ids = ", ".join(p.id for p in pasajes[:3])
    top = pasajes[0]
    if formato == "multiple_choice":
        opciones = opciones or {}
        tok_p = _tokens(" ".join(p.texto for p in pasajes))
        puntajes = {k: len(_tokens(v) & tok_p) / (len(_tokens(v)) or 1) for k, v in opciones.items()}
        elegida = max(sorted(puntajes), key=lambda k: puntajes[k]) if puntajes else None
        return {
            "formato": formato, "abstencion": False, "respuesta_correcta": elegida,
            "justificacion": f"[MOCK] Opción con mayor respaldo léxico en [{top.id}]: {_resumen(top.texto)}",
            "descarte_opciones": {k: f"[MOCK] Menor respaldo en los pasajes ({ids})."
                                  for k in opciones if k != elegida},
        }
    if formato == "semi_open":
        return {
            "formato": formato, "abstencion": False,
            "respuesta": f"[MOCK] Según [{top.id}]: {_resumen(top.texto, 300)}",
            "palabras_clave": sorted(_tokens(pregunta))[:5],
            "referencia_legal": ", ".join(p.id for p in pasajes[:3]),
        }
    return {
        "formato": formato, "abstencion": False,
        "marco_normativo": f"[MOCK] Normas recuperadas: {ids}.",
        "analisis": f"[MOCK] Según [{top.id}]: {_resumen(top.texto, 400)}",
        "jurisprudencia": "[MOCK] No se verificó jurisprudencia en los pasajes.",
        "conclusion": f"[MOCK] Conclusión provisional con base en [{top.id}].",
    }


def write_legal_response(pregunta: str, flags: dict, pasajes: list[CanonicalPassage],
                         opciones: dict = None) -> dict:
    """Redacta la respuesta según `flags['formato']` usando solo `pasajes`.

    Devuelve el borrador con las llaves del schema de entrega para ese formato
    más `formato` y `abstencion`. Sin pasajes, abstención. Si no hay servidor
    LLM o su salida no es JSON válido, usa `mock_write_legal_response`.
    """
    formato = flags["formato"]
    if not pasajes:
        return _abstencion(formato)
    system, user = build_prompts(pregunta, flags, pasajes, opciones)
    try:
        borrador = _parsear_json(_llamar_llm(system, user))
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return mock_write_legal_response(pregunta, flags, pasajes, opciones)
    borrador["formato"] = formato
    borrador["abstencion"] = bool(borrador.get("abstencion", False))
    return borrador
