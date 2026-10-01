"""Pruebas del grafo de LangGraph del agente. Sin red, sin índices y sin LLM."""
import json

from src.agent.agent import LegalAgent
from src.agent.graph import run_with_judge
from src.agent.schemas import CanonicalPassage
from src.agent.tools import judge_tool

CERRADA = {"id": 1, "formato": "multiple_choice", "pregunta": "¿Cuándo procede la acción de grupo?",
           "opciones": {"A": "Interés colectivo", "B": "Perjuicios individuales"}}
ABIERTA = {"id": 2, "formato": "semi_open", "pregunta": "¿Qué es la acción de grupo?"}
P46 = CanonicalPassage(id="ley_472_1998/art_46", texto="Las acciones de grupo proceden por perjuicios individuales.")
P88 = CanonicalPassage(id="constitucion/art_88", texto="La ley regulará las acciones populares.")
RECHAZO = {"responde_sub_tarea": True, "afirmaciones_sin_soporte": ["x"], "pasajes_suficientes": True,
           "area_coherente": True, "feedback": "Falta la norma.", "consulta_sugerida": "Ley 472 de 1998"}


def _nodos(agente, item, con_juez=False):
    entrada = {"raw_item": item, "juez": judge_tool.mock_evaluate_with_judge}
    return [n for paso in agente.grafo(con_juez).stream(entrada, stream_mode="updates") for n in paso]


def test_nodos_del_grafo():
    nodos = set(LegalAgent().grafo(con_juez=True).get_graph().nodes)
    assert {"entrada", "consulta_cerrada", "reescribir_consulta", "recuperar", "escribir", "validar_fuentes",
            "juzgar", "finalizar"} <= nodos
    assert "juzgar" not in LegalAgent().grafo().get_graph().nodes


def test_ruta_por_formato():
    agente = LegalAgent(lambda s: [P46], forzar_mock_escritor=True)
    assert _nodos(agente, CERRADA) == ["entrada", "consulta_cerrada", "recuperar", "escribir", "validar_fuentes",
                                       "finalizar"]
    assert _nodos(agente, ABIERTA, con_juez=True) == ["entrada", "reescribir_consulta", "recuperar", "escribir",
                                                      "validar_fuentes", "juzgar", "finalizar"]


def test_sin_juez_entrega_el_borrador_y_valida_fuentes():
    state = LegalAgent(lambda s: [P46], forzar_mock_escritor=True).run(ABIERTA)
    assert state.borrador_respuesta["respuesta"] and not state.abstencion
    assert state.citas_invalidas == [] and state.aprobado_por_juez is None
    assert LegalAgent(forzar_mock_escritor=True).run(ABIERTA).abstencion  # sin retriever no hay pasajes


def test_pasajes_inyectados_tienen_prioridad():
    state = LegalAgent(lambda s: [P46], forzar_mock_escritor=True).run(ABIERTA, pasajes=[P88])
    assert [p.id for p in state.pasajes_recuperados] == ["constitucion/art_88"]


def test_el_reintento_no_muta_el_primer_intento(monkeypatch):
    monkeypatch.setattr(judge_tool, "JUDGE_VOTO_CERRADAS", False)  # prueba la revisión, no el voto
    monkeypatch.setattr(judge_tool, "_llamar_juez", lambda s, u, esquema=None: json.dumps(RECHAZO))
    vistos = []

    def retriever(state):
        vistos.append(state.pregunta)
        return [P46] if len(vistos) == 1 else [P88]

    state, traza = run_with_judge(LegalAgent(retriever, forzar_mock_escritor=True), CERRADA)
    # Dos rechazos con los mismos problemas: se entrega el más reciente y el primero queda como estaba.
    assert traza["ciclos"] == 2 and traza["ciclo_elegido"] == 2
    assert [p.id for p in state.pasajes_recuperados] == ["constitucion/art_88"]
    assert vistos[1] == CERRADA["pregunta"] + "\nLey 472 de 1998" and state.pregunta == CERRADA["pregunta"]
