"""Flujo del agente como grafo de LangGraph (diagrama "Arquitectura del sistema" del README).

    entrada -> consulta_cerrada | reescribir_consulta -> recuperar -> escribir -> validar_fuentes
            (-> buscar_citas -> validar_fuentes, si hay citas fuera de los pasajes)
            -> juzgar -> (rechaza y queda ciclo) reescribir_consulta | finalizar

Si el juez rechaza el primer borrador, se vuelve a recuperar con la consulta ajustada por su
feedback y se redacta de nuevo con los pasajes nuevos. La pregunta que ve el escritor no cambia:
solo cambia la evidencia. Máximo 2 ciclos por pregunta.

En las cerradas el juez vota a ciegas en vez de revisar (`judge_tool.votar_cerrada`): rechaza cuando
su letra no coincide con la del escritor. Si tras el segundo ciclo siguen sin coincidir, se entrega
un borrador del escritor (letra y justificación del mismo modelo; el del ciclo más reciente salvo
que tenga más citas fuera de los pasajes).

El grafo se compila sin checkpointer (la memoria se reinicia en cada pregunta) y sin ramas
paralelas: la ejecución es secuencial y determinista.

    python -m src.agent.graph      # imprime el grafo en Mermaid

Configuración por entorno o .env:
    JUDGE_ABSTENER  0 desactiva la abstención forzada cuando el juez declara, en todos los
                    ciclos, que los pasajes no bastan (default 1)
"""
from __future__ import annotations

import os
from typing import Any, Callable, List, Optional, TypedDict

# langchain-core trae langsmith: el trazado remoto queda apagado siempre (por regla del reto
# ninguna llamada puede salir a un servicio de terceros).
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from langgraph.graph import END, START, StateGraph  # noqa: E402

from src.agent.schemas import CanonicalPassage, QuestionState  # noqa: E402
from src.agent.tools.citation_search_tool import resolver_citas  # noqa: E402
from src.agent.tools.flags_tool import extract_query_flags  # noqa: E402
from src.agent.tools.judge_tool import (Veredicto, citas_fuera_de_pasajes, evaluate_with_judge,  # noqa: E402
                                        mock_evaluate_with_judge)
from src.agent.tools.expansion_tool import expandir_consulta  # noqa: E402
from src.agent.tools.writer_tool import _abstencion, mock_write_legal_response, write_legal_response  # noqa: E402

JUDGE_ABSTENER = os.environ.get("JUDGE_ABSTENER", "1") != "0"

Juez = Callable[[QuestionState], Veredicto]
_FLAG_KEYS = ("area", "sub_tarea", "complejidad", "tema", "formato")


class EstadoGrafo(TypedDict, total=False):
    """Memoria de corto plazo de una pregunta."""

    # --- Entrada ---
    raw_item: dict
    pasajes: Optional[List[CanonicalPassage]]  # inyectados: tienen prioridad sobre el retriever
    mock_escritor: Optional[bool]  # None = el del agente
    juez: Optional[Juez]
    # --- Ciclo ---
    state: QuestionState
    consulta: str
    consultas: List[str]
    intentos: List[tuple]  # (QuestionState, Veredicto) por ciclo
    misma_evidencia: bool
    citas_buscadas: bool  # el subagente de citas ya revisó el borrador actual
    # --- Salida ---
    traza: Optional[dict]


def estado_inicial(raw_item: dict) -> QuestionState:
    flags = extract_query_flags(raw_item)
    return QuestionState(
        id=raw_item["id"],
        pregunta=raw_item["pregunta"],
        opciones=raw_item.get("opciones"),
        legal_basis=raw_item.get("legal_basis"),
        respuesta_correcta=raw_item.get("respuesta_correcta"),
        texto_respuesta_correcta=raw_item.get("texto_respuesta_correcta"),
        **flags,
    )


def _consulta_ajustada(state: QuestionState, veredicto: Veredicto) -> str:
    extra = veredicto.consulta_sugerida or veredicto.feedback
    return f"{state.pregunta}\n{extra}".strip()


def _anotar(state: QuestionState, veredicto: Veredicto, ciclo: int, consultas: list[str]) -> None:
    state.ciclo_actual = ciclo
    state.queries_generadas = list(consultas)
    state.aprobado_por_juez = veredicto.aprobado
    state.juez_feedback = veredicto.feedback or None
    state.citas_invalidas = list(veredicto.citas_invalidas)


def construir_grafo(agente: Any, con_juez: bool = False):
    """Compila el grafo para `agente` (se leen `agente.retriever`, `agente.forzar_mock_escritor` y
    `agente.buscador_citas`).

    Sin `con_juez` el flujo termina tras la validación determinista de fuentes."""

    def entrada(s: EstadoGrafo) -> dict:
        return {"state": estado_inicial(s["raw_item"]), "consultas": [], "intentos": [], "misma_evidencia": False,
                "citas_buscadas": False, "traza": None}

    def ruta_formato(s: EstadoGrafo) -> str:
        return "consulta_cerrada" if s["state"].formato == "multiple_choice" else "reescribir_consulta"

    def consulta_cerrada(s: EstadoGrafo) -> dict:
        # Pregunta + opciones A-D, sin LLM: las opciones las añade el retriever (`consulta_de`).
        return {"consulta": s["state"].pregunta}

    def reescribir_consulta(s: EstadoGrafo) -> dict:
        # Ciclo 1: la pregunta tal cual, más la expansión (figuras y normas candidatas) que solo usa la
        # búsqueda; el escritor ve la pregunta original. Ciclo 2: ajustada con el feedback del juez.
        if not s["intentos"]:
            state = s["state"]
            mock = agente.forzar_mock_escritor if s.get("mock_escritor") is None else s["mock_escritor"]
            if not mock and agente.retriever is not None and not state.expansion:
                flags = {k: getattr(state, k) for k in _FLAG_KEYS}
                state.expansion = expandir_consulta(state.pregunta, flags)
            return {"state": state, "consulta": state.pregunta}
        state, veredicto = s["intentos"][-1]
        return {"consulta": _consulta_ajustada(state, veredicto)}

    def recuperar(s: EstadoGrafo) -> dict:
        state = s["state"]
        if not s["intentos"]:
            pasajes = s.get("pasajes")
            if pasajes is None:
                pasajes = agente.retriever(state) if agente.retriever else []
            state.pasajes_recuperados = pasajes[:10]
            return {"consultas": [state.pregunta]}
        pasajes = agente.retriever(state.model_copy(update={"pregunta": s["consulta"]}))[:10]
        if [p.id for p in pasajes] == [p.id for p in state.pasajes_recuperados]:
            return {"misma_evidencia": True}  # con temperature=0 el escritor repetiría el borrador
        # Estado nuevo: el del ciclo anterior queda intacto en `intentos` por si resulta el elegido.
        nuevo = estado_inicial(s["raw_item"])
        nuevo.pasajes_recuperados = pasajes
        return {"state": nuevo, "consultas": s["consultas"] + [s["consulta"]]}

    def ruta_evidencia(s: EstadoGrafo) -> str:
        return "finalizar" if s["misma_evidencia"] else "escribir"

    def escribir(s: EstadoGrafo) -> dict:
        state = s["state"]
        flags = {k: getattr(state, k) for k in _FLAG_KEYS}
        mock = agente.forzar_mock_escritor if s.get("mock_escritor") is None else s["mock_escritor"]
        redactar = mock_write_legal_response if mock else write_legal_response
        state.borrador_respuesta = redactar(state.pregunta, flags, state.pasajes_recuperados, state.opciones)
        state.abstencion = bool(state.borrador_respuesta.get("abstencion", False))
        return {"state": state, "citas_buscadas": False}

    def validar_fuentes(s: EstadoGrafo) -> dict:
        # Determinista, sin LLM: citas del borrador que no están en los pasajes recuperados.
        state = s["state"]
        state.citas_invalidas = citas_fuera_de_pasajes(state.borrador_respuesta or {}, state.pasajes_recuperados)
        return {"state": state}

    def ruta_citas(s: EstadoGrafo) -> str:
        if s["state"].citas_invalidas and not s["citas_buscadas"]:
            return "buscar_citas"
        return "juzgar" if con_juez else "finalizar"

    def buscar_citas(s: EstadoGrafo) -> dict:
        # Subagente de búsqueda: la cita que existe en el corpus trae su pasaje; la que no, se suprime.
        state = s["state"]
        state.busqueda_citas = resolver_citas(state, getattr(agente, "buscador_citas", None))
        return {"state": state, "citas_buscadas": True}

    def juzgar(s: EstadoGrafo) -> dict:
        state = s["state"]
        veredicto = (s.get("juez") or evaluate_with_judge)(state)
        _anotar(state, veredicto, len(s["intentos"]) + 1, s["consultas"])
        return {"state": state, "intentos": s["intentos"] + [(state, veredicto)]}

    def ruta_veredicto(s: EstadoGrafo) -> str:
        state, veredicto = s["intentos"][-1]
        if veredicto.aprobado is not False or len(s["intentos"]) >= state.max_ciclos or agente.retriever is None:
            return "finalizar"
        return "reescribir_consulta"

    def finalizar(s: EstadoGrafo) -> dict:
        intentos = s["intentos"]
        if not intentos:  # sin juez: se entrega el borrador tal cual
            return {}
        # Sin aprobación se entrega el borrador con menos problemas (en empate, el más reciente).
        state, veredicto = next(((e, v) for e, v in intentos if v.aprobado is not False),
                                min(reversed(intentos), key=lambda ev: ev[1].problemas))
        # Las cerradas nunca se abstienen por el juez: el esquema exige una letra y responder rinde más
        # (acierto 1, abstención 0,5, error 0, y la abstención vale 0 en exactitud). En la 58 la letra
        # era la correcta y la abstención forzada la anulaba.
        abstencion_forzada = (JUDGE_ABSTENER and not state.abstencion and state.formato != "multiple_choice"
                              and all(v.aprobado is False and not v.pasajes_suficientes for _, v in intentos))
        if abstencion_forzada:
            state.borrador_respuesta = _abstencion(state.formato)
            state.abstencion = True
        traza = {
            "id": state.id,
            "formato": state.formato,
            "ciclos": len(intentos),
            "ciclo_elegido": state.ciclo_actual,
            "aprobado": veredicto.aprobado,
            "abstencion_forzada": abstencion_forzada,
            "consultas": s["consultas"],
            "citas": state.busqueda_citas,
            "veredictos": [v.model_dump() for _, v in intentos],
        }
        return {"state": state, "traza": traza}

    g = StateGraph(EstadoGrafo)
    for nodo in (entrada, consulta_cerrada, reescribir_consulta, recuperar, escribir, validar_fuentes, buscar_citas,
                 finalizar):
        g.add_node(nodo.__name__, nodo)
    g.add_edge(START, "entrada")
    g.add_conditional_edges("entrada", ruta_formato, ["consulta_cerrada", "reescribir_consulta"])
    g.add_edge("consulta_cerrada", "recuperar")
    g.add_edge("reescribir_consulta", "recuperar")
    g.add_conditional_edges("recuperar", ruta_evidencia, ["escribir", "finalizar"])
    g.add_edge("escribir", "validar_fuentes")
    g.add_edge("buscar_citas", "validar_fuentes")
    if con_juez:
        g.add_node("juzgar", juzgar)
        g.add_conditional_edges("validar_fuentes", ruta_citas, ["buscar_citas", "juzgar"])
        g.add_conditional_edges("juzgar", ruta_veredicto, ["reescribir_consulta", "finalizar"])
    else:
        g.add_conditional_edges("validar_fuentes", ruta_citas, ["buscar_citas", "finalizar"])
    g.add_edge("finalizar", END)
    return g.compile()


def run_with_judge(agente: Any, raw_item: dict, juez: Optional[Juez] = None,
                   mock: bool = False) -> tuple[QuestionState, dict]:
    """Ejecuta el agente con revisión del juez. Devuelve (estado final, traza del juez).

    `juez` por defecto es el real (`evaluate_with_judge`), o el simulado si `mock`. La traza es
    para depurar y medir; no va en submissions.jsonl."""
    juez = juez or (mock_evaluate_with_judge if mock else evaluate_with_judge)
    final = agente.grafo(con_juez=True).invoke({"raw_item": raw_item, "juez": juez})
    return final["state"], final["traza"]


if __name__ == "__main__":
    from src.agent.agent import LegalAgent

    print(LegalAgent().grafo(con_juez=True).get_graph().draw_mermaid())
