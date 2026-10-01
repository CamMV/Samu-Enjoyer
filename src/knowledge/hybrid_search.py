"""Recuperación híbrida para una pregunta: BM25 + HNSW -> RRF -> reranker -> 10 pasajes.

1. Citas expresas: lo que la pregunta cita ("art. 42 del CGP", "C-355 de 2006") se trae
   por id y entra a la fusión como una lista más.
2. BM25 y HNSW, `candidatos` cada uno, fusionados con RRF (k=60).
3. Reranker sobre los `n_rerank` mejores de la fusión.
4. Ajustes: bajan un poco lo derogado y la prioridad baja (p. ej. leyes aprobatorias de
   tratados del nivel 1); máximo `max_por_doc` pasajes por documento; las partes de un
   mismo artículo cuentan una vez.
5. Expansión: una parte de artículo se entrega como el artículo completo.

Todo el orden se desempata por chunk_id: con el mismo índice, el resultado es el mismo
en la A40 y en el portátil (lo exige la verificación en vivo).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .bm25_store import IndiceBM25
from .chunk_store import Almacen
from .vector_store import IndiceDenso
from .citation_lookup import chunks_citados
from .reranker import Reranker

K_RRF = 60


@dataclass
class Config:
    candidatos: int = 100      # por buscador (BM25 y HNSW)
    n_rerank: int = 150        # cuántos de la fusión pasan por el reranker (A40: 0,68 s por pregunta)
    k: int = 10                # pasajes entregados (el evaluador mira los 10 primeros)
    max_por_doc: int = 3
    penal_derogado: float = 0.15
    penal_prioridad_baja: float = 0.05
    usar_citas: bool = True
    expandir_articulo: bool = True
    # Ajustes de orden tras el reranker (el banco de pruebas mostró que preámbulos de
    # decretos, notas del Senado y fichas de tutelas desplazaban a los artículos):
    # Valores por defecto = perfil "completo_150_seccion", el ganador sobre el corpus completo
    # (2,2 M chunks, 50 preguntas): recall_citas@10 0,862 -> 0,898, recall_docs@10 0,439 -> 0,764,
    # MRR 0,236 -> 0,380 y nDCG@10 0,314 -> 0,520 frente a "base".
    penal_tipo: dict = field(default_factory=lambda: {"preambulo": 0.2, "notas": 0.15, "anexo": 0.1,
                                                      "seccion": 0.1})
    bonus_prioridad_alta: float = 0.1                 # normas del seed (las que más usa el banco)
    max_sentencias: int | None = 4                    # tope de pasajes de sentencias entre los k


# Perfiles comparados en el banco de pruebas (evaluation/retrieval_benchmark).
PERFILES = {
    "base": {"penal_tipo": {}, "bonus_prioridad_alta": 0.0, "max_sentencias": None},  # sin ajustes
    "penal": {"penal_tipo": {"preambulo": 0.2, "notas": 0.15, "anexo": 0.1}},
    "penal_bonus": {"penal_tipo": {"preambulo": 0.2, "notas": 0.15, "anexo": 0.1}, "bonus_prioridad_alta": 0.1},
    "penal_tope": {"penal_tipo": {"preambulo": 0.2, "notas": 0.15, "anexo": 0.1}, "max_sentencias": 4},
    "completo": {"penal_tipo": {"preambulo": 0.2, "notas": 0.15, "anexo": 0.1}, "bonus_prioridad_alta": 0.1,
                 "max_sentencias": 4},
    "completo_100": {"penal_tipo": {"preambulo": 0.2, "notas": 0.15, "anexo": 0.1}, "bonus_prioridad_alta": 0.1,
                     "max_sentencias": 4, "n_rerank": 100},
}
# Variantes para el corpus completo (2,2 M chunks): las ventanas de sentencias ("seccion")
# desplazan a las normas más que en el banco de prueba.
_COMPLETO = PERFILES["completo"]
PERFILES.update({
    "completo_s3": {**_COMPLETO, "max_sentencias": 3},
    "completo_s2": {**_COMPLETO, "max_sentencias": 2},
    "completo_seccion": {**_COMPLETO, "penal_tipo": {**_COMPLETO["penal_tipo"], "seccion": 0.1}},
    "completo_c200": {**_COMPLETO, "candidatos": 200},
    "completo_c200_100": {**_COMPLETO, "candidatos": 200, "n_rerank": 100},
    # Corpus completo: 100 al reranker sube recall_citas 0,862 -> 0,886; el castigo a "seccion"
    # mejora el orden (MRR 0,294 -> 0,369) sin cambiar el recall. Se combinan.
    "completo_100_seccion": {**_COMPLETO, "n_rerank": 100,
                             "penal_tipo": {**_COMPLETO["penal_tipo"], "seccion": 0.1}},
    "completo_150_seccion": {**_COMPLETO, "n_rerank": 150,
                             "penal_tipo": {**_COMPLETO["penal_tipo"], "seccion": 0.1}},
})


def config_de(perfil: str, **base) -> "Config":
    return Config(**{**base, **PERFILES[perfil]})


@dataclass
class Resultado:
    pasajes: list[dict]
    etapas: dict = field(default_factory=dict)    # chunk_ids por etapa, para evaluar
    tiempos: dict = field(default_factory=dict)


def rrf(listas: list[list[str]], k: int = K_RRF) -> list[tuple[str, float]]:
    puntaje: dict[str, float] = {}
    for lista in listas:
        for pos, cid in enumerate(lista, 1):
            puntaje[cid] = puntaje.get(cid, 0.0) + 1.0 / (k + pos)
    return sorted(puntaje.items(), key=lambda p: (-round(p[1], 8), p[0]))


def consulta_de(item: dict) -> str:
    """Texto de búsqueda: la pregunta y, en las cerradas, sus opciones."""
    q = item.get("pregunta", "").strip()
    if isinstance(item.get("opciones"), dict):
        q += "\n" + "\n".join(f"{k}) {v}" for k, v in sorted(item["opciones"].items()))
    return q


class Recuperador:
    def __init__(self, bm25: Path | None, denso: Path | None, reranker: str | None,
                 config: Config | None = None, almacen: Almacen | None = None, dispositivo: str | None = None):
        self.cfg = config or Config()
        self.almacen = almacen or Almacen()
        self.bm25 = IndiceBM25(bm25) if bm25 else None
        self.denso = IndiceDenso(denso, dispositivo) if denso else None
        self.reranker = Reranker(reranker, dispositivo) if reranker else None

    def buscar(self, consulta: str) -> Resultado:
        cfg, t, etapas = self.cfg, {}, {}
        t0 = time.perf_counter()
        citadas = chunks_citados(consulta, self.almacen) if cfg.usar_citas else []
        t["citas"] = time.perf_counter() - t0

        listas = [citadas] if citadas else []
        if self.bm25:
            t0 = time.perf_counter()
            etapas["bm25"] = [c for c, _ in self.bm25.buscar(consulta, cfg.candidatos)]
            t["bm25"] = time.perf_counter() - t0
            listas.append(etapas["bm25"])
        if self.denso:
            t0 = time.perf_counter()
            etapas["denso"] = [c for c, _ in self.denso.buscar(consulta, cfg.candidatos)]
            t["denso"] = time.perf_counter() - t0
            listas.append(etapas["denso"])
        fusion = rrf(listas)
        etapas["rrf"] = [c for c, _ in fusion]

        pool = [c for c, _ in fusion[:cfg.n_rerank]]
        datos = self.almacen.get(pool)
        pool = [c for c in pool if c in datos]
        if self.reranker:
            t0 = time.perf_counter()
            puntajes = self.reranker.puntuar(consulta, [datos[c]["texto"] for c in pool])
            t["reranker"] = time.perf_counter() - t0
        else:  # sin reranker: el puntaje RRF, reescalado
            maximo = fusion[0][1] if fusion else 1.0
            puntajes = [round(dict(fusion)[c] / maximo, 4) for c in pool]

        ajustados = []
        for cid, s in zip(pool, puntajes):
            d = datos[cid]
            if d.get("derogado") or d.get("vigencia") == "derogada":
                s -= cfg.penal_derogado
            if d.get("prioridad") == "baja":
                s -= cfg.penal_prioridad_baja
            if cid not in citadas:  # lo que la pregunta cita expresamente no se castiga
                s -= cfg.penal_tipo.get(d["tipo_chunk"], 0.0)
                if d.get("prioridad") == "alta" and d.get("tipo_documento") != "sentencia":
                    s += cfg.bonus_prioridad_alta
            ajustados.append((cid, round(s, 4)))
        ajustados.sort(key=lambda p: (-p[1], p[0]))
        etapas["rerank"] = [c for c, _ in ajustados]

        t0 = time.perf_counter()
        pasajes = self._seleccionar(ajustados, datos, set(citadas))
        t["seleccion"] = time.perf_counter() - t0
        etapas["final"] = [p["chunk_id"] for p in pasajes]
        return Resultado(pasajes, etapas, {k: round(v, 3) for k, v in t.items()})

    def _seleccionar(self, ajustados: list[tuple[str, float]], datos: dict,
                     citadas: set[str] = frozenset()) -> list[dict]:
        cfg, elegidos, por_doc, articulos, n_sent, diferidos = self.cfg, [], {}, set(), 0, []

        def tomar(cid: str, s: float) -> bool:
            d = datos[cid]
            unidad = d.get("articulo_id") if d["tipo_chunk"] in ("articulo", "parte_articulo") else cid
            if unidad in articulos or por_doc.get(d["doc_id"], 0) >= cfg.max_por_doc:
                return False
            articulos.add(unidad)
            por_doc[d["doc_id"]] = por_doc.get(d["doc_id"], 0) + 1
            elegidos.append((cid, s))
            return True

        for cid, s in ajustados:
            if len(elegidos) == cfg.k:
                break
            es_sentencia = datos[cid].get("tipo_documento") == "sentencia"
            if es_sentencia and cfg.max_sentencias is not None and n_sent >= cfg.max_sentencias \
                    and cid not in citadas:
                diferidos.append((cid, s))  # vuelven solo si no alcanza para k pasajes
                continue
            n_sent += tomar(cid, s) and es_sentencia
        for cid, s in diferidos:
            if len(elegidos) == cfg.k:
                break
            tomar(cid, s)
        elegidos.sort(key=lambda p: (-p[1], p[0]))

        out = []
        for cid, s in elegidos:
            d = datos[cid]
            texto, pid = d["texto"], cid
            if cfg.expandir_articulo and d["tipo_chunk"] == "parte_articulo":
                texto, pid = self._articulo_completo(d), d["articulo_id"]
            out.append({"doc_id": d["doc_id"], "chunk_id": pid, "texto": texto, "score": s,
                        "inicio": d.get("inicio"), "fin": d.get("fin"), "tipo_chunk": d["tipo_chunk"]})
        return out

    def _articulo_completo(self, d: dict) -> str:
        partes = [c for c in self.almacen.por("articulo_id", d["articulo_id"]) if c["tipo_chunk"] == "parte_articulo"]
        partes.sort(key=lambda c: c.get("parte", 0))
        if not partes:
            return d["texto"]
        cabeza = partes[0]["texto"].split("\n", 2)
        # Encabezado de la primera parte (sin "(parte 1 de n)") + cuerpos de todas.
        titulo = "\n".join(cabeza[:2]).replace(f" (parte 1 de {len(partes)})", "")
        cuerpos = [c["texto"].split("\n", 2)[2] if c["texto"].count("\n") >= 2 else "" for c in partes]
        return titulo + "\n" + "\n\n".join(cuerpos)
