"""Tipos de los campos de submissions.jsonl: el evaluador oficial se cae con una lista donde espera texto."""
import sys
from pathlib import Path

from src.agent.agent import LegalAgent
from src.agent.salida import normalizar
from src.agent.schemas import CanonicalPassage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate import answer_text  # noqa: E402  (evaluador oficial)
import citations  # noqa: E402

OPC = {"A": "uno", "B": "dos", "C": "tres", "D": "cuatro"}


def test_justificacion_en_lista_queda_texto():
    b = normalizar({"respuesta_correcta": "C", "justificacion": ["Primero.", "Segundo."],
                    "descarte_opciones": {"A": ["no", "aplica"]}, "extra": 1}, "multiple_choice", OPC)
    assert b == {"respuesta_correcta": "C", "justificacion": "Primero. Segundo.", "descarte_opciones": {"A": "no aplica"}}
    citations.extract(answer_text({"formato": "multiple_choice", **b}))  # ya no se cae


def test_letra_de_la_opcion():
    for v, esperado in [("C", "C"), ("c", "C"), ("C. tres", "C"), ("(B)", "B"), ("Opción D", "D"),
                        ("La respuesta es la opción a", "A"), ("Según la ley, a veces", None), ("E", None), (None, None)]:
        assert normalizar({"respuesta_correcta": v}, "multiple_choice", OPC)["respuesta_correcta"] == esperado, v


def test_semi_y_abierta():
    s = normalizar({"respuesta": {"texto": "x"}, "palabras_clave": "a, b; c", "referencia_legal": ["L1", "L2"]},
                   "semi_open")
    assert s == {"respuesta": "texto: x", "palabras_clave": ["a", "b", "c"], "referencia_legal": "L1 L2"}
    o = normalizar({"analisis": None, "conclusion": 3}, "open_ended")
    assert o == {"marco_normativo": "", "analisis": "", "jurisprudencia": "", "conclusion": "3"}


def test_to_submission_normaliza_y_convierte():
    p = CanonicalPassage(id="ley_472_1998/art_46", texto="Ley 472 de 1998 › TITULO III\nArtículo 46.\n…")
    item = {"id": 51, "formato": "multiple_choice", "pregunta": "¿Acción de grupo?", "opciones": OPC}
    state = LegalAgent().build_state(item)
    state.pasajes_recuperados = [p]
    state.borrador_respuesta = {"formato": "multiple_choice", "abstencion": False, "respuesta_correcta": "C. tres",
                                "justificacion": ["Procede [ley_472_1998/art_46]."], "descarte_opciones": {}}
    r = LegalAgent.to_submission(state)
    assert r["respuesta_correcta"] == "C" and isinstance(r["justificacion"], str)
    assert r["justificacion"] == "Procede (artículo 46 de la Ley 472 de 1998)."
