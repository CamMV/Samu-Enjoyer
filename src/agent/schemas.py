"""Esquemas Pydantic del agente RAG jurídico."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Formato = Literal["multiple_choice", "semi_open", "open_ended"]


class CanonicalPassage(BaseModel):
    """Pasaje recuperado con ID canónico `<doc_id>/art_<N>`."""

    id: str = Field(description="ID canónico, ej: ley_1564_2012/art_42")
    texto: str = Field(description="Texto literal del pasaje")
    metadatos: Dict[str, Any] = Field(
        default_factory=dict,
        description="Front-matter del documento; debe incluir 'vigencia'",
    )
    score: Optional[float] = Field(default=None, description="Puntaje del recuperador/reranker")

    @property
    def doc_id(self) -> str:
        return self.id.split("/", 1)[0]


class QuestionState(BaseModel):
    """Estado completo de una pregunta a lo largo del ciclo del agente."""

    # --- Campos crudos del jsonl (llaves de sample_50.jsonl) ---
    id: int
    formato: Formato
    area: Optional[str] = None
    tema: Optional[str] = None
    complejidad: Optional[str] = None
    sub_tarea: Optional[str] = None
    pregunta: str = Field(description="Enunciado de la pregunta (llave 'pregunta' del jsonl)")
    opciones: Optional[Dict[str, str]] = Field(default=None, description="Opciones A-D (solo multiple_choice)")
    legal_basis: Optional[str] = None
    respuesta_correcta: Optional[str] = None
    texto_respuesta_correcta: Optional[str] = None

    # --- Memoria del ciclo ---
    ciclo_actual: int = 1
    max_ciclos: int = 2

    # --- Recuperación ---
    queries_generadas: List[str] = Field(default_factory=list)
    pasajes_recuperados: List[CanonicalPassage] = Field(default_factory=list)

    # --- Salida y evaluación ---
    borrador_respuesta: Optional[Dict[str, Any]] = None
    citas_invalidas: List[str] = Field(default_factory=list)
    busqueda_citas: List[Dict[str, Any]] = Field(
        default_factory=list, description="Informe del subagente de búsqueda de citas (agregada / suprimida)")
    juez_feedback: Optional[str] = None
    aprobado_por_juez: Optional[bool] = None
    abstencion: bool = False
