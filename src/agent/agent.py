"""LegalAgent: une flags_tool y writer_tool y produce el borrador estructurado."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, List, Optional

from src.agent.schemas import CanonicalPassage, QuestionState
from src.agent.tools.flags_tool import extract_query_flags
from src.agent.tools.writer_tool import write_legal_response

Retriever = Callable[[QuestionState], List[CanonicalPassage]]
_FLAG_KEYS = ("area", "sub_tarea", "complejidad", "tema", "formato")


class LegalAgent:
    """Orquesta: flags -> pasajes -> redacción. El validador y el juez se aplican después."""

    def __init__(self, retriever: Optional[Retriever] = None):
        self.retriever = retriever

    def build_state(self, raw_item: dict) -> QuestionState:
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

    def run(self, raw_item: dict, pasajes: Optional[List[CanonicalPassage]] = None) -> QuestionState:
        """Procesa un item. `pasajes` tiene prioridad sobre el retriever; sin ninguno no hay
        pasajes y el borrador resultante es una abstención."""
        state = self.build_state(raw_item)
        if pasajes is None:
            pasajes = self.retriever(state) if self.retriever else []
        state.pasajes_recuperados = pasajes[:10]
        flags = {k: getattr(state, k) for k in _FLAG_KEYS}
        state.borrador_respuesta = write_legal_response(
            state.pregunta, flags, state.pasajes_recuperados, state.opciones
        )
        state.abstencion = bool(state.borrador_respuesta.get("abstencion", False))
        return state

    @staticmethod
    def to_submission(state: QuestionState) -> dict:
        """Registro conforme a submission.schema.json (sin campos internos de evaluación)."""
        borrador = dict(state.borrador_respuesta or {})
        borrador.pop("formato", None)
        borrador.pop("abstencion", None)
        return {
            "id": state.id,
            "formato": state.formato,
            "abstencion": state.abstencion,
            "pasajes_recuperados": [
                {"doc_id": p.doc_id, "texto": p.texto, **({"score": p.score} if p.score is not None else {})}
                for p in state.pasajes_recuperados
            ],
            **borrador,
        }


if __name__ == "__main__":
    ruta = Path(__file__).resolve().parents[2] / "data" / "sample_50.jsonl"
    with open(ruta, encoding="utf-8") as f:
        item = json.loads(f.readline())

    # Pasajes SIMULADOS (demo): el retriever real lo aporta el módulo de recuperación.
    demo = [
        CanonicalPassage(id="constitucion/art_88", texto="[SIMULADO] Texto del artículo 88 de la Constitución.",
                         metadatos={"vigencia": "vigente"}, score=0.9),
        CanonicalPassage(id="ley_472_1998/art_46", texto="[SIMULADO] Texto del artículo 46 de la Ley 472 de 1998.",
                         metadatos={"vigencia": "vigente"}, score=0.8),
    ]
    estado = LegalAgent().run(item, pasajes=demo)
    print("FLAGS:", json.dumps({k: getattr(estado, k) for k in _FLAG_KEYS}, ensure_ascii=False, indent=2))
    print("RESPUESTA:", json.dumps(estado.borrador_respuesta, ensure_ascii=False, indent=2))
