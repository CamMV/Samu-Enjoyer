"""Pruebas de la conversión de citas canónicas a citas que reconoce el evaluador oficial."""
import sys
from pathlib import Path

from src.agent.agent import LegalAgent
from src.agent.citas import borrador_con_citas_legibles, citas_legibles, con_normas_consultadas, respuesta_concisa, sin_encabezados
from src.agent.schemas import CanonicalPassage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import citations  # noqa: E402  (extractor del evaluador oficial)

CGP = CanonicalPassage(id="codigo_general_proceso/art_42", texto=(
    "Código General del Proceso (Ley 1564 de 2012) › LIBRO PRIMERO. › TÍTULO III.\nArtículo 42. DEBERES DEL JUEZ\n…"))
L1581 = CanonicalPassage(id="ley_1581_2012/art_5#2", texto="Ley 1581 de 2012 › TÍTULO III.\nArtículo 5. DATOS\n…")
CP = CanonicalPassage(id="constitucion/art_88", texto="Constitución Política de Colombia › TITULO II\nArtículo 88.\n…")
C355 = CanonicalPassage(id="jurisprudencia_c-355_2006/ficha",
                        texto="Corte Constitucional, Sentencia C-355 de 2006 › Ficha\nSentencia C-355/06\n…")
DEC = CanonicalPassage(id="decreto_1072_2015/art_2.2.2.2.1", texto="Decreto 1072 de 2015 › PARTE 1\nArtículo 2.2.2.2.1.\n…")
PASAJES = [CGP, L1581, CP, C355, DEC]
NOMBRES = {p.doc_id: p.texto.split(" › ")[0] for p in PASAJES}


def test_convierte_cada_tipo_de_documento():
    assert citas_legibles("Según [codigo_general_proceso/art_42].", NOMBRES) == \
        "Según (artículo 42 del Código General del Proceso (Ley 1564 de 2012))."
    assert citas_legibles("[ley_1581_2012/art_5#2]", NOMBRES) == "(artículo 5 de la Ley 1581 de 2012)"
    assert citas_legibles("[constitucion/art_88]", NOMBRES) == "(artículo 88 de la Constitución Política de Colombia)"
    assert citas_legibles("[jurisprudencia_c-355_2006/ficha]", NOMBRES) == "(Corte Constitucional, Sentencia C-355 de 2006)"
    assert citas_legibles("[decreto_1072_2015/art_2.2.2.2.1]", NOMBRES) == "(artículo 2.2.2.2.1 del Decreto 1072 de 2015)"
    assert citas_legibles("[codigo_general_proceso/art_42/notas]", NOMBRES).startswith("(artículo 42 del Código")


def test_el_evaluador_oficial_reconoce_las_citas_convertidas():
    for p in PASAJES:
        convertida = citas_legibles(f"[{p.id}]", NOMBRES)
        assert citations.extract(f"[{p.id}]") == set() or p.doc_id == "constitucion"  # el formato crudo no sirve
        cuerpos = citations.bodies(citations.extract(convertida))
        assert cuerpos and cuerpos <= citations.bodies(citations.extract(p.texto)), (p.id, convertida)


def test_ids_sueltos_y_ajenos():
    # Sin corchetes (p. ej. en referencia_legal) también se convierte si el documento está en los pasajes.
    assert citas_legibles("codigo_general_proceso/art_42, ley_1581_2012/art_5", NOMBRES) == \
        "artículo 42 del Código General del Proceso (Ley 1564 de 2012), artículo 5 de la Ley 1581 de 2012"
    # Un ID entre corchetes de un documento que no está en los pasajes se quita; el texto normal no se toca.
    assert citas_legibles("Ver [ley_999_2020/art_1] y/o la C-355/06.", NOMBRES) == "Ver y/o la C-355/06."


def test_to_submission_convierte_y_conserva_el_borrador():
    state = LegalAgent().build_state({"id": 1, "formato": "semi_open", "pregunta": "¿Deberes del juez?"})
    state.pasajes_recuperados = PASAJES
    state.borrador_respuesta = {"formato": "semi_open", "abstencion": False,
                                "respuesta": "El juez debe dirigir el proceso [codigo_general_proceso/art_42].",
                                "palabras_clave": ["juez"], "referencia_legal": "[codigo_general_proceso/art_42]"}
    registro = LegalAgent.to_submission(state)
    # La cita sale del texto que lee RAGAS y queda en referencia_legal, que lee el evaluador de citas.
    assert registro["respuesta"] == "El juez debe dirigir el proceso."
    assert "artículo 42 del Código General del Proceso (Ley 1564 de 2012)" in registro["referencia_legal"]
    assert "[" not in registro["referencia_legal"]
    assert "[codigo_general_proceso/art_42]" in state.borrador_respuesta["respuesta"]  # el juez sigue viendo IDs
    texto = registro["respuesta"] + " " + registro["referencia_legal"]
    assert ("codigo_general_proceso", None, None) in citations.bodies(citations.extract(texto))


def test_borrador_anidado():
    b = borrador_con_citas_legibles({"descarte_opciones": {"A": "No [constitucion/art_88]"}, "n": 3}, PASAJES)
    assert b == {"descarte_opciones": {"A": "No (artículo 88 de la Constitución Política de Colombia)"}, "n": 3}


def test_normas_consultadas_en_el_campo_de_fundamento(monkeypatch):
    from src.agent import citas
    monkeypatch.setattr(citas, "FUENTES_AMPLIADAS", False)  # la lista base; las ampliadas tienen su prueba
    b = con_normas_consultadas({"referencia_legal": "artículo 42 del CGP", "respuesta": "x"}, "semi_open", PASAJES)
    assert b["respuesta"] == "x"
    assert b["referencia_legal"] == (
        "artículo 42 del CGP Normas de los pasajes consultados: artículo 42 del Código General del Proceso "
        "(Ley 1564 de 2012); artículo 5 de la Ley 1581 de 2012; artículo 88 de la Constitución Política de "
        "Colombia; artículo 2.2.2.2.1 del Decreto 1072 de 2015.")  # sin la sentencia
    got = citations.bodies(citations.extract(b["referencia_legal"]))
    assert {("codigo_general_proceso", None, None), ("ley", "1581", "2012"), ("constitucion", None, None)} <= got
    assert con_normas_consultadas({"justificacion": ""}, "multiple_choice", [CGP])["justificacion"].startswith(
        "Normas de los pasajes consultados: artículo 42")
    abierta = {"marco_normativo": "m", "analisis": "a"}
    assert con_normas_consultadas(abierta, "open_ended", PASAJES) == abierta  # RAGAS lee todos sus campos


def test_to_submission_no_agrega_normas_si_se_abstiene():
    state = LegalAgent().build_state({"id": 2, "formato": "semi_open", "pregunta": "¿?"})
    state.pasajes_recuperados, state.abstencion = PASAJES, True
    state.borrador_respuesta = {"respuesta": "", "palabras_clave": [], "referencia_legal": ""}
    assert LegalAgent.to_submission(state)["referencia_legal"] == ""


def test_respuesta_concisa_saca_las_citas_y_deja_tres_oraciones():
    b = {"respuesta": ("Sí procede (artículo 46 de la Ley 472 de 1998). La exige un grupo (artículo 3 de la Ley 472 "
                       "de 1998). Requiere 20 personas. Es una acción de reparación. Caduca en dos años."),
         "referencia_legal": "artículo 46 de la Ley 472 de 1998", "palabras_clave": ["grupo"]}
    r = respuesta_concisa(b, 3)
    assert r["respuesta"] == "Sí procede. La exige un grupo. Requiere 20 personas."
    assert r["referencia_legal"] == "artículo 46 de la Ley 472 de 1998; artículo 3 de la Ley 472 de 1998"
    got = citations.bodies(citations.extract(r["respuesta"] + " " + r["referencia_legal"]))
    assert ("ley", "472", "1998") in got                       # el evaluador de citas las sigue viendo
    assert respuesta_concisa({"respuesta": "Plazo de diez (10) días. Otra."}, 3)["respuesta"] == \
        "Plazo de diez (10) días. Otra."                     # paréntesis que no son citas se quedan


def test_sin_encabezados_de_seccion():
    b = {"jurisprudencia": "Sentencia SC-13208 de 2015 › II. LA DEMANDA D E CASACIÓN (32/78) fija la regla.",
         "otro": ["Corte Constitucional, Sentencia T-1 de 2020 › Inicio (3/5)"]}
    assert sin_encabezados(b) == {"jurisprudencia": "Sentencia SC-13208 de 2015 fija la regla.",
                                  "otro": ["Corte Constitucional, Sentencia T-1 de 2020"]}


def test_sin_meta_texto_solo_en_los_campos_de_ragas():
    from src.agent.citas import sin_meta_texto
    b = {"respuesta": "Según los pasajes proporcionados, la acción procede. La norma, según los pasajes, exige veinte "
                      "personas. El juez decide en los pasajes de su despacho.",
         "referencia_legal": "Según los pasajes, Ley 472 de 1998"}
    r = sin_meta_texto(b, "semi_open")
    assert r["respuesta"] == ("La acción procede. La norma exige veinte personas. "
                              "El juez decide en los pasajes de su despacho.")   # "pasajes" sin calificativo se queda
    assert r["referencia_legal"] == b["referencia_legal"]                       # RAGAS no lo lee: no se toca
    abierta = sin_meta_texto({"marco_normativo": "Los pasajes indican que rige la Ley 472 de 1998."}, "open_ended")
    assert abierta["marco_normativo"] == "Rige la Ley 472 de 1998."


def test_fuentes_ampliadas_sentencias_y_leyes_mencionadas(monkeypatch):
    from src.agent import citas
    from src.agent.schemas import CanonicalPassage
    pasajes = [
        CanonicalPassage(id="codigo_general_proceso/art_24#1",
                         texto="Código General del Proceso (Ley 1564 de 2012) › Artículo 24.\nLa Superintendencia..."),
        CanonicalPassage(id="jurisprudencia_t-173_2011/ficha",
                         texto="Corte Constitucional, Sentencia T-173 de 2011 › Ficha\nSegún el Código Sustantivo del "
                               "Trabajo y el Decreto 1072 de 2015, en concordancia con la Ley 1233 de 2008..."),
        CanonicalPassage(id="csj_sp_1977/ficha", texto="Csj sp 24 01 1977 › Ficha\nTexto."),
    ]
    monkeypatch.setattr(citas, "FUENTES_AMPLIADAS", False)
    base = citas.con_normas_consultadas({"referencia_legal": "x"}, "semi_open", pasajes)["referencia_legal"]
    assert "Sentencias" not in base
    monkeypatch.setattr(citas, "FUENTES_AMPLIADAS", True)
    ref = citas.con_normas_consultadas({"referencia_legal": "x"}, "semi_open", pasajes)["referencia_legal"]
    assert "Sentencias de los pasajes consultados: Corte Constitucional, Sentencia T-173 de 2011." in ref
    assert "Código Sustantivo del Trabajo" in ref and "Ley 1233 de 2008" in ref
    assert "Decreto 1072" not in ref.split("Leyes y códigos")[1]       # decretos mencionados: no
    assert "Csj sp" not in ref                                          # encabezado sin cita reconocible
    assert ref.count("Código General del Proceso") == 1                 # ya estaba en las normas consultadas
