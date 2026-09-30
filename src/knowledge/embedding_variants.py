"""Modelos abiertos del sistema: embedders (índice HNSW) y rerankers.

Todos caben en el portátil del equipo (RTX 3050 Ti de 4 GB): la A40 construye el
índice y corre las ~992 preguntas, pero la verificación en vivo regenera respuestas en
el portátil, así que lo que corre por consulta tiene que caber y dar lo mismo en los dos.

Cada embedder declara cómo se le presenta la consulta: E5 y Qwen3 esperan una
instrucción; bge-m3 no usa prefijos. Omitirlos degrada la recuperación en silencio.
"""
from __future__ import annotations

from dataclasses import dataclass

TAREA = ("Dada una pregunta de derecho colombiano, recupera los artículos de normas o los "
         "fragmentos de sentencias que la responden")


@dataclass(frozen=True)
class Embedder:
    clave: str
    hf: str
    dim: int
    max_tokens: int
    prefijo_consulta: str = ""
    prefijo_pasaje: str = ""


EMBEDDERS = {
    "bge-m3": Embedder("bge-m3", "BAAI/bge-m3", 1024, 1024),
    "qwen3-emb-0.6b": Embedder("qwen3-emb-0.6b", "Qwen/Qwen3-Embedding-0.6B", 1024, 1024,
                               prefijo_consulta=f"Instruct: {TAREA}\nQuery: "),
    "e5-large-instruct": Embedder("e5-large-instruct", "intfloat/multilingual-e5-large-instruct", 1024, 512,
                                  prefijo_consulta=f"Instruct: {TAREA}\nQuery: "),
}


@dataclass(frozen=True)
class Reranker:
    clave: str
    hf: str
    tipo: str          # "cross" (CrossEncoder) o "qwen3" (LLM que responde yes/no)
    max_tokens: int = 512


RERANKERS = {
    "bge-reranker-v2-m3": Reranker("bge-reranker-v2-m3", "BAAI/bge-reranker-v2-m3", "cross"),
    "qwen3-reranker-0.6b": Reranker("qwen3-reranker-0.6b", "Qwen/Qwen3-Reranker-0.6B", "qwen3"),
}
