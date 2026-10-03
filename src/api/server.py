"""Back local de la interfaz (interfaz/): expone el agente por HTTP.

    python -m src.api.server                     # http://127.0.0.1:8000 (índices reales + LLM local)
    python -m src.api.server --mock              # pasajes y escritor simulados: sin índices ni LLM
    python -m src.api.server --port 8000 --host 127.0.0.1

Endpoints (contrato en interfaz/src/api/types.ts):
    GET  /api/salud                  estado: modo (real/mock), LLM configurado, corpus disponible
    POST /api/preguntar              {"pregunta": "..."} -> registro de submissions.jsonl + datos para la UI
    GET  /api/documentos/{doc_id}    documento completo del corpus (front-matter + Markdown)

Es la misma configuración que la entrega: el agente se arma con `batch_runner.crear_agente` y la
respuesta sale de `LegalAgent.to_submission`, así que una pregunta del test enviada con su `id`,
`formato` y `opciones` da el mismo registro que `submissions.jsonl`. Las peticiones se atienden de a
una (candado): llama-server corre con `-np 1` y el agente no tiene memoria entre preguntas.

Todo es local: el servidor escucha en 127.0.0.1 y el agente solo habla con el LLM de LLM_BASE_URL
(writer_tool rechaza hosts de terceros).
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import re
import sqlite3
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.agent.agent import LegalAgent
from src.agent.batch_runner import FORMATOS, crear_agente
from src.agent.salida import normalizar
from src.agent.schemas import CanonicalPassage

ROOT = Path(__file__).resolve().parents[2]
MD = ROOT / "corpus" / "md"
SQLITE = ROOT / "corpus" / "chunks" / "chunks.sqlite"
DOC_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,200}$")
CAMPOS_DOC = ("titulo", "tipo_norma", "numero", "anio", "vigencia", "fuente")


# ------------------------------------------------------------------ pregunta en texto libre

# "A) …", "a) …", "(A) …" o "A. …" al inicio de línea o tras un espacio.
_MARCA = re.compile(r"(?:^|(?<=\s))(?:\(([A-Da-d])\)|([A-Da-d])\)|([A-D])\.)\s+")


def separar_opciones(texto: str) -> tuple[str, Optional[Dict[str, str]]]:
    """Enunciado y opciones de una cerrada escrita en un solo texto ("… A) Ley 1564 B) Ley 270 …").
    Exige las marcas A, B y C (D opcional) en orden; si no las hay, el texto es la pregunta entera."""
    letras, marcas = "ABCD", []
    for m in _MARCA.finditer(texto):
        letra = next(g for g in m.groups() if g).upper()
        if len(marcas) < 4 and letra == letras[len(marcas)]:
            marcas.append(m)
    if len(marcas) < 3 or not texto[:marcas[0].start()].strip():
        return texto.strip(), None
    opciones = {}
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        opcion = texto[m.end():fin].strip()
        if not opcion:
            return texto.strip(), None
        opciones[letras[i]] = opcion
    return texto[:marcas[0].start()].strip(), opciones


class Pregunta(BaseModel):
    """Solo `pregunta` es obligatoria. Los demás campos permiten mandar un item del banco tal cual
    (p. ej. para comparar con submissions.jsonl); si faltan, el agente los infiere (flags_tool)."""

    pregunta: str = Field(min_length=1, max_length=20_000)
    id: Optional[int] = None
    formato: Optional[str] = None
    opciones: Optional[Dict[str, str]] = None
    area: Optional[str] = None
    tema: Optional[str] = None
    complejidad: Optional[str] = None
    sub_tarea: Optional[str] = None


_ids = itertools.count(1)


def item_de(p: Pregunta) -> dict:
    pregunta, opciones = p.pregunta, p.opciones
    if not opciones and p.formato in (None, "multiple_choice"):
        pregunta, opciones = separar_opciones(pregunta)
    item = {"id": p.id if p.id is not None else next(_ids), "pregunta": pregunta}
    if opciones:
        item["opciones"] = opciones
    for k in ("formato", "area", "tema", "complejidad", "sub_tarea"):
        if getattr(p, k):
            item[k] = getattr(p, k)
    return item


# ------------------------------------------------------------------ metadatos del corpus

class Corpus:
    """Lectura de chunks.sqlite (si existe) para los metadatos de cada pasaje y los documentos."""

    def __init__(self, ruta: Path = SQLITE):
        self.db = (sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, check_same_thread=False)
                   if ruta.is_file() else None)

    def chunk(self, chunk_id: str) -> Optional[dict]:
        if self.db is None:
            return None
        fila = self.db.execute("SELECT datos FROM chunks WHERE chunk_id = ?", (chunk_id,)).fetchone()
        return json.loads(fila[0]) if fila else None

    def primero(self, doc_id: str) -> Optional[dict]:
        if self.db is None:
            return None
        fila = self.db.execute("SELECT datos FROM chunks WHERE doc_id = ? ORDER BY rowid LIMIT 1",
                               (doc_id,)).fetchone()
        return json.loads(fila[0]) if fila else None

    def textos(self, doc_id: str) -> list[dict]:
        if self.db is None:
            return []
        filas = self.db.execute("SELECT datos FROM chunks WHERE doc_id = ? ORDER BY rowid", (doc_id,))
        return [json.loads(d) for (d,) in filas]


def _titulo(texto: str) -> Optional[str]:
    """Encabezado citable del pasaje: su primera línea, sin la marca de vigencia."""
    linea = texto.split("\n", 1)[0].strip()
    return re.sub(r"\s*\[vigencia:[^\]]*\]\s*$", "", linea) or None


def pasaje_ui(p: CanonicalPassage, entrega: dict, corpus: Corpus) -> dict:
    """El pasaje de submissions.jsonl más chunk_id, encabezado, vigencia y tipo de norma."""
    meta = corpus.chunk(p.id) or corpus.primero(p.doc_id) or {}
    out = {"chunk_id": p.id, **entrega, "titulo": _titulo(p.texto)}
    for k in ("vigencia", "tipo_norma", "tipo_chunk"):
        v = p.metadatos.get(k) or meta.get(k)
        if v:
            out[k] = v
    return out


# ------------------------------------------------------------------ aplicación

class Estado:
    agente: Optional[LegalAgent] = None
    modo: str = "sin cargar"
    corpus: Optional[Corpus] = None
    candado = threading.Lock()


def _aviso_puertos(puerto_api: int) -> None:
    llm = os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1")
    u = urlparse(llm)
    if u.hostname in ("localhost", "127.0.0.1", "0.0.0.0") and (u.port or 80) == puerto_api:
        print(f"!! LLM_BASE_URL ({llm}) usa el mismo puerto que este servidor ({puerto_api}). Arrancar "
              f"llama-server en otro puerto (p. ej. 8010) y ajustar LLM_BASE_URL en .env.", flush=True)


def crear_app(mock: bool = False) -> FastAPI:
    @asynccontextmanager
    async def ciclo(app: FastAPI):
        t0 = time.perf_counter()
        print(f"== cargando el agente ({'mock' if mock else 'índices reales'})…", flush=True)
        Estado.agente, Estado.modo = crear_agente(mock)
        Estado.corpus = Corpus()
        print(f"== listo en {time.perf_counter() - t0:.1f} s (modo {Estado.modo})", flush=True)
        yield

    app = FastAPI(title="Samu-Enjoyer", version="1.0", lifespan=ciclo)
    # El front (Vite, puerto 3000) pasa por su proxy; CORS solo cubre abrirlo sin proxy en la misma máquina.
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.get("/api/salud")
    def salud() -> dict:
        return {"ok": Estado.agente is not None, "modo": Estado.modo,
                "llm": os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1"),
                "chunks_sqlite": SQLITE.is_file(), "ocupado": Estado.candado.locked()}

    @app.post("/api/preguntar")
    def preguntar(p: Pregunta) -> dict:
        if p.formato is not None and p.formato not in FORMATOS:
            raise HTTPException(422, f"formato inválido: {p.formato} (use {', '.join(FORMATOS)})")
        item = item_de(p)
        t0 = time.perf_counter()
        with Estado.candado:  # una pregunta a la vez, como batch_runner
            try:
                estado = Estado.agente.run(item)
                registro = LegalAgent.to_submission(estado)
            except Exception as e:
                raise HTTPException(500, f"El agente falló: {type(e).__name__}: {e}") from e
        entregados = registro["pasajes_recuperados"]
        registro["pasajes_recuperados"] = [pasaje_ui(p, e, Estado.corpus)
                                           for p, e in zip(estado.pasajes_recuperados, entregados)]
        if estado.opciones:
            registro["opciones"] = estado.opciones
        if estado.borrador_respuesta and not estado.abstencion:
            # Campos con los IDs canónicos [doc_id/art_N]: el front numera las citas y las enlaza.
            registro["borrador"] = normalizar(dict(estado.borrador_respuesta), estado.formato, estado.opciones)
        registro["latencia_ms"] = round((time.perf_counter() - t0) * 1000)
        return registro

    @app.get("/api/documentos/{doc_id}")
    def documento(doc_id: str) -> dict:
        if not DOC_ID.match(doc_id):
            raise HTTPException(404, f"doc_id inválido: {doc_id}")
        ruta = MD / f"{doc_id}.md"
        if ruta.is_file():
            from src.knowledge.chunking import leer_md
            meta, cuerpo, _ = leer_md(ruta)
            return {"doc_id": doc_id, **{k: meta[k] for k in CAMPOS_DOC if meta.get(k) not in (None, "")},
                    "markdown": cuerpo}
        # Sin corpus/md (el zip del índice no lo trae): el documento se arma con sus chunks en orden.
        chunks = Estado.corpus.textos(doc_id) if Estado.corpus else []
        if not chunks:
            raise HTTPException(404, f"No se encontró el documento «{doc_id}» en el corpus.")
        meta = chunks[0]
        return {"doc_id": doc_id, **{k: meta[k] for k in CAMPOS_DOC if meta.get(k) not in (None, "")},
                "markdown": "\n\n".join(c["texto"] for c in chunks)}

    return app


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--mock", action="store_true", help="pasajes y escritor simulados, sin índices ni LLM")
    args = ap.parse_args()
    _aviso_puertos(args.port)
    import uvicorn
    uvicorn.run(crear_app(args.mock), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
