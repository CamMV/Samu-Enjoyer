"""Pruebas de las fallas del escritor y del arranque del lote. Sin red, sin índices y sin LLM."""
import pytest
import requests

from src.agent import batch_runner
from src.agent.schemas import CanonicalPassage
from src.agent.tools import writer_tool

FLAGS = {"formato": "semi_open", "area": "Derecho procesal", "tema": "juez", "sub_tarea": "definicion"}
PASAJES = [CanonicalPassage(id="codigo_general_proceso/art_42", texto="Código General del Proceso › Artículo 42.")]


def test_llm_caido_da_abstencion_y_no_mock(monkeypatch, capsys):
    def caido(system, user):
        raise requests.exceptions.ConnectTimeout("timeout")
    monkeypatch.setattr(writer_tool, "_llamar_llm", caido)
    borrador = writer_tool.write_legal_response("¿Deberes del juez?", FLAGS, PASAJES)
    assert borrador["abstencion"] is True and "[MOCK]" not in str(borrador)
    assert "AVISO" in capsys.readouterr().err


def test_json_invalido_da_abstencion(monkeypatch):
    monkeypatch.setattr(writer_tool, "_llamar_llm", lambda s, u: "no es json")
    assert writer_tool.write_legal_response("¿Deberes del juez?", FLAGS, PASAJES)["abstencion"] is True


def test_corrida_real_sin_indices_se_detiene(monkeypatch):
    def sin_indices():
        raise FileNotFoundError("No hay índices")
    monkeypatch.setattr(batch_runner, "get_real_retriever", sin_indices)
    with pytest.raises(SystemExit, match="Recuperación real no disponible"):
        batch_runner.crear_agente(mock=False)
    agente, modo = batch_runner.crear_agente(mock=True)
    assert modo == "mock" and agente.forzar_mock_escritor


def test_rag_device_denso_llega_al_recuperador(monkeypatch, tmp_path):
    from src.agent import agent as agent_mod
    indices = tmp_path / "corpus" / "indices"
    (indices / "bm25_todo").mkdir(parents=True)
    (indices / "qwen3-emb-0.6b_todo").mkdir()
    (indices / "qwen3-emb-0.6b_todo" / "hnsw.faiss").write_bytes(b"")
    visto = {}

    class Falso:
        def __init__(self, *a, **kw):
            visto.update(kw)

    monkeypatch.setattr(agent_mod, "ROOT", tmp_path)
    monkeypatch.setattr(agent_mod, "Recuperador", Falso)
    monkeypatch.setattr(agent_mod, "Config", lambda: None)
    monkeypatch.setenv("RAG_DEVICE_DENSO", "cpu")
    agent_mod.get_real_retriever()
    assert visto["dispositivo_denso"] == "cpu"
    monkeypatch.setenv("RAG_DEVICE_DENSO", "")
    agent_mod.get_real_retriever()
    assert visto["dispositivo_denso"] is None


def test_pasaje_largo_se_recorta_solo_en_el_prompt():
    largo = CanonicalPassage(id="decreto_1_2020/art_1", texto="Decreto 1 de 2020 › Artículo 1.\n" + "palabra " * 5000)
    system, user = writer_tool.build_prompts("¿Pregunta?", FLAGS, [largo] * 10)
    assert "[…recortado]" in user and len(user) < 10 * (writer_tool.MAX_CHARS_PASAJE + 200) + 500
    assert len(largo.texto) > 40_000  # el pasaje original (el que va a submissions.jsonl) no cambia
    corto = PASAJES[0]
    assert writer_tool.texto_para_prompt(corto) == corto.texto
