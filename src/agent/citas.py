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


# Meta-texto: frases que hablan de la evidencia en vez de afirmar el derecho. Para RAGAS son
# afirmaciones sobrantes ("los pasajes mencionan…" no está en ninguna respuesta esperada).
_META = re.compile(
    r"\b(?:según|de acuerdo con|conforme a|con base en)\s+(?:lo\s+\w+\s+en\s+)?(?:los|el|la información de los)\s+"
    r"pasajes?(?:\s+(?:proporcionados?|recuperados?|entregados?|consultados?|disponibles?))?"
    # "en los pasajes" solo con calificativo o con "se menciona que": "pasajes" también es una palabra común.
    r"|\b(?:en|de)\s+los\s+pasajes(?:\s+(?:proporcionados|recuperados|entregados|consultados)"
    r"(?:\s*,?\s*se\s+(?:menciona|indica|establece|señala|observa)\s+que)?"
    r"|\s*,?\s*se\s+(?:menciona|indica|establece|señala|observa)\s+que)"
    r"|\blos\s+pasajes(?:\s+(?:proporcionados|recuperados))?\s+(?:mencionan|indican|establecen|señalan|muestran)\s+que"
    r"|\bes\s+importante\s+(?:señalar|destacar|mencionar|resaltar)\s+que",
    re.I)
_CAMPOS_RAGAS = {"semi_open": ("respuesta",), "open_ended": ("marco_normativo", "analisis", "jurisprudencia", "conclusion")}


_META_ENTRE_COMAS = re.compile(r",\s*(?:" + _META.pattern + r")\s*,", re.I)


def _sin_meta_texto(texto: str) -> str:
    if not _META.search(texto):
        return texto   # sin meta-texto no se normaliza nada ("lit. a" no debe volverse "lit. A")
    t = _META_ENTRE_COMAS.sub("", texto)   # "La norma, según los pasajes, exige" -> "La norma exige"
    t = _META.sub("", t)
    t = re.sub(r"\s+,", ",", t)
    t = re.sub(r",\s*,", ",", t)
    t = re.sub(r"(^|[.!?]\s+)[,;:]\s*", r"\1", t)
    t = re.sub(r"[ \t]{2,}", " ", t).strip()
    # Mayúscula al inicio de cada oración que quedó empezando en minúscula.
    return re.sub(r"(^|[.!?]\s+)([a-záéíóúñ])", lambda m: m.group(1) + m.group(2).upper(), t)


def sin_meta_texto(borrador: dict, formato: str) -> dict:
    """Quita el meta-texto de los campos que lee RAGAS."""
    out = dict(borrador)
    for campo in _CAMPOS_RAGAS.get(formato, ()):
        if isinstance(out.get(campo), str):
            out[campo] = _sin_meta_texto(out[campo])
    return out


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
    # Restos de puntuación donde estaban las citas: "servicio., " -> "servicio.", "norma, ." -> "norma."
    texto = re.sub(r"([.;:])(?:\s*[,;])+", r"\1", texto)
    texto = re.sub(r",\s*([.;:])", r"\1", texto).rstrip(" ,;")
    if n:
        texto = " ".join(_ORACION.split(texto)[:n]).strip()
    if len(texto.split()) > MAX_PALABRAS_RESPUESTA:  # máximo oficial (esquema y organizadores)
        texto = _recortar(texto, n or 99, MAX_PALABRAS_RESPUESTA)
    previa = str(borrador.get("referencia_legal") or "").strip()
    nuevas = [c for c in dict.fromkeys(citas) if c not in previa]
    referencia = "; ".join([x for x in [previa.rstrip(".;")] + nuevas if x])
    return {**borrador, "respuesta": texto, "referencia_legal": referencia}


# Abiertas: oraciones máximas por campo. En v6 las 5 abiertas tenían ~480-510 palabras y el juez de
# RAGAS no alcanzó a dar veredicto en ninguna (timeout): cuentan como cero. El esquema pide análisis de
# 5 a 8 oraciones; los demás campos van breves.
# Además, un tope de palabras: en v6 el marco normativo salió como lista "id: … contenido: …" que
# copiaba los pasajes (237 palabras sin un punto). Con ~350 palabras en total (como en v2) el juez sí
# da veredicto.
# Con IRAC (2/oct) el marco normativo abre con el problema jurídico: 100 palabras en vez de 80 (total ≤ 370).
# Con LARGO_OFICIAL (writer_tool) los topes suman 500, el máximo que indicaron los organizadores; ojo: en
# v6, con ~500 palabras, el juez de RAGAS (180 s por llamada en el evaluador oficial) no daba veredicto.
MAX_ORACIONES_ABIERTA = {"marco_normativo": 3, "analisis": 5, "jurisprudencia": 2, "conclusion": 2}
MAX_PALABRAS_ABIERTA = {"marco_normativo": 100, "analisis": 160, "jurisprudencia": 60, "conclusion": 50}
MAX_ORACIONES_ABIERTA_LARGA = {"marco_normativo": 4, "analisis": 8, "jurisprudencia": 3, "conclusion": 3}
MAX_PALABRAS_ABIERTA_LARGA = {"marco_normativo": 130, "analisis": 250, "jurisprudencia": 70, "conclusion": 50}
# Semiabiertas: máximo oficial de palabras de `respuesta` (esquema: "De 3 a 5 oraciones, maximo 150 palabras").
MAX_PALABRAS_RESPUESTA = 150


def _recortar(texto: str, oraciones: int, palabras: int) -> str:
    """Las primeras oraciones que quepan en `palabras`; si ni la primera cabe, sus primeras palabras."""
    elegidas, n = [], 0
    for o in _ORACION.split(texto.strip())[:oraciones]:
        largo = len(o.split())
        if elegidas and n + largo > palabras:
            break
        elegidas.append(o)
        n += largo
    salida = " ".join(elegidas).strip()
    if len(salida.split()) > palabras:
        salida = " ".join(salida.split()[:palabras]).rstrip(",;:") + "…"
    return salida


def abierta_concisa(borrador: dict, largo: bool = False) -> dict:
    """Abiertas: cada campo en sus primeras oraciones y dentro de su tope de palabras (los de LARGO_OFICIAL
    con `largo`). En los dos casos el total queda por debajo de las 500 palabras oficiales."""
    oraciones = MAX_ORACIONES_ABIERTA_LARGA if largo else MAX_ORACIONES_ABIERTA
    palabras = MAX_PALABRAS_ABIERTA_LARGA if largo else MAX_PALABRAS_ABIERTA
    out = dict(borrador)
    for campo, n in oraciones.items():
        texto = str(out.get(campo) or "").strip()
        if texto:
            out[campo] = _recortar(texto, n, palabras[campo])
    return out


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
    if FUENTES_AMPLIADAS:
        lista += fuentes_ampliadas(f"{previo} {lista}", pasajes)
    return {**borrador, campo: f"{previo} {lista}".strip() if previo else lista}


# Fuentes ampliadas (activadas; FUENTES_AMPLIADAS=0 las apaga): además de las normas de los pasajes,
# (1) las sentencias de los pasajes y (2) las leyes, códigos y la Constitución que el texto de los pasajes
# menciona (p. ej. una sentencia que aplica el Código Sustantivo del Trabajo). Todas salen de la evidencia
# recuperada: quedan respaldadas. Decretos, resoluciones y sentencias solo mencionadas no se listan
# (multiplicaban la lista por tres sin agregar ninguna cita de referencia). Simulado sobre v14 sin
# regenerar: citación 16,73 -> 18,37 (45 de 49 cuerpos de referencia) y abstención 8,84 -> 9,07;
# confirmado en la A40 (v16: 44,77/50 sin RAGAS, 0 citas sin respaldo). No entra en el texto de RAGAS.
FUENTES_AMPLIADAS = os.environ.get("FUENTES_AMPLIADAS", "1") == "1"
_NOMBRE_CUERPO = {
    "constitucion": "Constitución Política", "codigo_civil": "Código Civil", "codigo_penal": "Código Penal",
    "codigo_procedimiento_penal": "Código de Procedimiento Penal", "codigo_comercio": "Código de Comercio",
    "codigo_sustantivo_trabajo": "Código Sustantivo del Trabajo", "codigo_procesal_trabajo": "Código Procesal del Trabajo",
    "codigo_general_proceso": "Código General del Proceso",
    "cpaca": "Código de Procedimiento Administrativo y de lo Contencioso Administrativo",
    "estatuto_tributario": "Estatuto Tributario", "codigo_infancia": "Código de la Infancia y la Adolescencia",
    "codigo_nacional_policia": "Código Nacional de Seguridad y Convivencia Ciudadana",
    "codigo_disciplinario": "Código General Disciplinario", "estatuto_consumidor": "Estatuto del Consumidor",
    "decision_andina_486": "Decisión 486 de la Comisión de la Comunidad Andina",
}
_ES_SENTENCIA = ("corte", "consejo", "sentencia", "tribunal", "csj")


def _nombre_cuerpo(cuerpo: tuple) -> str | None:
    tipo, numero, anio = cuerpo
    if tipo in _NOMBRE_CUERPO:
        return _NOMBRE_CUERPO[tipo]
    if tipo == "ley" and numero and anio:
        return f"Ley {numero} de {anio}"
    return None


def fuentes_ampliadas(ya_citado: str, pasajes: List[CanonicalPassage]) -> str:
    """Texto a agregar tras la lista de normas: sentencias de los pasajes y leyes o códigos que mencionan."""
    from src.knowledge.citation_lookup import cuerpos  # extractor de citas del evaluador oficial
    # Las de la CSJ con prefijo csj_ traen un encabezado sin cita reconocible ("Csj sp 24 01 1977"): fuera.
    sentencias = list(dict.fromkeys(nombre_documento(p) for p in pasajes[:10]
                                    if nombre_documento(p).lower().startswith(_ES_SENTENCIA)
                                    and not nombre_documento(p).lower().startswith("csj")))
    vistos = cuerpos(ya_citado) | cuerpos(" ".join(sentencias))
    mencionados = set()
    for p in pasajes[:10]:
        mencionados |= cuerpos(p.texto or "")
    leyes = [n for n in sorted({_nombre_cuerpo(c) for c in mencionados - vistos} - {None})]
    out = ""
    if sentencias:
        out += " Sentencias de los pasajes consultados: " + "; ".join(sentencias) + "."
    if leyes:
        out += " Leyes y códigos mencionados en los pasajes consultados: " + "; ".join(leyes) + "."
    return out
