"""Pruebas de la conversión de citas canónicas a citas que reconoce el evaluador oficial."""
import sys
from pathlib import Path

from src.agent.agent import LegalAgent
from src.agent.citas import borrador_con_citas_legibles, citas_legibles
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
    assert registro["respuesta"] == ("El juez debe dirigir el proceso (artículo 42 del Código General del Proceso "
                                     "(Ley 1564 de 2012)).")
    assert "[" not in registro["referencia_legal"]
    assert "[codigo_general_proceso/art_42]" in state.borrador_respuesta["respuesta"]  # el juez sigue viendo IDs
    texto = registro["respuesta"] + " " + registro["referencia_legal"]
    assert ("codigo_general_proceso", None, None) in citations.bodies(citations.extract(texto))


def test_borrador_anidado():
    b = borrador_con_citas_legibles({"descarte_opciones": {"A": "No [constitucion/art_88]"}, "n": 3}, PASAJES)
    assert b == {"descarte_opciones": {"A": "No (artículo 88 de la Constitución Política de Colombia)"}, "n": 3}
