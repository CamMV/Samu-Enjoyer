"""Subagente de búsqueda de citas: revisa las citas del borrador que no están en los pasajes.

Por cada ID canónico entre corchetes que el escritor citó sin que esté entre los pasajes
recuperados, se busca en el corpus (corpus/chunks/chunks.sqlite):

    existe y está vigente  -> se agrega el pasaje (sustituye al último pasaje que el borrador no
                              cita, para no pasar de 10: el evaluador solo mira 10)
    no existe, está derogada, cita solo el documento, los 10 pasajes ya están citados
    o no hay corpus (--mock) -> la cita se suprime del borrador

Determinista, sin LLM. Al terminar, toda cita del borrador está respaldada por un pasaje. El
texto de las afirmaciones no se toca: lo revisa después el juez, que ya ve los pasajes agregados.
"""
from __future__ import annotations

import re
from typing import Callable, List, Optional

from src.agent.schemas import CanonicalPassage, QuestionState
from src.agent.tools.judge_tool import _SIN_PARTE_RE, _textos, citas_fuera_de_pasajes

MAX_PASAJES = 10
Buscador = Callable[[str], Optional[CanonicalPassage]]


def buscar_cita(cita: str, almacen, articulo_completo: Optional[Callable[[dict], str]] = None
                ) -> Optional[CanonicalPassage]:
    """Pasaje del corpus para un ID canónico, o None si no existe.

    `almacen` es el `Almacen` de src/knowledge/chunk_store.py. Un artículo partido se entrega
    completo (`articulo_completo` = `Recuperador._articulo_completo`), con el ID del artículo."""
    cid = cita.strip().lower()
    if "/" not in cid:  # solo el documento: no se trae una norma entera
        return None
    d = almacen.get([cid]).get(cid)
    texto = d["texto"] if d else ""
    if d is None or d["tipo_chunk"] == "parte_articulo":
        partes = [c for c in almacen.por("articulo_id", _SIN_PARTE_RE.sub("", cid))
                  if c["tipo_chunk"] in ("articulo", "parte_articulo")]
        if not partes:
            return None
        d = partes[0]
        texto = d["texto"]
        if d["tipo_chunk"] == "parte_articulo":
            cid = d["articulo_id"]
            texto = articulo_completo(d) if articulo_completo else "\n\n".join(c["texto"] for c in partes)
    return CanonicalPassage(id=cid, texto=texto, metadatos={
        "doc_id": d["doc_id"], "tipo_chunk": d["tipo_chunk"], "inicio": d.get("inicio"), "fin": d.get("fin"),
        "vigencia": d.get("vigencia"), "derogado": bool(d.get("derogado") or d.get("vigencia") == "derogada"),
        "origen": "busqueda_citas"})


def suprimir_citas(borrador: dict, citas: List[str]) -> dict:
    """Copia del borrador sin los `[id]` de `citas` (en todos sus textos, anidados incluidos)."""
    if not citas:
        return borrador
    patron = re.compile("|".join(r"\[" + re.escape(c) + r"\]" for c in citas), re.I)

    def limpiar(v):
        if isinstance(v, str):
            if not patron.search(v):
                return v
            v = re.sub(r"\(\s*\)", "", patron.sub("", v))
            return re.sub(r"\s+([.,;:])", r"\1", re.sub(r"[ \t]{2,}", " ", v)).strip()
        if isinstance(v, dict):
            return {k: limpiar(x) for k, x in v.items()}
        if isinstance(v, list):
            return [limpiar(x) for x in v]
        return v

    return limpiar(borrador)


def _sin_citar(state: QuestionState) -> Optional[int]:
    """Posición del último pasaje que el borrador no cita (None si los cita todos)."""
    texto = " ".join(_textos(state.borrador_respuesta)).lower()
    for i in range(len(state.pasajes_recuperados) - 1, -1, -1):
        p = state.pasajes_recuperados[i]
        claves = {_SIN_PARTE_RE.sub("", p.id.lower()), str(p.metadatos.get("articulo_id") or p.id).lower()}
        if not any(c in texto for c in claves) and f"[{p.doc_id.lower()}]" not in texto:
            return i
    return None


def resolver_citas(state: QuestionState, buscar: Optional[Buscador] = None) -> List[dict]:
    """Resuelve `state.citas_invalidas`: agrega el pasaje de cada cita que existe en el corpus y
    suprime del borrador las demás. Modifica `state` y devuelve el informe por cita."""
    informe, suprimir = [], []

    def anotar(cita: str, accion: str, motivo: str) -> None:
        informe.append({"cita": cita, "accion": accion, "motivo": motivo})
        if accion == "suprimida":
            suprimir.append(cita)

    for cita in state.citas_invalidas:
        if not citas_fuera_de_pasajes({"cita": f"[{cita}]"}, state.pasajes_recuperados):
            anotar(cita, "agregada", "el pasaje ya se agregó por otra cita del mismo artículo")
            continue
        if "/" not in cita:
            anotar(cita, "suprimida", "cita un documento sin artículo")
            continue
        if buscar is None:
            anotar(cita, "suprimida", "sin corpus donde buscar")
            continue
        pasaje = buscar(cita)
        if pasaje is None:
            anotar(cita, "suprimida", "no existe en el corpus")
        elif pasaje.metadatos.get("derogado"):
            anotar(cita, "suprimida", "la norma está derogada")
        elif len(state.pasajes_recuperados) < MAX_PASAJES:
            state.pasajes_recuperados.append(pasaje)
            anotar(cita, "agregada", "existe en el corpus")
        elif (i := _sin_citar(state)) is not None:
            anotar(cita, "agregada", f"existe en el corpus; sustituye a {state.pasajes_recuperados[i].id}")
            state.pasajes_recuperados[i] = pasaje
        else:
            anotar(cita, "suprimida", f"los {MAX_PASAJES} pasajes ya están citados")

    borrador = suprimir_citas(state.borrador_respuesta or {}, suprimir)
    # Garantía: lo que aún no tenga pasaje (p. ej. un ID agregado con otra forma) también se quita.
    state.borrador_respuesta = suprimir_citas(borrador, citas_fuera_de_pasajes(borrador, state.pasajes_recuperados))
    return informe
