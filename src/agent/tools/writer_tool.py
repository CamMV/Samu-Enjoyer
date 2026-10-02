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

from src.agent.salida import _letra
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
    "transitoria. Afirma el contenido jurídico de forma directa: nunca hables de los pasajes ni del "
    "contexto (nada de 'según los pasajes', 'los pasajes mencionan', 'es importante señalar'). "
    "Si los pasajes no bastan para responder, devuelve {\"abstencion\": true}. "
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
    # RAGAS cuenta como error toda afirmación que no esté en la respuesta esperada, aunque sea cierta:
    # respuestas cortas y directas, sin describir los pasajes (ver src/agent/citas.py).
    "semi_open": (
        'Devuelve JSON con las llaves: "respuesta" (exactamente 3 oraciones breves, máximo 70 palabras: '
        'la PRIMERA responde directamente la pregunta —sí o no, la norma, la autoridad, la definición, el '
        'plazo o el sentido del fallo—; las otras dos dan solo el fundamento esencial, citando IDs '
        'canónicos; nada que la pregunta no pida), "palabras_clave" (lista de strings), "referencia_legal" '
        '(IDs/normas citadas), "abstencion" (boolean).'
    ),
    "open_ended": (
        'Devuelve JSON con las llaves, todas de tipo texto corrido (nunca listas ni objetos): '
        '"marco_normativo" (máximo 3 oraciones: qué normas aplican, con su ID canónico, y qué establecen '
        'para el caso; no copies el texto de los pasajes ni los describas), "analisis" (5 oraciones que '
        'aplican esas normas a los hechos del caso, citando IDs canónicos), "jurisprudencia" (máximo 2 '
        'oraciones: las sentencias de los pasajes que aplican y la regla que fijan; si no hay, escribe '
        '"No se identificó jurisprudencia aplicable en el corpus."), "conclusion" (una o dos oraciones que '
        'responden directamente la pregunta), "abstencion" (boolean). En total, menos de 300 palabras.'
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


# --- Calculadora de montos (determinista, sin LLM) ----------------------------------------
# Los umbrales legales (cuantías, multas, topes) están en salarios mínimos y las preguntas dan pesos.
# Un modelo de 8B hace bien la división pero compara mal (pregunta 528: calcula 21,07 smlmv y elige
# "mayor cuantía", que exige más de 150). El sistema hace la aritmética y la comparación con los
# umbrales que traen los pasajes, y se la entrega al modelo como dato.
_MONTO_RE = re.compile(r"\$\s*(\d{1,3}(?:[.,]\d{3}){2,})|\b(\d{1,3}(?:[.,]\d{3}){2,})\s*(?:COP|pesos)\b", re.I)
_SMLMV_RE = re.compile(r"salario m[ií]nimo (?:legal )?mensual(?: legal)?(?: vigente)? para el año (\d{4})"
                       r".{0,400}?\(\s*\$\s*(\d{1,3}(?:\.\d{3})+)", re.I | re.S)
_UMBRAL_RE = re.compile(r"\(\s*(\d{1,5})\s*smm?lmv\s*\)|\b(\d{1,5})\s*salarios? m[ií]nimos?", re.I)


def _entero(txt: str) -> int:
    return int(re.sub(r"[.,]", "", txt))


def _num(x: float) -> str:
    return f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def datos_calculados(pregunta: str, pasajes: list[CanonicalPassage]) -> str:
    """Si la pregunta trae un monto en pesos y un pasaje fija el salario mínimo, el monto en salarios
    mínimos y su comparación con cada umbral en salarios mínimos que aparezca en los pasajes."""
    montos = [_entero(a or b) for a, b in _MONTO_RE.findall(pregunta or "")]
    smlmv = None
    for p in pasajes:
        m = _SMLMV_RE.search(p.texto or "")
        if m:
            smlmv = (int(m.group(1)), _entero(m.group(2)), p.id)
            break
    if not montos or not smlmv:
        return ""
    umbrales = sorted({int(a or b) for p in pasajes for a, b in _UMBRAL_RE.findall(p.texto or "")} - {0})
    anio, valor, fuente = smlmv
    lineas = []
    pesos = lambda x: f"${x:,}".replace(",", ".")  # noqa: E731
    for monto in sorted(set(montos)):
        n = monto / valor
        lineas.append(f"- {pesos(monto)} equivalen a {_num(n)} salarios mínimos mensuales "
                      f"(salario mínimo de {anio}: {pesos(valor)}, según [{fuente}]).")
        lineas += [f"  {_num(n)} {'EXCEDE' if n > u else 'NO EXCEDE'} {u} salarios mínimos." for u in umbrales]
    return "DATOS CALCULADOS POR EL SISTEMA (aritmética exacta; úsalos tal cual):\n" + "\n".join(lineas)


# --- Primera oración según la sub-tarea (semiabiertas) -------------------------------------------
# RAGAS premia que la respuesta contenga las afirmaciones de la esperada y castiga las que sobran. La
# primera oración debe dar exactamente lo que la sub-tarea pide, en la forma en que se pregunta. Las
# sub-tareas son el catálogo público del banco (enunciado, sección 4.2): sirve igual en el test.
_GUIA_SUBTAREA = (
    (r"existencia normativa", "di si existe (sí o no) y nombra la norma que lo regula (tipo, número y año)"),
    (r"autoridad competente", "nombra la autoridad competente"),
    (r"juez que decide", "nombra el juez o tribunal que decide"),
    (r"jerarqu", "ubica la norma o el acto en la jerarquía normativa (qué rango tiene y frente a qué)"),
    (r"definici", "define el concepto: '<concepto> es …'"),
    (r"clasificaci", "di en qué categoría jurídica encaja: '<figura> es un/una …'"),
    (r"elementos? esencial", "enumera los elementos esenciales"),
    (r"sentido del fallo", "di qué decidió el tribunal (p. ej. declaró exequible o inexequible, concedió o negó)"),
    (r"reproducci", "reproduce entre comillas el texto de la norma tal como aparece en el pasaje"),
    (r"precedente", "nombra la sentencia y la regla que fija"),
    (r"vigencia", "di si la norma está vigente y desde o hasta cuándo"),
    (r"distinci", "di la diferencia principal entre los conceptos"),
    (r"requisito", "enumera los requisitos legales"),
    (r"excepci", "enumera las excepciones legales"),
    (r"imparcialidad", "di si se garantiza o se afecta la imparcialidad y por qué"),
    (r"conflicto normativo", "di qué norma prevalece y con qué criterio (jerarquía, especialidad o temporalidad)"),
    (r"f[aá]ctic", "resume los hechos jurídicamente relevantes"),
    (r"postura procesal", "di qué posición o actuación procesal procede"),
    (r"problema jur", "responde de forma directa la cuestión jurídica planteada con su conclusión"),
    (r"fundamento jur|ratio", "di la razón central de la decisión (ratio decidendi)"),
    (r"ponderaci", "di qué principio o derecho prevalece en el caso y por qué"),
    (r"interpretaci", "di qué resulta de leer las normas en conjunto"),
)
_VERDADERO_FALSO = re.compile(r"\b(falsa|falso)\s+o\s+verdader|\bverdader[ao]\s+o\s+fals", re.I)


# Oraciones 2 y 3 de las semiabiertas (ORACIONES_SUSTANTIVAS=1; apagado mientras se mide). RAGAS divide la
# respuesta en afirmaciones y cuenta como error cada una que la esperada no trae: con "el fundamento
# esencial" el modelo agrega normas y contexto. En la prueba del 1/oct sobre v2 (mismas respuestas
# recortadas), las de complejidad baja daban 0,465 con 1 oración y 0,383 con 3; el esquema exige 3.
ORACIONES_SUSTANTIVAS = os.environ.get("ORACIONES_SUSTANTIVAS", "0") == "1"

# Ejemplos de estilo (EJEMPLOS_ESTILO=1; apagado mientras se mide): pares pregunta/respuesta esperada de la
# muestra pública (data/sample_50.jsonl), nunca la misma pregunta: 2 en semiabiertas (primero de la misma
# sub-tarea) y 1 en abiertas. Muestran la extensión y el nivel de detalle que se espera; el prompt prohíbe
# usar su contenido. Determinista.
EJEMPLOS_ESTILO = os.environ.get("EJEMPLOS_ESTILO", "0") == "1"
_MUESTRA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "data", "sample_50.jsonl")
_muestra_cache: Optional[list] = None


def _muestra() -> list:
    global _muestra_cache
    if _muestra_cache is None:
        try:
            with open(_MUESTRA, encoding="utf-8") as f:
                _muestra_cache = [json.loads(l) for l in f if l.strip()]
        except OSError:
            _muestra_cache = []
    return _muestra_cache


def ejemplos_de_estilo(pregunta: str, flags: dict) -> str:
    formato = flags.get("formato")
    if not EJEMPLOS_ESTILO or formato not in ("semi_open", "open_ended"):
        return ""
    propia = re.sub(r"\s+", " ", pregunta or "").strip()
    candidatos = [it for it in _muestra() if it.get("formato") == formato and it.get("respuesta_esperada")
                  and re.sub(r"\s+", " ", it.get("pregunta") or "").strip() != propia]
    if formato == "semi_open":
        sub = flags.get("sub_tarea")
        candidatos.sort(key=lambda it: (it.get("sub_tarea") != sub, it["id"]))
        elegidos = candidatos[:2]
    else:  # abiertas: la de respuesta esperada más corta, para no alargar el prompt
        elegidos = sorted(candidatos, key=lambda it: (len(it["respuesta_esperada"]), it["id"]))[:1]
    if not elegidos:
        return ""
    bloques = [f"Pregunta: {it['pregunta'].strip()}\nRespuesta esperada: {it['respuesta_esperada'].strip()}"
               for it in elegidos]
    return ("EJEMPLOS DE ESTILO (otras preguntas, con la respuesta que espera el evaluador; muestran la extensión, "
            "lo directo y el nivel de detalle. NO uses su contenido, sus normas ni sus sentencias: tu respuesta "
            "sale solo de los PASAJES):\n\n" + "\n\n".join(bloques))


def guia_primera_oracion(pregunta: str, sub_tarea: Optional[str]) -> str:
    """Instrucción para la primera oración de una semiabierta, según la pregunta y su sub-tarea."""
    if _VERDADERO_FALSO.search(pregunta or ""):
        guia = "empieza con 'La afirmación es verdadera' o 'La afirmación es falsa' y da la razón"
    else:
        sub = (sub_tarea or "").lower()
        guia = next((g for rx, g in _GUIA_SUBTAREA if re.search(rx, sub)),
                    "responde directamente lo que se pregunta")
    siguientes = ("Las dos oraciones siguientes completan la respuesta con el contenido sustantivo que la pregunta "
                  "pide (requisitos, condiciones, efectos, excepciones o la razón jurídica); sin contexto, antecedentes, "
                  "fechas ni normas que no respondan la pregunta." if ORACIONES_SUSTANTIVAS
                  else "Las dos oraciones siguientes, solo el fundamento esencial.")
    return (f"PRIMERA ORACIÓN (sub-tarea: {sub_tarea or 'sin dato'}): {guia}, retomando los términos de la "
            f"pregunta. {siguientes}")


# Largo de las semiabiertas según la complejidad del ítem (LARGO_COMPLEJIDAD=1; apagado mientras se mide).
# En la muestra, la respuesta esperada tiene una mediana de 116 palabras en complejidad alta, 66 en media
# y 32 en baja; con 3 oraciones respondemos ~40 en todas, y en alta el RAGAS medio era 0,357 contra 0,547
# en baja y 0,644 en media (v8sj): faltan afirmaciones de la esperada. Baja queda como está.
LARGO_COMPLEJIDAD = os.environ.get("LARGO_COMPLEJIDAD", "0") == "1"
_EXTENSION = {
    "alta": (5, 120, "después de la primera, la regla jurídica, las normas o sentencias que la fundamentan, "
                     "sus requisitos o excepciones relevantes y su aplicación a lo que se pregunta"),
    "media": (4, 80, "después de la primera, la regla jurídica, su fundamento y su aplicación a lo que se pregunta"),
}


def nivel_complejidad(complejidad: Optional[str]) -> str:
    c = (complejidad or "").strip().lower()
    return {"high": "alta", "medium": "media", "low": "baja"}.get(c, c)


def oraciones_semiabierta(complejidad: Optional[str]) -> Optional[int]:
    """Oraciones de `respuesta` para `respuesta_concisa` (None = el valor por defecto)."""
    if not LARGO_COMPLEJIDAD or nivel_complejidad(complejidad) not in _EXTENSION:
        return None
    return _EXTENSION[nivel_complejidad(complejidad)][0]


def extension_por_complejidad(complejidad: Optional[str]) -> str:
    if not LARGO_COMPLEJIDAD or nivel_complejidad(complejidad) not in _EXTENSION:
        return ""
    n, palabras, contenido = _EXTENSION[nivel_complejidad(complejidad)]
    return (f"EXTENSIÓN (prevalece sobre la indicada arriba; pregunta de complejidad {nivel_complejidad(complejidad)}): "
            f"\"respuesta\" de exactamente {n} oraciones, máximo {palabras} palabras; {contenido}. Nada que la "
            "pregunta no pida.")


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
    calculo = datos_calculados(pregunta, pasajes)
    if calculo:
        partes.insert(-1, calculo)
    ejemplos = ejemplos_de_estilo(pregunta, flags)
    if ejemplos:
        partes.insert(-1, ejemplos)
    if flags.get("formato") == "semi_open":
        partes.append(guia_primera_oracion(pregunta, flags.get("sub_tarea")))
        extension = extension_por_complejidad(flags.get("complejidad"))
        if extension:
            partes.append(extension)
    if opciones:
        partes.append("OPCIONES:\n" + "\n".join(f"{k}. {v}" for k, v in sorted(opciones.items())))
    return system, "\n\n".join(partes)


def _verificar_host_local(base_url: str) -> None:
    host = (urlparse(base_url).hostname or "").lower()
    if any(p in host for p in _HOSTS_PROHIBIDOS):
        raise ValueError(f"LLM_BASE_URL apunta a un proveedor cerrado prohibido: {host}")


# Modo de razonamiento de Qwen3 (PENSAR=1; apagado mientras se mide). Se había descartado porque el portátil
# (CPU, ~2 tokens/s) no podía reproducirlo en la verificación en vivo; con una GPU de 32 GB sí. Ataca los
# errores de razonamiento con los pasajes correctos (453, 563, 1065 en v14).
PENSAR = os.environ.get("PENSAR", "0") == "1"
PENSAR_MAX_TOKENS = int(os.environ.get("PENSAR_MAX_TOKENS", "6000"))


def _llamar_llm(system: str, user: str, esquema: Optional[dict] = None) -> str:
    """POST al Qwen3-8B local (modelo abierto). Lanza `requests.exceptions.RequestException`
    si falla la conexión, hay timeout o el servidor responde con error HTTP.

    Sin modo de razonamiento: con él las cerradas tardarían minutos más en el portátil (CPU,
    ~2 tokens/s) y la verificación en vivo no reproduciría las respuestas de la A40."""
    _verificar_host_local(LLM_BASE_URL)
    pensar = PENSAR and not esquema  # el paso de la letra (gramática) va siempre sin razonamiento
    payload = {
        "model": LLM_MODEL,
        "temperature": 0,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "chat_template_kwargs": {"enable_thinking": pensar},  # Qwen3: con o sin bloque <think>
        # Sin caché de prompts: llama-server reutiliza por defecto el prefijo común con la petición anterior
        # (el system prompt) y solo calcula el resto, así que la salida dependía de qué pregunta se procesó
        # antes. Con el mismo código y los mismos pasajes, dos corridas de las 50 dieron 0/50 respuestas
        # idénticas (42,90 contra 38,96 de 50). Cada pregunta se calcula siempre completa: reproducible.
        "cache_prompt": False,
    }
    if pensar:
        # Con decodificación codiciosa el razonamiento puede repetirse sin fin: tope de tokens y una
        # penalización de presencia leve (llama.cpp la aplica sobre los últimos 64 tokens; determinista).
        payload["max_tokens"] = PENSAR_MAX_TOKENS
        payload["presence_penalty"] = 1.5
    if esquema:  # salida guiada por gramática (llama.cpp): el JSON y sus valores quedan acotados
        payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "salida", "schema": esquema}}
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


def cerrada_de_respaldo(pasajes: list[CanonicalPassage], opciones: dict) -> dict:
    """Cerrada cuando el LLM falla: la opción con más respaldo léxico en los pasajes (el criterio del escritor
    simulado), con una justificación que cita el pasaje principal. Una cerrada sin letra vale 0 seguro y el
    esquema la rechaza (en v19 la 58 quedó así: el razonamiento llegó al tope de tokens sin cerrar el JSON)."""
    tok_p = _tokens(" ".join(p.texto for p in pasajes))
    puntajes = {k: len(_tokens(v) & tok_p) / (len(_tokens(v)) or 1) for k, v in opciones.items()}
    letra = max(sorted(puntajes), key=lambda k: puntajes[k])
    return {
        "formato": "multiple_choice", "abstencion": False, "respuesta_correcta": letra,
        "justificacion": f"La opción {letra} es la que tiene mayor respaldo en los pasajes consultados, en especial "
                         f"[{pasajes[0].id}].",
        "descarte_opciones": {k: "Tiene menor respaldo en los pasajes consultados." for k in sorted(opciones) if k != letra},
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
    cerrada = formato == "multiple_choice" and bool(opciones)
    try:
        salida = _llamar_llm(system, user)
    except requests.exceptions.RequestException as e:  # conexión caída, timeout, HTTP error
        print(f"   AVISO: el LLM no respondió ({type(e).__name__}: {e}); "
              + ("cerrada con la opción de más respaldo léxico" if cerrada else "la pregunta queda en abstención"),
              file=sys.stderr, flush=True)
        return cerrada_de_respaldo(pasajes, opciones) if cerrada else _abstencion(formato)
    try:
        borrador = _parsear_json(salida)
    except ValueError:  # JSON inválido (p. ej. el razonamiento llegó al tope de tokens sin cerrar el JSON)
        if cerrada:
            print("   AVISO: salida sin JSON; cerrada con la opción de más respaldo léxico", file=sys.stderr, flush=True)
            return cerrada_de_respaldo(pasajes, opciones)
        return _abstencion(formato)
    borrador["formato"] = formato
    borrador["abstencion"] = bool(borrador.get("abstencion", False))
    if formato == "multiple_choice" and opciones:
        # La letra se interpreta con el mismo criterio que la entrega (salida._letra). Antes bastaba el primer
        # carácter: "Código General del Proceso" pasaba como "C" aquí y la entrega la dejaba vacía (v19, la 58).
        borrador["respuesta_correcta"] = _letra(borrador.get("respuesta_correcta"), opciones)
        # Una cerrada con letra válida se responde aunque el modelo marque abstención (ver graph.finalizar).
        letra = str(borrador.get("respuesta_correcta") or "").strip().upper()[:1]
        if borrador["abstencion"] and letra in opciones:
            borrador["abstencion"] = False
        if ELEGIR_LETRA and (not borrador["abstencion"] or borrador.get("justificacion")):
            borrador = con_letra_de_la_justificacion(borrador, opciones)
            if str(borrador.get("respuesta_correcta") or "").strip().upper()[:1] in opciones:
                borrador["abstencion"] = False
        # Respaldo: una cerrada sin letra vale 0 seguro (y el esquema la rechaza). Si ni el escritor ni el
        # verificador dieron una letra válida, se elige la opción con más respaldo léxico en los pasajes
        # (el mismo criterio del escritor simulado), determinista. No cambia ningún prompt: solo actúa
        # cuando falta la letra (pasó en una variante de prueba con la 748).
        if str(borrador.get("respuesta_correcta") or "").strip().upper()[:1] not in opciones:
            respaldo = mock_write_legal_response(pregunta, flags, pasajes, opciones)["respuesta_correcta"]
            print(f"   AVISO: cerrada sin letra; se usa la de más respaldo léxico ({respaldo})", file=sys.stderr, flush=True)
            borrador = {**borrador, "respuesta_correcta": respaldo, "abstencion": False}
    return borrador


# --- Elección de la letra en un paso aparte (cerradas) ------------------------------------
# El 8B razona bien y luego anuncia otra letra (58: concluye "la Ley 1564 de 2012" y elige la D, Ley
# 906; 528: escribe "no corresponde a mayor cuantía" y elige mayor cuantía). Un segundo llamado al
# mismo modelo lee solo el razonamiento, sin las frases que anuncian una letra, y devuelve la opción
# que ese razonamiento respalda, con la salida acotada a las letras válidas. Temperatura 0: determinista.
ELEGIR_LETRA = os.environ.get("ELEGIR_LETRA", "1") != "0"
# Sin re.I: las letras de opción van en mayúscula; con re.I "es a" o "opción … a" atraparían frases normales.
_ANUNCIA_LETRA = re.compile(r"\b[Oo]pci[oó]n(?:es)?\b[^.]*?\b[A-H]\b|\b(?:la|es)\s+[A-H]\b(?![\w.])|\b[A-H]\)")
_SYSTEM_LETRA = (
    "Eres un verificador. Recibes el RAZONAMIENTO de una respuesta a una pregunta de opción múltiple y las "
    "OPCIONES. Básate solo en el razonamiento, no en conocimiento propio. Devuelve SOLO un objeto JSON con "
    "las llaves, en este orden: \"conclusion\" (una oración: qué responde el razonamiento a la pregunta) y "
    "\"letra\" (la opción cuyo contenido coincide con esa conclusión). Si una opción nombra la misma norma "
    "que el razonamiento con otro año (error de digitación), cuenta como coincidencia."
)

# Tolerancia a un año errado en las opciones (TOLERAR_ANIO=0 la quita, para medir). Salió de la 58, cuya
# clave dice "Ley 1564 de 2002" (el CGP es de 2012); en el test podría confundir opciones que solo
# difieren en el año.
TOLERAR_ANIO = os.environ.get("TOLERAR_ANIO", "1") == "1"
if not TOLERAR_ANIO:
    _FORMATO_INSTRUCCIONES["multiple_choice"] = _FORMATO_INSTRUCCIONES["multiple_choice"].replace(
        "Si una opción nombra una norma con el número correcto pero otro año (error de digitación), identifícala "
        "por su número y por el nombre que trae el encabezado del pasaje. ", "")
    _SYSTEM_LETRA = _SYSTEM_LETRA.replace(
        " Si una opción nombra la misma norma que el razonamiento con otro año (error de digitación), cuenta "
        "como coincidencia.", "")


def _sin_anuncios(texto: str) -> str:
    frases = re.split(r"(?<=[.;])\s+", texto or "")
    return " ".join(f for f in frases if not _ANUNCIA_LETRA.search(f)).strip()


def con_letra_de_la_justificacion(borrador: dict, opciones: dict) -> dict:
    """Corrige `respuesta_correcta` con la letra que respalda el razonamiento de la justificación.
    Si el segundo llamado falla, o el razonamiento queda vacío, el borrador no cambia."""
    letras = sorted(opciones)
    razonamiento = _sin_anuncios(str(borrador.get("justificacion") or ""))
    if not razonamiento:
        return borrador
    user = (f"RAZONAMIENTO:\n{razonamiento}\n\nOPCIONES:\n"
            + "\n".join(f"{k}. {v}" for k, v in sorted(opciones.items())))
    esquema = {"type": "object", "properties": {"conclusion": {"type": "string"},
                                                "letra": {"type": "string", "enum": letras}},
               "required": ["conclusion", "letra"]}
    try:
        letra = str(_parsear_json(_llamar_llm(_SYSTEM_LETRA, user, esquema)).get("letra", "")).strip().upper()[:1]
    except (requests.exceptions.RequestException, ValueError, AttributeError):
        return borrador
    anterior = str(borrador.get("respuesta_correcta") or "").strip().upper()[:1]
    if letra not in opciones or letra == anterior:
        return borrador
    print(f"   letra corregida por el razonamiento: {anterior or '-'} -> {letra}", file=sys.stderr, flush=True)
    descartes = {k: v for k, v in (borrador.get("descarte_opciones") or {}).items() if k != letra}
    return {**borrador, "respuesta_correcta": letra, "descarte_opciones": descartes,
            "justificacion": f"{razonamiento} Por lo tanto, la opción correcta es la {letra}."}
