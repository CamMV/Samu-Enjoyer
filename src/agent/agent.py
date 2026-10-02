"""LegalAgent: fachada del grafo de LangGraph (src/agent/graph.py) que produce el borrador estructurado."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, List, Optional

from src.agent.citas import (abierta_concisa, con_fuentes_abiertas, sin_oraciones_accesorias, borrador_con_citas_legibles, con_normas_consultadas, respuesta_concisa,
                             sin_encabezados, sin_meta_texto)
from src.agent.graph import _FLAG_KEYS, construir_grafo, estado_inicial
from src.agent.salida import normalizar
from src.agent.schemas import CanonicalPassage, QuestionState
from src.agent.tools.citation_search_tool import Buscador, buscar_cita
from src.agent.tools import writer_tool
from src.agent.tools.writer_tool import oraciones_semiabierta

# La recuperación depende de requirements-rag.txt (faiss, bm25s, torch); el agente debe poder
# importarse sin ellas.
try:
    from src.knowledge.hybrid_search import Config, Recuperador, consulta_de
except ImportError:  # pragma: no cover
    Config = Recuperador = consulta_de = None

ROOT = Path(__file__).resolve().parents[2]
Retriever = Callable[[QuestionState], List[CanonicalPassage]]


class LegalAgent:
    """Orquesta el grafo: flags -> consulta -> pasajes -> redacción -> validación de fuentes.
    Las citas fuera de los pasajes las resuelve el subagente de búsqueda (`buscador_citas`).
    El juez y su ciclo de reintento se activan con `run_with_judge` (src/agent/graph.py)."""

    def __init__(self, retriever: Optional[Retriever] = None, forzar_mock_escritor: bool = False,
                 buscador_citas: Optional[Buscador] = None):
        """`buscador_citas` busca en el corpus una cita que no está en los pasajes (None = sin
        corpus: esas citas solo se suprimen)."""
        self.retriever = retriever
        self.forzar_mock_escritor = forzar_mock_escritor
        self.buscador_citas = buscador_citas
        self._grafos: dict = {}

    def grafo(self, con_juez: bool = False):
        """Grafo compilado (una vez por agente) con o sin el nodo del juez."""
        if con_juez not in self._grafos:
            self._grafos[con_juez] = construir_grafo(self, con_juez)
        return self._grafos[con_juez]

    def build_state(self, raw_item: dict) -> QuestionState:
        return estado_inicial(raw_item)

    def run(self, raw_item: dict, pasajes: Optional[List[CanonicalPassage]] = None,
            forzar_mock_escritor: Optional[bool] = None) -> QuestionState:
        """Procesa un item. `pasajes` tiene prioridad sobre el retriever; sin ninguno no hay
        pasajes y el borrador resultante es una abstención. `forzar_mock_escritor` (None = el del
        constructor) usa el escritor simulado sin intentar la llamada HTTP al LLM."""
        final = self.grafo().invoke({"raw_item": raw_item, "pasajes": pasajes,
                                     "mock_escritor": forzar_mock_escritor})
        return final["state"]

    @staticmethod
    def to_submission(state: QuestionState) -> dict:
        """Registro conforme a submission.schema.json (sin campos internos de evaluación).

        Cada campo queda con el tipo del esquema (src/agent/salida.py) y las citas
        `[doc_id/art_N]` se reescriben como citas que reconoce el evaluador oficial
        ("artículo N del ..."): ver src/agent/citas.py."""
        borrador = normalizar(dict(state.borrador_respuesta or {}), state.formato, state.opciones)
        borrador = sin_encabezados(borrador_con_citas_legibles(borrador, state.pasajes_recuperados))
        if not state.abstencion:
            borrador = sin_meta_texto(borrador, state.formato)
        if state.formato == "semi_open" and not state.abstencion:
            borrador = respuesta_concisa(borrador, oraciones_semiabierta(state.complejidad))
            borrador = sin_oraciones_accesorias(borrador, state.pregunta, state.sub_tarea, state.complejidad)
        if state.formato == "open_ended" and not state.abstencion:
            borrador = abierta_concisa(borrador, largo=writer_tool.LARGO_OFICIAL)
            borrador = con_fuentes_abiertas(borrador, state.pasajes_recuperados)
        if not state.abstencion:
            borrador = con_normas_consultadas(borrador, state.formato, state.pasajes_recuperados)
        return {
            "id": state.id,
            "formato": state.formato,
            "abstencion": state.abstencion,
            "pasajes_recuperados": [_pasaje_entrega(p) for p in state.pasajes_recuperados],
            **borrador,
        }


def _pasaje_entrega(p: CanonicalPassage) -> dict:
    """Pasaje con los campos del esquema: doc_id y texto literal; inicio y fin (posición en el
    documento del corpus, para reconstruirlo en la verificación en vivo) y score si se conocen."""
    out = {"doc_id": p.doc_id}
    inicio, fin = p.metadatos.get("inicio"), p.metadatos.get("fin")
    if isinstance(inicio, int) and isinstance(fin, int) and 0 <= inicio <= fin:
        out.update(inicio=inicio, fin=fin)
    out["texto"] = p.texto
    if p.score is not None:
        out["score"] = p.score
    return out


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
    # Ganador del banco de pruebas (evaluation/retrieval_benchmark): qwen3-emb-0.6b + BM25 con raíces
    # + bge-reranker-v2-m3 con el perfil "completo" (valores por defecto de Config).
    bm25_path, denso_path = indices / "bm25_todo", indices / "qwen3-emb-0.6b_todo"
    bm25_path = bm25_path if bm25_path.exists() else None
    denso_path = denso_path if (denso_path / "hnsw.faiss").exists() else None
    if bm25_path is None and denso_path is None:
        raise FileNotFoundError(f"No hay índices en {indices}")
    # RAG_DEVICE_DENSO=cpu (en el .env) embebe la consulta en CPU: necesario en GPUs de 4 GB, donde
    # embedder y reranker juntos desbordan la memoria y la búsqueda pasa de 6 s a 60 s. Los pasajes
    # salen idénticos. Vacío = los dos modelos en la GPU (A40).
    # RAG_LIDERES=0 quita el cupo fijo del 1.º de BM25 de normas en cerradas (Config.lideres), para medir
    # si sobra: se puso por la 128 ("Fintech") y nunca mostró beneficio.
    recuperador = Recuperador(bm25_path, denso_path, "bge-reranker-v2-m3",
                              Config(lideres=int(os.environ.get("RAG_LIDERES", "1"))),
                              dispositivo_denso=os.environ.get("RAG_DEVICE_DENSO") or None)

    def hook(consulta) -> List[CanonicalPassage]:
        """`consulta`: dict con "pregunta" (y "opciones" en las cerradas) o texto libre."""
        if isinstance(consulta, dict):
            resultado = recuperador.buscar_item(consulta)
        else:
            resultado = recuperador.buscar(consulta)
        return [
            CanonicalPassage(
                id=p["chunk_id"],
                texto=p["texto"],
                score=p.get("score"),
                metadatos={k: v for k, v in p.items() if k not in ("chunk_id", "texto", "score")},
            )
            for p in resultado.pasajes
        ]

    # Subagente de búsqueda de citas: mismo chunks.sqlite del recuperador, sin cargar nada más.
    hook.buscar_cita = lambda cita: buscar_cita(cita, recuperador.almacen, recuperador._articulo_completo)
    return hook


if __name__ == "__main__":
    ruta = ROOT / "data" / "sample_50.jsonl"
    with open(ruta, encoding="utf-8") as f:
        item = json.loads(f.readline())

    try:
        hook = get_real_retriever()
        # LegalAgent llama al retriever con el QuestionState; el hook recibe el texto de búsqueda
        # (pregunta + opciones en las cerradas).
        agregar = os.environ.get("CITAS_AGREGAR_PASAJES", "0") == "1"  # ver batch_runner.crear_agente
        agente = LegalAgent(lambda s: hook({"pregunta": s.pregunta, "opciones": s.opciones}),
                            buscador_citas=hook.buscar_cita if agregar else None)
        print("Retriever REAL (corpus/indices)")
    except Exception as e:  # índices ausentes, dependencias RAG o modelos no disponibles
        print(f"Retriever real no disponible ({type(e).__name__}: {e}); se usa mock_retriever")
        agente = LegalAgent(mock_retriever)

    estado = agente.run(item)
    print("FLAGS:", json.dumps({k: getattr(estado, k) for k in _FLAG_KEYS}, ensure_ascii=False, indent=2))
    print("RESPUESTA:", json.dumps(estado.borrador_respuesta, ensure_ascii=False, indent=2))
