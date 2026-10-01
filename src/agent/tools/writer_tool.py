"""Tool de escritura: redacta la respuesta jurídica con Qwen3-8B (temperature=0).

Se conecta EXCLUSIVAMENTE a una instancia LOCAL de Qwen3-8B (modelo abierto)
servida por vLLM / Ollama / llama.cpp con API compatible con OpenAI
(endpoint /v1/chat/completions). Por regla del reto no se usan APIs ni modelos
cerrados (OpenAI, Anthropic, Google, Cohere): el cliente es `requests` puro y
se rechaza cualquier LLM_BASE_URL que apunte a un SaaS de terceros.

Si la llamada falla (caída de conexión, timeout, error HTTP), la pregunta queda
en abstención y el error se avisa en stderr: nunca se entrega una respuesta
simulada como si fuera real. El escritor simulado (mock) solo se usa a pedido
(`--mock` en batch_runner).

Dependencias (ver requirements-agent.txt):
    pydantic>=2.6.0      modelos CanonicalPassage / QuestionState
    requests>=2.31.0     cliente HTTP hacia el servidor local
    python-dotenv>=1.0.0 carga de variables desde un archivo .env

Configuración por entorno o .env:
    LLM_BASE_URL  (default http://localhost:8000/v1)
    LLM_MODEL     (default Qwen/Qwen3-8B)
    LLM_TIMEOUT   segundos (default 300: en el portátil el LLM corre en CPU y leer
                  10 pasajes toma minutos)
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Optional
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from src.agent.schemas import CanonicalPassage

load_dotenv()

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "Qwen/Qwen3-8B")
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "300"))

# Proveedores cerrados prohibidos por el reto (causal de descalificación).
_HOSTS_PROHIBIDOS = ("openai", "anthropic", "google", "googleapis", "cohere", "azure", "mistral")

_SYSTEM_BASE = (
    "Eres un asistente jurídico colombiano. Responde EXCLUSIVAMENTE con la información de los "
    "PASAJES entregados; no uses conocimiento externo ni inventes normas. Cita cada norma con su "
    "ID canónico exactamente como aparece entre corchetes (ej. [codigo_general_proceso/art_42]). No cites "
    "ningún ID que no esté en los pasajes. No presentes como vigente una norma marcada derogada o "
    "transitoria. Si los pasajes no bastan para responder, devuelve {\"abstencion\": true}. "
    "Responde SOLO con un objeto JSON válido, sin texto adicional."
)

_FORMATO_INSTRUCCIONES = {
    "multiple_choice": (
        # La justificación va ANTES de la letra: el modelo escribe en orden y, con la letra primero,
        # elegía antes de razonar (pregunta 671: razonaba la C y había respondido B).
        'Devuelve JSON con las llaves, en este orden: "justificacion" (primero razona con los pasajes '
        'qué opción es correcta y por qué, citando IDs canónicos), "respuesta_correcta" (la letra de '
        'la opción que tu justificación respalda), "descarte_opciones" (objeto con la letra de cada '
        'opción incorrecta y una razón breve), "abstencion" (boolean). Si una opción nombra una norma '
        'con el número correcto pero otro año (error de digitación), identifícala por su número y por el '
        'nombre que trae el encabezado del pasaje. Si la pregunta da un monto en pesos y un pasaje fija '
        'el salario mínimo, convierte el monto a salarios mínimos antes de compararlo con los umbrales.'
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


# Presupuesto de caracteres para los 10 pasajes DENTRO del prompt (escritor y juez), con el LLM
# en contexto de 32k tokens (-c 32768). Se reparte de forma justa: los pasajes que caben van
# completos y solo se recortan los más largos, con lo que sobra. En las 50 de muestra, 45 entran
# sin recortar nada; las 5 restantes traen anexos de 59k-310k tokens metidos en un solo artículo.
# 85.000 caracteres ≈ 24k tokens (3,6 caracteres por token medidos con el tokenizador de Qwen3):
# queda margen para instrucciones, pregunta, borrador (juez) y respuesta. En submissions.jsonl
# los pasajes van completos.
MAX_CHARS_PASAJES = int(os.environ.get("MAX_CHARS_PASAJES", "85000"))


def cupos(longitudes: list[int], presupuesto: int = None) -> list[int]:
    """Caracteres para cada pasaje: el que cabe en su parte justa va completo y lo que no usa se
    reparte entre los demás. Determinista; conserva el orden."""
    restante = MAX_CHARS_PASAJES if presupuesto is None else presupuesto
    cupo = [0] * len(longitudes)
    pendientes = sorted(range(len(longitudes)), key=lambda i: (longitudes[i], i))
    for n, i in enumerate(pendientes):
        cupo[i] = min(longitudes[i], max(restante, 0) // (len(pendientes) - n))
        restante -= cupo[i]
    return cupo


def textos_para_prompt(pasajes: list[CanonicalPassage]) -> list[str]:
    textos = [p.texto or "" for p in pasajes]
    salida = []
    for texto, c in zip(textos, cupos([len(t) for t in textos])):
        salida.append(texto if c >= len(texto) else texto[:c].rsplit(" ", 1)[0] + " […recortado]")
    return salida


def build_prompts(pregunta: str, flags: dict, pasajes: list[CanonicalPassage],
                  opciones: Optional[dict] = None) -> tuple[str, str]:
    """Construye (system_prompt, user_prompt)."""
    system = f"{_SYSTEM_BASE}\n{_FORMATO_INSTRUCCIONES[flags['formato']]}"
    bloques = []
    for p, texto in zip(pasajes, textos_para_prompt(pasajes)):
        vig = p.metadatos.get("vigencia", "desconocida")
        bloques.append(f"[{p.id}] (vigencia: {vig})\n{texto}")
    partes = [
        f"Área: {flags.get('area')} | Tema: {flags.get('tema')} | Sub-tarea: {flags.get('sub_tarea')}",
        "PASAJES:\n" + ("\n\n".join(bloques) if bloques else "(ninguno)"),
        f"PREGUNTA: {pregunta}",
    ]
    if opciones:
        partes.append("OPCIONES:\n" + "\n".join(f"{k}. {v}" for k, v in sorted(opciones.items())))
    return system, "\n\n".join(partes)


def _verificar_host_local(base_url: str) -> None:
    host = (urlparse(base_url).hostname or "").lower()
    if any(p in host for p in _HOSTS_PROHIBIDOS):
        raise ValueError(f"LLM_BASE_URL apunta a un proveedor cerrado prohibido: {host}")


def _llamar_llm(system: str, user: str) -> str:
    """POST al Qwen3-8B local (modelo abierto). Lanza `requests.exceptions.RequestException`
    si falla la conexión, hay timeout o el servidor responde con error HTTP.

    Sin modo de razonamiento: con él las cerradas tardarían minutos más en el portátil (CPU,
    ~2 tokens/s) y la verificación en vivo no reproduciría las respuestas de la A40."""
    _verificar_host_local(LLM_BASE_URL)
    payload = {
        "model": LLM_MODEL,
        "temperature": 0,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "chat_template_kwargs": {"enable_thinking": False},  # Qwen3: sin bloque <think>
    }
    resp = requests.post(f"{LLM_BASE_URL.rstrip('/')}/chat/completions", json=payload, timeout=LLM_TIMEOUT)
    resp.raise_for_status()
    try:
        return resp.json()["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise requests.exceptions.RequestException(f"Respuesta del servidor con formato inesperado: {e}") from e


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
    más `formato` y `abstencion`. Sin pasajes, abstención. Si la llamada al servidor
    LLM falla o responde JSON inválido, abstención (con aviso en stderr si falló la llamada).
    """
    formato = flags["formato"]
    if not pasajes:
        return _abstencion(formato)
    system, user = build_prompts(pregunta, flags, pasajes, opciones)
    try:
        salida = _llamar_llm(system, user)
    except requests.exceptions.RequestException as e:  # conexión caída, timeout, HTTP error
        print(f"   AVISO: el LLM no respondió ({type(e).__name__}: {e}); la pregunta queda en abstención",
              file=sys.stderr, flush=True)
        return _abstencion(formato)
    try:
        borrador = _parsear_json(salida)
    except ValueError:  # JSON inválido: el servidor respondió, no se enmascara con el mock
        return _abstencion(formato)
    borrador["formato"] = formato
    borrador["abstencion"] = bool(borrador.get("abstencion", False))
    return borrador
