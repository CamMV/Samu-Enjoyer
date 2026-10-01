"""Lectura de corpus/chunks: textos en orden fijo y metadatos por chunk_id.

El orden de corpus/chunks/chunks.jsonl (documentos por doc_id y chunks en orden de
lectura) define la posición de cada chunk en BM25 y en HNSW: los dos índices
guardan la lista de chunk_id en ese orden (`ids.json`).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[2]
CHUNKS = ROOT / "corpus" / "chunks"
INDICES = ROOT / "corpus" / "indices"

def es_sentencia(c: dict) -> bool:
    """Igual que el chunking: algunas sentencias no traen tipo_documento en el front-matter."""
    return c.get("tipo_documento") == "sentencia" or c["doc_id"].startswith("jurisprudencia_")


SELECCIONES = {
    "todo": lambda c: True,
    # Subcorpus para comparar modelos rápido: normas completas + fichas de sentencias.
    "normas_fichas": lambda c: c.get("tipo_documento") != "sentencia" or c["tipo_chunk"] == "ficha",
    # Solo normas: lista aparte en la fusión para que las sentencias (~85 % del corpus) no las entierren.
    "normas": lambda c: not es_sentencia(c),
}


def leer_chunks(seleccion: str = "todo", limite: int | None = None,
                ruta: Path = CHUNKS / "chunks.jsonl") -> Iterator[dict]:
    filtro = SELECCIONES[seleccion]
    n = 0
    with ruta.open(encoding="utf-8") as f:
        for linea in f:
            c = json.loads(linea)
            if filtro(c):
                yield c
                n += 1
                if limite and n >= limite:
                    return


class Almacen:
    """Metadatos y texto de cada chunk (chunks.sqlite), para el reranker, la expansión y la salida."""

    def __init__(self, ruta: Path = CHUNKS / "chunks.sqlite"):
        self.db = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, check_same_thread=False)

    def get(self, ids: list[str]) -> dict[str, dict]:
        out = {}
        for i in range(0, len(ids), 500):
            parte = ids[i:i + 500]
            q = f"SELECT chunk_id, datos FROM chunks WHERE chunk_id IN ({','.join('?' * len(parte))})"
            out.update({cid: json.loads(d) for cid, d in self.db.execute(q, parte)})
        return out

    def por(self, campo: str, valor: str) -> list[dict]:
        assert campo in ("doc_id", "articulo_id", "seccion_id")
        filas = self.db.execute(f"SELECT datos FROM chunks WHERE {campo} = ? ORDER BY rowid", (valor,))
        return [json.loads(d) for (d,) in filas]
