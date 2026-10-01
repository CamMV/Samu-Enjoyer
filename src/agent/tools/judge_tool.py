"""Tool del juez (LLM as judge): revisa el borrador del escritor contra los pasajes recuperados.

Evalúa tres cosas, usando SOLO los 10 pasajes como evidencia:
    1. si el borrador responde la pregunta y su sub-tarea;
    2. si cada afirmación tiene un pasaje que la soporte;
    3. si el área jurídica es coherente (señal blanda: se registra, no rechaza).

En las cerradas el juez no revisa: VOTA (`votar_cerrada`). Responde la pregunta a ciegas, sin ver el
borrador, y el borrador se aprueba si su letra coincide con la del escritor. Si discrepan, el grafo
vuelve a buscar y se vota de nuevo; si la discrepancia persiste se entrega la respuesta del escritor.

El juez nunca ve la clave (`respuesta_correcta`, `respuesta_esperada`, `legal_basis`): en el
test no existe y contaminaría el veredicto.

Corre sobre un modelo ABIERTO y LOCAL, distinto del escritor (por defecto Gemma 4 E4B en Ollama; vía vLLM / Ollama / llama.cpp, API
compatible con OpenAI), con el mismo bloqueo de proveedores cerrados que el escritor. Si el
servidor falla o responde algo que no es el JSON esperado, el veredicto queda sin decisión
(`aprobado=None`) y el borrador se conserva: el juez nunca detiene el lote.

Configuración por entorno o .env:
    JUDGE_BASE_URL    (default http://localhost:11434/v1; servidor propio: llama.cpp ignora el campo
                      "model", así que apuntar al servidor del escritor haría juzgar al mismo Qwen)
    JUDGE_MODEL       (default gemma4:e4b)
    JUDGE_TIMEOUT     segundos (default 300)
    JUDGE_MAX_TOKENS  (default 1024)
    JUDGE_THINKING    1 activa el razonamiento del modelo si lo soporta (default 0)
    JUDGE_VOTO_CERRADAS  0 vuelve a la revisión del borrador también en las cerradas (default 1)
"""
from __future__ import annotations

import os
import re
import sys
from typing import List, Literal, Optional

import requests
from pydantic import BaseModel, Field

from src.agent.schemas import CanonicalPassage, QuestionState
from src.agent.tools.writer_tool import (_parsear_json, _tokens, _verificar_host_local,
                                         textos_para_prompt)

JUDGE_BASE_URL = os.environ.get("JUDGE_BASE_URL") or "http://localhost:11434/v1"
JUDGE_MODEL = os.environ.get("JUDGE_MODEL") or "gemma4:e4b"
JUDGE_TIMEOUT = float(os.environ.get("JUDGE_TIMEOUT", "300"))
JUDGE_MAX_TOKENS = int(os.environ.get("JUDGE_MAX_TOKENS", "1024"))
JUDGE_THINKING = os.environ.get("JUDGE_THINKING", "0") == "1"
JUDGE_VOTO_CERRADAS = os.environ.get("JUDGE_VOTO_CERRADAS", "1") != "0"


class Veredicto(BaseModel):
    """Resultado del juez sobre un borrador."""

    responde_sub_tarea: bool = True
    afirmaciones_sin_soporte: List[str] = Field(default_factory=list)
    pasajes_suficientes: bool = True
    area_coherente: bool = True
    feedback: str = ""
    consulta_sugerida: str = ""
    citas_invalidas: List[str] = Field(default_factory=list, description="IDs citados que no están en los pasajes")
    aprobado: Optional[bool] = Field(default=None, description="None = el juez no pudo decidir")
    origen: Literal["llm", "voto", "determinista", "mock", "error"] = "llm"
    voto: Optional[str] = Field(default=None, description="Cerradas: letra que votó el juez a ciegas")
    voto_escritor: Optional[str] = Field(default=None, description="Cerradas: letra del borrador")

    @property
    def problemas(self) -> int:
        return len(self.afirmaciones_sin_soporte) + len(self.citas_invalidas) + (not self.responde_sub_tarea)


# Lo que el modelo debe devolver; `aprobado` no se le pide: se calcula en código.
_ESQUEMA = {
    "type": "object",
    "properties": {
        "responde_sub_tarea": {"type": "boolean"},
        "afirmaciones_sin_soporte": {"type": "array", "items": {"type": "string"}},
        "pasajes_suficientes": {"type": "boolean"},
        "area_coherente": {"type": "boolean"},
        "feedback": {"type": "string"},
        "consulta_sugerida": {"type": "string"},
    },
    "required": ["responde_sub_tarea", "afirmaciones_sin_soporte", "pasajes_suficientes", "area_coherente",
                 "feedback", "consulta_sugerida"],
}

_SYSTEM = (
    "Eres un juez jurídico colombiano estricto. Revisas el BORRADOR de otro asistente contra los "
    "PASAJES recuperados. Los PASAJES son la única evidencia admisible: no uses conocimiento externo, "
    "ni para aprobar ni para rechazar. Evalúa:\n"
    "1. responde_sub_tarea: ¿el borrador responde lo que pide la PREGUNTA y su sub-tarea?\n"
    "2. afirmaciones_sin_soporte: lista cada afirmación jurídica del borrador que ningún pasaje respalda, "
    "o que contradice un pasaje, o que presenta como vigente una norma marcada derogada o transitoria. "
    "Copia la afirmación en pocas palabras. Lista vacía si todas tienen soporte.\n"
    "3. pasajes_suficientes: ¿los pasajes contienen lo necesario para responder la pregunta?\n"
    "4. area_coherente: ¿las normas usadas pertenecen al área jurídica indicada?\n"
    "5. feedback: una o dos oraciones con lo que hay que corregir (vacío si no hay nada).\n"
    "6. consulta_sugerida: si faltan pasajes, términos jurídicos y normas que habría que buscar para "
    "encontrarlos (vacío si los pasajes bastan).\n"
    "Responde SOLO con un objeto JSON con esas seis llaves, sin texto adicional."
)
_EXTRA_CERRADA = (
    "\nLa pregunta es de opción múltiple: si los pasajes respaldan una opción distinta de la elegida, o no "
    "permiten decidir entre opciones, repórtalo en afirmaciones_sin_soporte."
)

_SYSTEM_VOTO = (
    "Eres un asistente jurídico colombiano. Responde la pregunta de opción múltiple EXCLUSIVAMENTE con "
    "la información de los PASAJES entregados. No presentes como vigente una norma marcada derogada o "
    "transitoria. Devuelve SOLO un objeto JSON con las llaves, en este orden:\n"
    "1. razon: una o dos oraciones con lo que dicen los pasajes y la opción que respaldan.\n"
    "2. voto: la letra de la opción que tu razón respalda. Elige siempre una letra.\n"
    "3. consulta_sugerida: si los pasajes no bastan para decidir, términos jurídicos y normas que habría "
    "que buscar (vacío si bastan)."
)

_CITA_RE = re.compile(r"\[([a-z0-9_.\-]+(?:/[a-z0-9_.\-~#]+)+)\]", re.I)
_SIN_PARTE_RE = re.compile(r"(/notas)?(#\d+)?$")


def _textos(valor) -> list[str]:
    """Todas las cadenas de un borrador (valores anidados incluidos)."""
    if isinstance(valor, str):
        return [valor]
    if isinstance(valor, dict):
        return [t for v in valor.values() for t in _textos(v)]
    if isinstance(valor, (list, tuple)):
        return [t for v in valor for t in _textos(v)]
    return []


def citas_fuera_de_pasajes(borrador: dict, pasajes: List[CanonicalPassage]) -> list[str]:
    """Determinista, sin LLM: IDs canónicos entre corchetes del borrador que no están en los pasajes.

    Un artículo partido (`…/art_5#2`) o sus notas (`…/art_5/notas`) valen como el artículo."""
    validos = set()
    for p in pasajes:
        validos |= {p.id, _SIN_PARTE_RE.sub("", p.id), p.doc_id}
        if p.metadatos.get("articulo_id"):
            validos.add(p.metadatos["articulo_id"])
    validos = {v.lower() for v in validos}
    fuera = []
    for texto in _textos(borrador):
        for cita in _CITA_RE.findall(texto):
            c = cita.lower()
            if c not in validos and _SIN_PARTE_RE.sub("", c) not in validos and cita not in fuera:
                fuera.append(cita)
    return fuera


def _contexto(state: QuestionState) -> list[str]:
    """Pasajes, pregunta y opciones. No incluye ningún campo de la clave ni el borrador."""
    bloques = [f"[{p.id}] (vigencia: {p.metadatos.get('vigencia', 'desconocida')})\n{texto}"
               for p, texto in zip(state.pasajes_recuperados, textos_para_prompt(state.pasajes_recuperados))]
    partes = [
        f"Área: {state.area} | Tema: {state.tema} | Sub-tarea: {state.sub_tarea}",
        "PASAJES:\n" + ("\n\n".join(bloques) if bloques else "(ninguno)"),
        f"PREGUNTA: {state.pregunta}",
    ]
    if state.opciones:
        partes.append("OPCIONES:\n" + "\n".join(f"{k}. {v}" for k, v in sorted(state.opciones.items())))
    return partes


def build_vote_prompts(state: QuestionState) -> tuple[str, str]:
    """Prompt del voto a ciegas: el juez no ve el borrador del escritor, para no anclarse a su letra."""
    return _SYSTEM_VOTO, "\n\n".join(_contexto(state))


def build_judge_prompts(state: QuestionState) -> tuple[str, str]:
    """Construye (system_prompt, user_prompt). No incluye ningún campo de la clave."""
    system = _SYSTEM + (_EXTRA_CERRADA if state.formato == "multiple_choice" else "")
    partes = _contexto(state)
    borrador = {k: v for k, v in (state.borrador_respuesta or {}).items() if k not in ("formato", "abstencion")}
    lineas = []
    for k, v in borrador.items():
        if isinstance(v, dict):
            v = "; ".join(f"{a}: {b}" for a, b in v.items())
        elif isinstance(v, list):
            v = ", ".join(map(str, v))
        lineas.append(f"{k}: {v}")
    partes.append("BORRADOR:\n" + "\n".join(lineas))
    return system, "\n\n".join(partes)


def _llamar_juez(system: str, user: str, esquema: Optional[dict] = None) -> str:
    """POST al modelo local del juez. Lanza `requests.exceptions.RequestException` si falla."""
    _verificar_host_local(JUDGE_BASE_URL)
    url = f"{JUDGE_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": JUDGE_MODEL,
        "temperature": 0,
        "max_tokens": JUDGE_MAX_TOKENS,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    guiado = {
        "response_format": {"type": "json_schema", "json_schema": {"name": "veredicto", "schema": esquema or _ESQUEMA}},
        "chat_template_kwargs": {"enable_thinking": JUDGE_THINKING},
    }
    resp = requests.post(url, json={**payload, **guiado}, timeout=JUDGE_TIMEOUT)
    if resp.status_code == 400:  # servidor sin salida guiada: se reintenta con el payload mínimo
        resp = requests.post(url, json=payload, timeout=JUDGE_TIMEOUT)
    resp.raise_for_status()
    try:
        return resp.json()["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise requests.exceptions.RequestException(f"Respuesta del servidor con formato inesperado: {e}") from e


def _bool(v) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip().lower() in ("true", "false", "sí", "si", "no", "verdadero", "falso"):
        return v.strip().lower() in ("true", "sí", "si", "verdadero")
    raise ValueError(f"booleano inválido: {v!r}")


def _veredicto_de(datos: dict, citas_invalidas: list[str]) -> Veredicto:
    """Arma el veredicto a partir del JSON del modelo. `aprobado` se decide aquí, no lo decide el modelo."""
    sin_soporte = datos["afirmaciones_sin_soporte"]
    if isinstance(sin_soporte, str):
        sin_soporte = [sin_soporte] if sin_soporte.strip() else []
    sin_soporte = [str(a).strip() for a in sin_soporte if str(a).strip()]
    responde = _bool(datos["responde_sub_tarea"])
    return Veredicto(
        responde_sub_tarea=responde,
        afirmaciones_sin_soporte=sin_soporte,
        pasajes_suficientes=_bool(datos.get("pasajes_suficientes", True)),
        area_coherente=_bool(datos.get("area_coherente", True)),
        feedback=str(datos.get("feedback") or "").strip(),
        consulta_sugerida=str(datos.get("consulta_sugerida") or "").strip(),
        citas_invalidas=citas_invalidas,
        aprobado=responde and not sin_soporte and not citas_invalidas,
        origen="llm",
    )


def _previo(state: QuestionState) -> tuple[Optional[Veredicto], list[str]]:
    """Casos que se resuelven sin LLM y las citas inválidas del borrador."""
    borrador = state.borrador_respuesta or {}
    if state.abstencion or borrador.get("abstencion"):
        # Nada que corregir en una abstención: no hay afirmaciones ni citas que revisar.
        return Veredicto(aprobado=True, origen="determinista", pasajes_suficientes=False,
                         feedback="El escritor se abstuvo."), []
    return None, citas_fuera_de_pasajes(borrador, state.pasajes_recuperados)


def _letra(valor, opciones: dict) -> Optional[str]:
    letra = str(valor or "").strip().upper()[:1]
    return letra if letra in opciones else None


def votar_cerrada(state: QuestionState, citas_invalidas: list[str]) -> Veredicto:
    """Voto a ciegas del juez en una cerrada. Aprueba el borrador si las dos letras coinciden.

    Si discrepan, `consulta_sugerida` guía la nueva búsqueda: la que pide el juez o, si no pide
    ninguna, el texto de las dos opciones en disputa. `pasajes_suficientes` queda en True: una
    discrepancia nunca fuerza la abstención (en una cerrada abstenerse es fallar seguro)."""
    opciones = state.opciones or {}
    letra_escritor = _letra((state.borrador_respuesta or {}).get("respuesta_correcta"), opciones)
    esquema = {
        "type": "object",
        "properties": {"razon": {"type": "string"}, "voto": {"type": "string", "enum": sorted(opciones)},
                       "consulta_sugerida": {"type": "string"}},
        "required": ["razon", "voto", "consulta_sugerida"],
    }
    datos = _parsear_json(_llamar_juez(*build_vote_prompts(state), esquema=esquema))
    voto = _letra(datos["voto"], opciones)
    if voto is None:
        raise ValueError(f"voto inválido: {datos['voto']!r}")
    if voto == letra_escritor:
        return Veredicto(citas_invalidas=citas_invalidas, aprobado=not citas_invalidas, origen="voto", voto=voto,
                         voto_escritor=letra_escritor)
    en_disputa = " ".join(opciones[k] for k in (letra_escritor, voto) if k)
    return Veredicto(
        feedback=f"El juez votó {voto} y el escritor eligió {letra_escritor}: {str(datos.get('razon') or '').strip()}",
        consulta_sugerida=str(datos.get("consulta_sugerida") or "").strip() or en_disputa,
        citas_invalidas=citas_invalidas, aprobado=False, origen="voto", voto=voto, voto_escritor=letra_escritor)


def evaluate_with_judge(state: QuestionState) -> Veredicto:
    """Juzga `state.borrador_respuesta` contra `state.pasajes_recuperados`; en las cerradas, vota.

    `aprobado` es True/False, o None si el juez no pudo decidir (servidor caído o salida que no es
    el JSON esperado); en ese caso el llamador conserva el borrador y no reintenta."""
    veredicto, citas_invalidas = _previo(state)
    if veredicto:
        return veredicto
    if JUDGE_VOTO_CERRADAS and state.formato == "multiple_choice" and state.opciones:
        try:
            return votar_cerrada(state, citas_invalidas)
        except (requests.exceptions.RequestException, ValueError, KeyError, TypeError, AttributeError) as e:
            # Sin segundo voto se entrega la letra del escritor sin contraste: que se note en el log.
            print(f"   AVISO: el juez no votó la pregunta {state.id} ({type(e).__name__}: {e}); "
                  "se conserva la respuesta del escritor", file=sys.stderr, flush=True)
            return Veredicto(citas_invalidas=citas_invalidas, aprobado=None, origen="error",
                             feedback=f"Juez no disponible ({type(e).__name__}: {e})")
    system, user = build_judge_prompts(state)
    try:
        return _veredicto_de(_parsear_json(_llamar_juez(system, user)), citas_invalidas)
    except (requests.exceptions.RequestException, ValueError, KeyError, TypeError, AttributeError) as e:
        return Veredicto(citas_invalidas=citas_invalidas, aprobado=None, origen="error",
                         feedback=f"Juez no disponible ({type(e).__name__}: {e})")


def mock_evaluate_with_judge(state: QuestionState) -> Veredicto:
    """Juez determinista sin LLM (para --mock y pruebas): aprueba si todas las citas están en los
    pasajes y el borrador comparte vocabulario con ellos."""
    veredicto, citas_invalidas = _previo(state)
    if veredicto:
        return veredicto
    tok_borrador = _tokens(" ".join(_textos(state.borrador_respuesta)))
    tok_pasajes = _tokens(" ".join(p.texto for p in state.pasajes_recuperados))
    con_soporte = bool(tok_borrador & tok_pasajes)
    return Veredicto(
        afirmaciones_sin_soporte=[] if con_soporte else ["El borrador no comparte términos con los pasajes."],
        pasajes_suficientes=con_soporte,
        citas_invalidas=citas_invalidas,
        feedback="" if con_soporte and not citas_invalidas else "[MOCK] Citas o contenido sin respaldo en los pasajes.",
        aprobado=con_soporte and not citas_invalidas,
        origen="mock",
    )
