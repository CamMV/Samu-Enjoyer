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


def test_presupuesto_de_pasajes_en_el_prompt():
    assert writer_tool.cupos([100, 200, 300], 1000) == [100, 200, 300]       # todo cabe: nada se recorta
    assert writer_tool.cupos([100, 50_000, 300], 1000) == [100, 600, 300]    # solo el gigante se recorta
    assert writer_tool.cupos([900, 900], 1000) == [500, 500]
    largo = CanonicalPassage(id="decreto_1_2020/art_1", texto="Decreto 1 de 2020 › Artículo 1.\n" + "palabra " * 50_000)
    corto = PASAJES[0]
    system, user = writer_tool.build_prompts("¿Pregunta?", FLAGS, [corto, largo])
    assert corto.texto in user and "[…recortado]" in user                   # el corto va completo
    assert len(user) < writer_tool.MAX_CHARS_PASAJES + 2_000
    assert len(largo.texto) > 300_000  # el pasaje original (el que va a submissions.jsonl) no cambia


def test_cerradas_razonan_antes_de_elegir():
    instr = writer_tool._FORMATO_INSTRUCCIONES["multiple_choice"]
    assert instr.index('"justificacion"') < instr.index('"respuesta_correcta"')


def test_subagente_de_citas_solo_suprime_por_defecto(monkeypatch):
    def hook(consulta):
        return []
    hook.buscar_cita = lambda cita: None
    monkeypatch.setattr(batch_runner, "get_real_retriever", lambda: hook)
    monkeypatch.delenv("CITAS_AGREGAR_PASAJES", raising=False)
    assert batch_runner.crear_agente(mock=False)[0].buscador_citas is None
    monkeypatch.setenv("CITAS_AGREGAR_PASAJES", "1")
    assert batch_runner.crear_agente(mock=False)[0].buscador_citas is hook.buscar_cita


def test_batch_runner_filtra_por_formato(tmp_path):
    salida = tmp_path / "cerradas.jsonl"
    batch_runner.ejecutar(batch_runner.ROOT / "data" / "sample_50.jsonl", salida, None, mock=True,
                          formato="multiple_choice")
    import json
    filas = [json.loads(l) for l in salida.read_text(encoding="utf-8").splitlines()]
    assert len(filas) == 15 and {f["formato"] for f in filas} == {"multiple_choice"}


def test_jsonl_con_separadores_unicode_no_se_parte(tmp_path):
    """\u2028 y \x85 dentro de un texto legal no son fin de registro (splitlines() sí los cortaba)."""
    import json
    raro = "Artículo 1.\u2028Texto con separador\x85y otro."
    entrada = tmp_path / "preguntas.jsonl"
    entrada.write_text(json.dumps({"id": 1, "formato": "semi_open", "pregunta": raro}, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    salida = tmp_path / "salida.jsonl"
    batch_runner.ejecutar(entrada, salida, None, mock=True)   # valida al final: no debe lanzar
    filas = [json.loads(l) for l in salida.read_text(encoding="utf-8").split("\n") if l.strip()]
    assert len(filas) == 1 and filas[0]["id"] == 1


def test_dos_corridas_no_escriben_el_mismo_archivo(tmp_path):
    salida = tmp_path / "s.jsonl"
    with batch_runner._candado(salida):
        with pytest.raises(SystemExit, match="Otra corrida está escribiendo"):
            with batch_runner._candado(salida):
                pass
    assert not salida.with_name("s.jsonl.lock").exists()   # se libera al terminar
    with batch_runner._candado(salida):                      # y se puede volver a usar
        pass


# --- calculadora de montos y elección de la letra (cerradas) ---

ART25 = CanonicalPassage(id="codigo_general_proceso/art_25", metadatos={}, texto=(
    "Código General del Proceso (Ley 1564 de 2012)\nArtículo 25. CUANTÍA\nSon de mínima cuantía cuando versen sobre "
    "pretensiones patrimoniales que no excedan el equivalente a cuarenta salarios mínimos legales mensuales vigentes "
    "(40 smlmv). Son de mayor cuantía cuando excedan el equivalente a ciento cincuenta salarios mínimos legales "
    "mensuales vigentes (150 smlmv)."))
SMLMV = CanonicalPassage(id="decreto_1572_2024/art_1", metadatos={}, texto=(
    "Decreto 1572 de 2024\nArtículo 1.\nSalario Mínimo Legal Mensual vigente para el año 2025. Fijar a partir del "
    "primero (1°) de enero de 2025 como Salario Mínimo Legal Mensual, la suma de UN MILLÓN CUATROCIENTOS VEINTITRÉS "
    "MIL QUINIENTOS PESOS ($1.423.500)"))
CUANTIA = {"A": "Alta cuantía", "B": "Menor cuantía", "C": "Mínima cuantía", "D": "Mayor cuantía"}


def test_calculadora_convierte_el_monto_y_lo_compara_con_los_umbrales():
    q = "Si un proceso tiene pretensiones por 30.000.000 COP ¿a qué cuantía corresponde?"
    datos = writer_tool.datos_calculados(q, [ART25, SMLMV])
    assert "$30.000.000 equivalen a 21,07 salarios mínimos" in datos and "salario mínimo de 2025: $1.423.500" in datos
    assert "21,07 NO EXCEDE 40 salarios mínimos." in datos and "21,07 NO EXCEDE 150 salarios mínimos." in datos
    _, user = writer_tool.build_prompts(q, {"formato": "multiple_choice"}, [ART25, SMLMV], CUANTIA)
    assert user.index("DATOS CALCULADOS") < user.index("PREGUNTA:")
    # Sin monto en pesos o sin el decreto del salario mínimo, nada.
    assert writer_tool.datos_calculados("¿Qué es la cuantía?", [ART25, SMLMV]) == ""
    assert writer_tool.datos_calculados(q, [ART25]) == ""


def test_la_letra_sale_del_razonamiento_y_no_del_anuncio(monkeypatch):
    llamadas = []

    def llm(system, user, esquema=None):
        llamadas.append((system, user, esquema))
        if esquema is None:  # escritor: razona "mínima" y anuncia otra letra
            return ('{"justificacion": "Con 21,07 salarios mínimos no se exceden 40 [codigo_general_proceso/art_25], '
                    'así que es de mínima cuantía. Por lo tanto, la opción correcta es D.", '
                    '"respuesta_correcta": "D", "descarte_opciones": {"C": "No.", "B": "No."}, "abstencion": false}')
        return '{"conclusion": "Es de mínima cuantía.", "letra": "C"}'

    monkeypatch.setattr(writer_tool, "_llamar_llm", llm)
    monkeypatch.setattr(writer_tool, "ELEGIR_LETRA", True)
    b = writer_tool.write_legal_response("¿Cuantía?", {"formato": "multiple_choice"}, [ART25], CUANTIA)
    assert b["respuesta_correcta"] == "C" and "C" not in b["descarte_opciones"]
    assert b["justificacion"].endswith("es de mínima cuantía. Por lo tanto, la opción correcta es la C.")
    _, user_letra, esquema = llamadas[1]
    assert "opción correcta es D" not in user_letra             # el verificador no ve el anuncio
    assert esquema["properties"]["letra"]["enum"] == ["A", "B", "C", "D"]


def test_la_letra_no_cambia_si_coincide_o_si_el_verificador_falla(monkeypatch):
    escritor = ('{"justificacion": "Es de mínima cuantía [codigo_general_proceso/art_25].", '
                '"respuesta_correcta": "C", "descarte_opciones": {}, "abstencion": false}')
    for verificador in ('{"conclusion": "Mínima.", "letra": "C"}', requests.exceptions.ConnectionError("caído")):
        def llm(system, user, esquema=None, v=verificador):
            if esquema is None:
                return escritor
            if isinstance(v, Exception):
                raise v
            return v
        monkeypatch.setattr(writer_tool, "_llamar_llm", llm)
        b = writer_tool.write_legal_response("¿Cuantía?", {"formato": "multiple_choice"}, [ART25], CUANTIA)
        assert b["respuesta_correcta"] == "C" and b["justificacion"] == "Es de mínima cuantía [codigo_general_proceso/art_25]."


def test_cerrada_con_letra_no_se_abstiene(monkeypatch):
    monkeypatch.setattr(writer_tool, "ELEGIR_LETRA", False)
    monkeypatch.setattr(writer_tool, "_llamar_llm", lambda s, u, esquema=None: (
        '{"justificacion": "Los pasajes no bastan.", "respuesta_correcta": "B", "descarte_opciones": {}, '
        '"abstencion": true}'))
    b = writer_tool.write_legal_response("¿Cuantía?", {"formato": "multiple_choice"}, [ART25], CUANTIA)
    assert b["abstencion"] is False and b["respuesta_correcta"] == "B"


def test_quitar_anuncios_no_borra_frases_normales():
    texto = "Lo que es a la vez un deber del juez. La opción correcta es la B. Según el artículo 25, B) no aplica."
    assert writer_tool._sin_anuncios(texto) == "Lo que es a la vez un deber del juez."
