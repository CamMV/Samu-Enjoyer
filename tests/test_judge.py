"""Pruebas del LLM as judge y de su ciclo. Sin red, sin índices y sin LLM."""
import json

import pytest
import requests

from src.agent import judge_loop
from src.agent.agent import LegalAgent
from src.agent.judge_loop import run_with_judge
from src.agent.schemas import CanonicalPassage
from src.agent.tools import judge_tool
from src.agent.tools.judge_tool import (build_judge_prompts, citas_fuera_de_pasajes, evaluate_with_judge,
                                        mock_evaluate_with_judge)

ITEM = {
    "id": 51, "formato": "multiple_choice", "area": "Derecho constitucional", "tema": "Acción de grupo",
    "pregunta": "¿En cuál de los siguientes casos procede la acción de grupo?",
    "opciones": {"A": "Derechos fundamentales", "B": "Interés colectivo", "C": "Perjuicios individuales",
                 "D": "Inconstitucionalidad"},
    "legal_basis": "LEGAL_BASIS_SECRETA", "respuesta_correcta": "C",
    "texto_respuesta_correcta": "TEXTO_CORRECTO_SECRETO", "respuesta_esperada": "ESPERADA_SECRETA",
}
P46 = CanonicalPassage(id="ley_472_1998/art_46", texto="Las acciones de grupo proceden por perjuicios individuales.",
                       metadatos={"vigencia": "vigente"})
P88 = CanonicalPassage(id="constitucion/art_88", texto="La ley regulará las acciones populares.",
                       metadatos={"vigencia": "vigente"})
OK = {"responde_sub_tarea": True, "afirmaciones_sin_soporte": [], "pasajes_suficientes": True,
      "area_coherente": True, "feedback": "", "consulta_sugerida": ""}
RECHAZO = {**OK, "afirmaciones_sin_soporte": ["Exige 20 personas"], "pasajes_suficientes": False,
           "feedback": "Falta la norma.", "consulta_sugerida": "Ley 472 de 1998 artículo 46"}


def _estado(borrador=None, pasajes=(P46,)):
    state = LegalAgent().build_state(ITEM)
    state.pasajes_recuperados = list(pasajes)
    state.borrador_respuesta = borrador or {
        "formato": "multiple_choice", "abstencion": False, "respuesta_correcta": "C",
        "justificacion": "Procede por perjuicios individuales [ley_472_1998/art_46].", "descarte_opciones": {}}
    return state


def _responde(monkeypatch, *salidas):
    """El LLM del juez devuelve `salidas` en orden (dict -> JSON; excepción -> se lanza)."""
    cola, llamadas = list(salidas), []

    def falso(system, user):
        llamadas.append((system, user))
        salida = cola.pop(0)
        if isinstance(salida, Exception):
            raise salida
        return json.dumps(salida) if isinstance(salida, dict) else salida

    monkeypatch.setattr(judge_tool, "_llamar_juez", falso)
    return llamadas


def test_aprueba(monkeypatch):
    _responde(monkeypatch, OK)
    v = evaluate_with_judge(_estado())
    assert v.aprobado is True and v.origen == "llm"


def test_rechaza_afirmacion_sin_soporte(monkeypatch):
    _responde(monkeypatch, RECHAZO)
    v = evaluate_with_judge(_estado())
    assert v.aprobado is False and v.afirmaciones_sin_soporte == ["Exige 20 personas"]


def test_aprobado_se_calcula_en_codigo(monkeypatch):
    _responde(monkeypatch, {**RECHAZO, "aprobado": True})
    assert evaluate_with_judge(_estado()).aprobado is False


def test_area_incoherente_no_rechaza(monkeypatch):
    _responde(monkeypatch, {**OK, "area_coherente": False})
    v = evaluate_with_judge(_estado())
    assert v.aprobado is True and v.area_coherente is False


def test_cita_fuera_de_pasajes_rechaza_aunque_el_llm_apruebe(monkeypatch):
    _responde(monkeypatch, OK)
    borrador = {"respuesta": "Según [ley_472_1998/art_46] y [ley_1564_2012/art_42]."}
    v = evaluate_with_judge(_estado(borrador))
    assert v.citas_invalidas == ["ley_1564_2012/art_42"] and v.aprobado is False


def test_citas_de_articulo_partido_y_notas_son_validas():
    pasajes = [CanonicalPassage(id="ley_1_2000/art_5#2", texto="x", metadatos={"articulo_id": "ley_1_2000/art_5"}),
               CanonicalPassage(id="ley_2_2001/art_7/notas", texto="y")]
    borrador = {"a": "[ley_1_2000/art_5] [ley_2_2001/art_7] [ley_1_2000] [ley_1_2000/art_6]", "b": ["[otra/art_1]"]}
    assert citas_fuera_de_pasajes(borrador, pasajes) == ["ley_1_2000/art_6", "otra/art_1"]


@pytest.mark.parametrize("salida", [requests.exceptions.ConnectionError("caído"), "no es json", {"feedback": "x"},
                                    {**OK, "responde_sub_tarea": "quizás"}])
def test_fallo_del_juez_no_decide(monkeypatch, salida):
    _responde(monkeypatch, salida)
    v = evaluate_with_judge(_estado())
    assert v.aprobado is None and v.origen == "error"


def test_abstencion_no_llama_al_llm(monkeypatch):
    llamadas = _responde(monkeypatch)
    v = evaluate_with_judge(_estado({"formato": "multiple_choice", "abstencion": True}))
    assert v.aprobado is True and v.origen == "determinista" and not llamadas


def test_prompt_sin_clave():
    system, user = build_judge_prompts(_estado())
    for secreto in ("LEGAL_BASIS_SECRETA", "TEXTO_CORRECTO_SECRETO", "ESPERADA_SECRETA"):
        assert secreto not in system + user
    assert "[ley_472_1998/art_46] (vigencia: vigente)" in user and "respuesta_correcta: C" in user


def test_host_prohibido(monkeypatch):
    monkeypatch.setattr(judge_tool, "JUDGE_BASE_URL", "https://api.openai.com/v1")
    with pytest.raises(ValueError):
        judge_tool._llamar_juez("s", "u")


def test_llamada_reintenta_sin_salida_guiada(monkeypatch):
    class Resp:
        def __init__(self, status):
            self.status_code = status

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "{}"}}]}

    payloads = []

    def post(url, json, timeout):
        payloads.append(json)
        return Resp(400 if len(payloads) == 1 else 200)

    monkeypatch.setattr(judge_tool.requests, "post", post)
    monkeypatch.setattr(judge_tool, "JUDGE_BASE_URL", "http://localhost:8000/v1")
    assert judge_tool._llamar_juez("s", "u") == "{}"
    assert "response_format" in payloads[0] and "response_format" not in payloads[1]
    assert all(p["temperature"] == 0 for p in payloads)


def test_juez_mock():
    assert mock_evaluate_with_judge(_estado()).aprobado is True
    assert mock_evaluate_with_judge(_estado({"respuesta": "Según [otra/art_1]."})).aprobado is False


# --- ciclo ---

def _agente(consultas, segunda=(P88,)):
    def retriever(state):
        consultas.append(state.pregunta)
        return [P46] if len(consultas) == 1 else list(segunda)

    return LegalAgent(retriever, forzar_mock_escritor=True)


def test_ciclo_aprueba_a_la_primera(monkeypatch):
    llamadas, consultas = _responde(monkeypatch, OK), []
    state, traza = run_with_judge(_agente(consultas), ITEM)
    assert state.aprobado_por_juez is True and state.ciclo_actual == 1
    assert traza["ciclos"] == 1 and len(consultas) == 1 and len(llamadas) == 1


def test_ciclo_reintenta_con_la_consulta_del_juez(monkeypatch):
    _responde(monkeypatch, RECHAZO, OK)
    consultas = []
    state, traza = run_with_judge(_agente(consultas), ITEM)
    assert consultas[1] == ITEM["pregunta"] + "\nLey 472 de 1998 artículo 46"
    assert state.ciclo_actual == 2 and state.aprobado_por_juez is True
    assert [p.id for p in state.pasajes_recuperados] == ["constitucion/art_88"]
    assert state.pregunta == ITEM["pregunta"] and state.queries_generadas == consultas
    assert traza["ciclos"] == 2 and traza["ciclo_elegido"] == 2 and not traza["abstencion_forzada"]


def test_ciclo_maximo_dos_y_abstencion_forzada(monkeypatch):
    llamadas = _responde(monkeypatch, RECHAZO, RECHAZO, RECHAZO)
    state, traza = run_with_judge(_agente([]), ITEM)
    assert len(llamadas) == 2 and traza["ciclos"] == 2
    assert traza["abstencion_forzada"] and state.abstencion and state.aprobado_por_juez is False
    registro = LegalAgent.to_submission(state)
    assert registro["abstencion"] is True and registro["respuesta_correcta"] is None
    assert not {"aprobado_por_juez", "juez_feedback", "citas_invalidas"} & set(registro)


def test_ciclo_sin_abstencion_elige_el_mejor_borrador(monkeypatch):
    monkeypatch.setattr(judge_loop, "JUDGE_ABSTENER", False)
    peor = {**RECHAZO, "afirmaciones_sin_soporte": ["a", "b"]}
    _responde(monkeypatch, RECHAZO, peor)
    state, traza = run_with_judge(_agente([]), ITEM)
    assert traza["ciclo_elegido"] == 1 and not state.abstencion
    assert [p.id for p in state.pasajes_recuperados] == ["ley_472_1998/art_46"]


def test_ciclo_no_reintenta_con_los_mismos_pasajes(monkeypatch):
    llamadas = _responde(monkeypatch, {**RECHAZO, "pasajes_suficientes": True})
    state, traza = run_with_judge(_agente([], segunda=(P46,)), ITEM)
    assert len(llamadas) == 1 and traza["ciclos"] == 1 and state.aprobado_por_juez is False


def test_ciclo_juez_caido_conserva_el_borrador(monkeypatch):
    _responde(monkeypatch, requests.exceptions.Timeout("lento"))
    consultas = []
    state, traza = run_with_judge(_agente(consultas), ITEM)
    assert state.aprobado_por_juez is None and not state.abstencion and len(consultas) == 1
    assert state.borrador_respuesta["respuesta_correcta"]
