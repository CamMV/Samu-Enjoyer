"""Firmas del pipeline del agente RAG (sin implementación)."""
from __future__ import annotations

from typing import List

from src.agent.schemas import CanonicalPassage, QuestionState


def parse_and_flag_input(raw_item: dict) -> QuestionState:
    """Convierte un item crudo de sample_50.jsonl (o de la UI) en un `QuestionState`.

    Detecta el formato (multiple_choice / semi_open / open_ended) y deja el
    estado inicial con ciclo_actual=1 y max_ciclos=2.
    """
    ...


def build_search_queries(state: QuestionState) -> List[str]:
    """Genera las consultas de recuperación.

    Cerradas: pregunta + opciones A-D, determinista y sin LLM.
    Abiertas/semiabiertas: query rewriter con términos jurídicos y normas
    candidatas, incorporando `juez_feedback` si ciclo_actual > 1.
    """
    ...


def retrieve_top_k(queries: List[str], k: int = 10) -> List[CanonicalPassage]:
    """Recuperación híbrida (BM25 + densa bge-m3 + RRF + reranker bge-reranker-v2-m3).

    Devuelve los `k` mejores pasajes con ID canónico `<doc_id>/art_<N>` y
    metadatos de vigencia.
    """
    ...


def generate_draft_response(state: QuestionState) -> dict:
    """Redacta el borrador con Qwen3-8B (temperature=0) usando EXCLUSIVAMENTE
    `state.pasajes_recuperados`. La estructura del dict depende del formato
    según submission.schema.json.
    """
    ...


def validate_citations_deterministically(
    draft: dict, passages: List[CanonicalPassage]
) -> tuple[bool, List[str]]:
    """Validación sin LLM: extrae las citas del borrador, las mapea a IDs
    canónicos y verifica que existan entre `passages`.

    Returns:
        (todas_validas, citas_invalidas).
    """
    ...


def evaluate_with_judge(state: QuestionState) -> tuple[bool, str]:
    """LLM-as-Judge (modelo abierto): evalúa si el borrador responde la
    sub-tarea, si cada afirmación está soportada por un pasaje y si es
    coherente con el área jurídica.

    Returns:
        (aprobado, feedback) para reintentar la consulta en el ciclo 2.
    """
    ...
