"""Pruebas del subagente de búsqueda de citas. Sin red, sin índices y sin LLM."""
import json

from src.agent.agent import LegalAgent
from src.agent.graph import run_with_judge
from src.agent.schemas import CanonicalPassage
from src.agent.tools import judge_tool, writer_tool
from src.agent.tools.citation_search_tool import buscar_cita, resolver_citas, suprimir_citas
from src.agent.tools.judge_tool import citas_fuera_de_pasajes

ITEM = {"id": 7, "formato": "semi_open", "pregunta": "¿Cuándo procede la acción de grupo?"}
P46 = CanonicalPassage(id="ley_472_1998/art_46", texto="Ley 472 de 1998 › TÍTULO III\nArtículo 46. Acciones de grupo.")
OK = {"responde_sub_tarea": True, "afirmaciones_sin_soporte": [], "pasajes_suficientes": True,
      "area_coherente": True, "feedback": "", "consulta_sugerida": ""}


def _chunk(cid, tipo="articulo", texto=None, **extra):
    doc = cid.split("/")[0]
    return {"chunk_id": cid, "doc_id": doc, "tipo_chunk": tipo, "texto": texto or f"Texto de {cid}", **extra}


class AlmacenFalso:
    def __init__(self, *chunks):
        self.chunks = {c["chunk_id"]: c for c in chunks}

    def get(self, ids):
        return {i: self.chunks[i] for i in ids if i in self.chunks}

    def por(self, campo, valor):
        return [c for c in self.chunks.values() if c.get(campo) == valor]


ALMACEN = AlmacenFalso(
    _chunk("ley_472_1998/art_3", articulo_id="ley_472_1998/art_3", vigencia="vigente"),
    _chunk("ley_1_2000/art_5#1", "parte_articulo", "Ley 1 › T\nArtículo 5 (parte 1 de 2)\nuno",
           articulo_id="ley_1_2000/art_5", parte=1),
    _chunk("ley_1_2000/art_5#2", "parte_articulo", "Ley 1 › T\nArtículo 5 (parte 2 de 2)\ndos",
           articulo_id="ley_1_2000/art_5", parte=2),
    _chunk("ley_9_1990/art_1", articulo_id="ley_9_1990/art_1", vigencia="derogada"),
    _chunk("jurisprudencia_c-355_2006/ficha", "ficha"),
)


def _buscar(cita):
    return buscar_cita(cita, ALMACEN)


def _estado(respuesta, pasajes=(P46,)):
    state = LegalAgent().build_state(ITEM)
    state.pasajes_recuperados = list(pasajes)
    state.borrador_respuesta = {"formato": "semi_open", "abstencion": False, "respuesta": respuesta,
                                "palabras_clave": [], "referencia_legal": ""}
    state.citas_invalidas = citas_fuera_de_pasajes(state.borrador_respuesta, state.pasajes_recuperados)
    return state


def test_buscar_cita_en_el_corpus():
    assert _buscar("LEY_472_1998/art_3").id == "ley_472_1998/art_3"
    assert _buscar("jurisprudencia_c-355_2006/ficha").metadatos["tipo_chunk"] == "ficha"
    assert _buscar("ley_472_1998/art_999") is None and _buscar("ley_472_1998") is None
    assert _buscar("ley_9_1990/art_1").metadatos["derogado"] is True


def test_articulo_partido_se_entrega_completo():
    for cita in ("ley_1_2000/art_5", "ley_1_2000/art_5#2"):
        p = _buscar(cita)
        assert p.id == "ley_1_2000/art_5" and "uno" in p.texto and "dos" in p.texto
    assert buscar_cita("ley_1_2000/art_5", ALMACEN, lambda d: "COMPLETO").texto == "COMPLETO"


def test_cita_existente_agrega_el_pasaje():
    state = _estado("Procede [ley_472_1998/art_46] y se define en [ley_472_1998/art_3].")
    informe = resolver_citas(state, _buscar)
    assert [p.id for p in state.pasajes_recuperados] == ["ley_472_1998/art_46", "ley_472_1998/art_3"]
    assert informe[0]["accion"] == "agregada" and "[ley_472_1998/art_3]" in state.borrador_respuesta["respuesta"]
    assert citas_fuera_de_pasajes(state.borrador_respuesta, state.pasajes_recuperados) == []


def test_citas_sin_respaldo_se_suprimen():
    state = _estado("Según [ley_472_1998/art_46], [ley_472_1998/art_999] y [ley_9_1990/art_1].")
    informe = resolver_citas(state, _buscar)
    assert [(i["cita"], i["accion"]) for i in informe] == [
        ("ley_472_1998/art_999", "suprimida"), ("ley_9_1990/art_1", "suprimida")]
    assert [p.id for p in state.pasajes_recuperados] == ["ley_472_1998/art_46"]
    texto = state.borrador_respuesta["respuesta"]
    assert "[ley_472_1998/art_46]" in texto and "art_999" not in texto and "ley_9_1990" not in texto
    assert citas_fuera_de_pasajes(state.borrador_respuesta, state.pasajes_recuperados) == []


def test_sin_corpus_solo_suprime():
    state = _estado("Se define en [ley_472_1998/art_3].")
    assert resolver_citas(state, None)[0]["motivo"] == "sin corpus donde buscar"
    assert state.borrador_respuesta["respuesta"] == "Se define en."
    assert len(state.pasajes_recuperados) == 1


def test_nunca_mas_de_diez_pasajes():
    relleno = [CanonicalPassage(id=f"ley_{i}_2001/art_1", texto="x") for i in range(9)]
    state = _estado("Procede [ley_472_1998/art_46] y [ley_0_2001/art_1]; ver [ley_472_1998/art_3].", [P46, *relleno])
    resolver_citas(state, _buscar)
    ids = [p.id for p in state.pasajes_recuperados]
    # Sustituye al último pasaje no citado; los citados se conservan.
    assert len(ids) == 10 and ids[-1] == "ley_472_1998/art_3" and "ley_8_2001/art_1" not in ids
    assert {"ley_472_1998/art_46", "ley_0_2001/art_1"} <= set(ids)

    todos = " ".join(f"[{p.id}]" for p in [P46, *relleno])
    state = _estado(f"{todos} y [ley_472_1998/art_3].", [P46, *relleno])
    assert resolver_citas(state, _buscar)[0]["accion"] == "suprimida"
    assert "ley_472_1998/art_3" not in [p.id for p in state.pasajes_recuperados]


def test_dos_formas_del_mismo_articulo_agregan_un_solo_pasaje():
    state = _estado("Ver [ley_1_2000/art_5#1] y [ley_1_2000/art_5#2].")
    informe = resolver_citas(state, _buscar)
    assert [i["accion"] for i in informe] == ["agregada", "agregada"] and len(state.pasajes_recuperados) == 2


def test_suprimir_citas_en_textos_anidados():
    borrador = {"a": "Uno [x/art_1] ([x/art_2]).", "b": {"A": "[x/art_1]"}, "c": ["[x/art_3]"], "d": True}
    assert suprimir_citas(borrador, ["x/art_1", "x/art_2"]) == {"a": "Uno.", "b": {"A": ""}, "c": ["[x/art_3]"],
                                                               "d": True}


def test_grafo_resuelve_las_citas_antes_del_juez(monkeypatch):
    borrador = {"respuesta": "Procede [ley_472_1998/art_46]; se define en [ley_472_1998/art_3] y [inventada/art_1].",
                "palabras_clave": [], "referencia_legal": "", "abstencion": False}
    monkeypatch.setattr(writer_tool, "_llamar_llm", lambda s, u: json.dumps(borrador))
    vistos = []

    def juez_llm(system, user):
        vistos.append(user)
        return json.dumps(OK)

    monkeypatch.setattr(judge_tool, "_llamar_juez", juez_llm)
    agente = LegalAgent(lambda s: [P46], buscador_citas=_buscar)
    entrada = {"raw_item": ITEM, "juez": judge_tool.evaluate_with_judge}
    nodos = [n for paso in agente.grafo(con_juez=True).stream(entrada, stream_mode="updates") for n in paso]
    assert nodos == ["entrada", "reescribir_consulta", "recuperar", "escribir", "validar_fuentes", "buscar_citas",
                     "validar_fuentes", "juzgar", "finalizar"]

    state, traza = run_with_judge(agente, ITEM)
    # El juez ve el pasaje agregado y ya no hay citas inválidas que lo hagan rechazar.
    assert state.aprobado_por_juez is True and state.citas_invalidas == [] and traza["ciclos"] == 1
    assert "[ley_472_1998/art_3]" in vistos[-1] and "inventada" not in vistos[-1]
    assert [c["accion"] for c in traza["citas"]] == ["agregada", "suprimida"]
    registro = LegalAgent.to_submission(state)
    assert len(registro["pasajes_recuperados"]) == 2 and "busqueda_citas" not in registro
    texto = registro["respuesta"] + " " + registro["referencia_legal"]  # lo que lee el evaluador de citas
    assert "artículo 3 de la Ley 472 de 1998" in texto and "inventada" not in texto
