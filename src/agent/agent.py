"""LegalAgent: une flags_tool y writer_tool y produce el borrador estructurado."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, List, Optional

from src.agent.schemas import CanonicalPassage, QuestionState
from src.agent.tools.flags_tool import extract_query_flags
from src.agent.tools.writer_tool import mock_write_legal_response, write_legal_response

# La recuperación depende de requirements-rag.txt (faiss, bm25s, torch); el agente debe poder
# importarse sin ellas.
try:
    from src.knowledge.hybrid_search import Config, Recuperador, consulta_de
except ImportError:  # pragma: no cover
    Config = Recuperador = consulta_de = None

ROOT = Path(__file__).resolve().parents[2]
Retriever = Callable[[QuestionState], List[CanonicalPassage]]
_FLAG_KEYS = ("area", "sub_tarea", "complejidad", "tema", "formato")


class LegalAgent:
    """Orquesta: flags -> pasajes -> redacción. El validador y el juez se aplican después."""

    def __init__(self, retriever: Optional[Retriever] = None, forzar_mock_escritor: bool = False):
        self.retriever = retriever
        self.forzar_mock_escritor = forzar_mock_escritor

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

    def run(self, raw_item: dict, pasajes: Optional[List[CanonicalPassage]] = None,
            forzar_mock_escritor: Optional[bool] = None) -> QuestionState:
        """Procesa un item. `pasajes` tiene prioridad sobre el retriever; sin ninguno no hay
        pasajes y el borrador resultante es una abstención. `forzar_mock_escritor` (None = el del
        constructor) usa el escritor simulado sin intentar la llamada HTTP al LLM."""
        state = self.build_state(raw_item)
        if pasajes is None:
            pasajes = self.retriever(state) if self.retriever else []
        state.pasajes_recuperados = pasajes[:10]
        flags = {k: getattr(state, k) for k in _FLAG_KEYS}
        mock = self.forzar_mock_escritor if forzar_mock_escritor is None else forzar_mock_escritor
        escribir = mock_write_legal_response if mock else write_legal_response
        state.borrador_respuesta = escribir(
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


def mock_retriever(state: QuestionState) -> List[CanonicalPassage]:
    """Pasajes SIMULADOS: fallback cuando no hay índices en corpus/indices/."""
    return [
        CanonicalPassage(id="constitucion/art_88", texto="[SIMULADO] Texto del artículo 88 de la Constitución.",
                         metadatos={"vigencia": "vigente"}, score=0.9),
        CanonicalPassage(id="ley_472_1998/art_46", texto="[SIMULADO] Texto del artículo 46 de la Ley 472 de 1998.",
                         metadatos={"vigencia": "vigente"}, score=0.8),
    ]


def get_real_retriever() -> Callable[[str], List[CanonicalPassage]]:
    """Adapta `Recuperador.buscar` (dicts) a objetos `CanonicalPassage`.

    Los índices BM25 y denso son opcionales (se usa el que exista); `chunks.sqlite` y el
    reranker son los de la configuración por defecto. Lanza FileNotFoundError / ImportError
    si no hay con qué recuperar, para que el llamador decida el fallback."""
    if Recuperador is None:
        raise ImportError("src.knowledge no disponible: instalar requirements-rag.txt")
    indices = ROOT / "corpus" / "indices"
    bm25_path, denso_path = indices / "bm25_todo", indices / "bge-m3_todo"
    bm25_path = bm25_path if bm25_path.exists() else None
    denso_path = denso_path if (denso_path / "hnsw.faiss").exists() else None
    if bm25_path is None and denso_path is None:
        raise FileNotFoundError(f"No hay índices en {indices}")
    recuperador = Recuperador(bm25_path, denso_path, "bge-reranker-v2-m3", Config())

    def hook(query: str) -> List[CanonicalPassage]:
        resultado = recuperador.buscar(query)
        return [
            CanonicalPassage(
                id=p["chunk_id"],
                texto=p["texto"],
                score=p.get("score"),
                metadatos={k: v for k, v in p.items() if k not in ("chunk_id", "texto", "score")},
            )
            for p in resultado.pasajes
        ]

    return hook


if __name__ == "__main__":
    ruta = ROOT / "data" / "sample_50.jsonl"
    with open(ruta, encoding="utf-8") as f:
        item = json.loads(f.readline())

    try:
        hook = get_real_retriever()
        # LegalAgent llama al retriever con el QuestionState; el hook recibe el texto de búsqueda
        # (pregunta + opciones en las cerradas).
        agente = LegalAgent(lambda s: hook(consulta_de({"pregunta": s.pregunta, "opciones": s.opciones})))
        print("Retriever REAL (corpus/indices)")
    except Exception as e:  # índices ausentes, dependencias RAG o modelos no disponibles
        print(f"Retriever real no disponible ({type(e).__name__}: {e}); se usa mock_retriever")
        agente = LegalAgent(mock_retriever)

    estado = agente.run(item)
    print("FLAGS:", json.dumps({k: getattr(estado, k) for k in _FLAG_KEYS}, ensure_ascii=False, indent=2))
    print("RESPUESTA:", json.dumps(estado.borrador_respuesta, ensure_ascii=False, indent=2))
