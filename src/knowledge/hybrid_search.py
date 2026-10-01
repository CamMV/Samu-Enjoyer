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

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .bm25_store import IndiceBM25
from .chunk_store import Almacen, es_sentencia
from .vector_store import IndiceDenso
from .citation_lookup import chunks_citados, documentos_citados
from .reranker import Reranker

K_RRF = 60
# "$30.000.000", "30.000.000 COP", "1.500.000 pesos": montos de un millón o más.
_PESOS_RE = re.compile(r"\$\s*\d{1,3}(?:[.,]\d{3}){2,}|\b\d{1,3}(?:[.,]\d{3}){2,}\s*(?:COP|pesos)\b", re.I)


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
    # Valores por defecto = perfil "ganador_dedup70", el ganador sobre el corpus completo
    # (2,2 M chunks, 50 preguntas): recall_citas@10 0,862 -> 0,919, recall_docs@10 0,439 -> 0,809,
    # MRR 0,236 -> 0,419 y nDCG@10 0,314 -> 0,561 frente a "base".
    penal_tipo: dict = field(default_factory=lambda: {"preambulo": 0.2, "notas": 0.15, "anexo": 0.1,
                                                      "seccion": 0.1})
    bonus_prioridad_alta: float = 0.1                 # normas del seed (las que más usa el banco)
    max_sentencias: int | None = 4                    # tope de pasajes de sentencias entre los k
    # Lista de normas: BM25 y HNSW sobre solo normas (índices <x>_normas junto a los de todo),
    # `normas` candidatos de cada uno como listas extra en el RRF. 0 = no se usa.
    # Con 50: recall_citas@10 0,898 -> 0,919, recall_docs@10 0,764 -> 0,785, MRR 0,380 -> 0,416.
    normas: int = 50
    # Cerradas: además de pregunta + todas las opciones, una búsqueda (BM25 y HNSW) por cada
    # "pregunta + opción X", con `por_opcion` candidatos cada una, como listas extra en el RRF: lo
    # que distingue a una opción (p. ej. "Fintech") no se diluye entre las cuatro. 0 = no se usa.
    por_opcion: int = 0
    # Seguir las citas (rewriter determinista, sin LLM): de los `seguir_desde` primeros de la fusión
    # se extraen las normas que citan (extractor del evaluador oficial) y los `seguir_citas`
    # artículos más citados entran como otra lista en el RRF. Ataca el caso típico de las
    # abiertas: llegan sentencias que mencionan el artículo, pero no el artículo. 0 = no se usa.
    seguir_citas: int = 0
    seguir_desde: int = 20
    # Quitar casi duplicados del top-k: un pasaje que no es artículo de norma y comparte >= `dedup`
    # de su texto (secuencias de 5 palabras) con uno ya elegido se salta y su lugar lo toma el
    # siguiente distinto. En las 50 de muestra, 65 de 500 pasajes repetían a otro (sentencias que
    # copian el mismo párrafo, notas que transcriben la norma). 0 = no se usa.
    # Con 0,7: recall_docs@10 0,785 -> 0,809, MRR 0,416 -> 0,419, nDCG 0,552 -> 0,561; recall_citas
    # igual (0,919); sin costo de tiempo. Con 0,5 da lo mismo.
    dedup: float = 0.7
    # Normas citadas sin artículo ("¿qué regula la Ley 1564...?", opciones que son leyes): los
    # `en_citadas` mejores chunks de cada una, con BM25 y denso restringidos a esa norma, entran como
    # listas extra en el RRF. Sin esto la norma citada compite con todo el corpus y puede no llegar
    # ni a los 150 candidatos. Hasta `max_citadas` normas por pregunta. 0 = no se usa.
    en_citadas: int = 0
    max_citadas: int = 6
    # Cerradas: una consulta con SOLO el texto de las opciones (sin la pregunta) sobre las normas,
    # `solo_opciones` candidatos de BM25 y de HNSW: cuando las opciones son conceptos jurídicos
    # ("falsa motivación", "desviación de poder") apuntan al artículo que los define. 0 = no se usa.
    solo_opciones: int = 0
    # Cerradas: el reranker puntúa cada candidato contra "pregunta + opción X" para cada opción y se
    # queda con el máximo (y el de la consulta completa): lo que solo respalda a una opción ("Fintech")
    # no se diluye entre las cuatro. Cuesta un reranker por opción.
    rerank_opciones: bool = False
    # Montos en pesos: los umbrales legales (cuantías, multas, topes) están en salarios mínimos, así
    # que si la pregunta trae un monto en pesos entra, con un lugar asegurado entre los k, el artículo
    # del decreto más reciente del corpus que fija el salario mínimo mensual legal.
    # En las 50 de muestra solo cambia la 528 (entra el art. 1 del Decreto 1572 de 2024 en lugar de una
    # nota del CPC); recall_citas, recall_docs, MRR y nDCG iguales.
    smlmv: bool = True
    # Mezcla final: al puntaje del reranker se suma `peso_fusion` x (puntaje RRF / el mejor RRF), para
    # que lo que BM25 y el denso ponen arriba no dependa solo del reranker (p. ej. "Fintech": 1.º en
    # BM25, puesto 48 tras el reranker). 0 = solo el reranker.
    peso_fusion: float = 0.0
    # Una sola ventana por sección de sentencia: las ventanas de ~1.700 caracteres de una misma sección
    # cuentan como una unidad (igual que las partes de un artículo) y entra la mejor puntuada; el lugar
    # de las demás lo toma otra fuente. En las 50 de muestra, 21 de 500 pasajes eran otra ventana de una
    # sección ya elegida.
    una_ventana: bool = False
    # Cupo para los líderes: los `lideres` primeros de cada buscador (BM25, HNSW y sus listas de normas)
    # entran al top-k aunque el reranker los baje (p. ej. "Fintech": 1.º en BM25 de normas, puesto 48
    # tras el reranker). Respetan los topes por documento y de sentencias. 0 = no se usa.
    lideres: int = 0


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
_GANADOR = PERFILES["completo_150_seccion"]
PERFILES.update({
    # Un tope de 2 pasajes por documento no cambió el recall. El diagnóstico mostró los
    # códigos y la Constitución en las posiciones 100-900 de BM25 y HNSW, enterrados por
    # sentencias: lista aparte sobre solo normas.
    "ganador_normas50": {**_GANADOR, "normas": 50},
    "ganador_normas100": {**_GANADOR, "normas": 100},
})
_NORMAS50 = PERFILES["ganador_normas50"]
PERFILES.update({
    # Búsqueda por opción en las cerradas y seguimiento de citas (ver Config).
    "ganador_opciones": {**_NORMAS50, "por_opcion": 50},
    "ganador_citas": {**_NORMAS50, "seguir_citas": 10},
    "ganador_ambas": {**_NORMAS50, "por_opcion": 50, "seguir_citas": 10},
    # Sin casi duplicados en el top-10 (ver Config.dedup).
    "ganador_dedup50": {**_NORMAS50, "dedup": 0.5},
    "ganador_dedup70": {**_NORMAS50, "dedup": 0.7},
})


def _hermano(ruta: Path) -> Path:
    """corpus/indices/bm25_todo -> bm25_normas; qwen3-emb-0.6b_todo -> qwen3-emb-0.6b_normas."""
    return ruta.with_name(ruta.name.rsplit("_", 1)[0] + "_normas")


def config_de(perfil: str, **base) -> "Config":
    # Los perfiles sin "normas" o sin "dedup" se midieron sin esas opciones: así se siguen reproduciendo.
    return Config(**{"normas": 0, "dedup": 0.0, **base, **PERFILES[perfil]})


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


def tejas(texto: str, n: int = 5) -> set[str]:
    """Secuencias de `n` palabras del cuerpo del pasaje (sin la línea del encabezado)."""
    cuerpo = texto.split("\n", 1)[1] if "\n" in texto else texto
    w = re.findall(r"\w+", cuerpo.lower())
    return {" ".join(w[i:i + n]) for i in range(max(len(w) - n + 1, 1))}


def contencion(a: set, b: set) -> float:
    """Fracción del más corto de los dos que está contenida en el otro."""
    return len(a & b) / max(min(len(a), len(b)), 1)


def consulta_de(item: dict) -> str:
    """Texto de búsqueda: la pregunta y, en las cerradas, sus opciones."""
    q = item.get("pregunta", "").strip()
    if isinstance(item.get("opciones"), dict):
        q += "\n" + "\n".join(f"{k}) {v}" for k, v in sorted(item["opciones"].items()))
    return q


class Recuperador:
    def __init__(self, bm25: Path | None, denso: Path | None, reranker: str | None,
                 config: Config | None = None, almacen: Almacen | None = None, dispositivo: str | None = None,
                 dispositivo_denso: str | None = None):
        """dispositivo_denso: dónde se embebe la consulta (por defecto, el mismo del reranker). En el
        portátil de 4 GB va en "cpu": con los dos modelos en la GPU, Windows desborda la memoria a la
        RAM y el reranker pasa de 3,6 s a 59 s; los pasajes salen idénticos (50/50 contra la A40)."""
        self.cfg = config or Config()
        self.almacen = almacen or Almacen()
        self.bm25 = IndiceBM25(bm25) if bm25 else None
        self.denso = IndiceDenso(denso, dispositivo_denso or dispositivo) if denso else None
        self.reranker = Reranker(reranker, dispositivo) if reranker else None
        self.bm25_normas = self.denso_normas = None
        if self.cfg.normas:
            if bm25:
                self.bm25_normas = IndiceBM25(_hermano(bm25))
            if denso:
                self.denso_normas = IndiceDenso(_hermano(denso), dispositivo)
                assert self.denso_normas.info["modelo"] == self.denso.info["modelo"]

    def buscar_item(self, item: dict) -> Resultado:
        """Búsqueda para una pregunta (dict con "pregunta" y, en las cerradas, "opciones")."""
        opciones = item.get("opciones") if isinstance(item.get("opciones"), dict) else {}
        pregunta = item.get("pregunta", "").strip()
        extras = [(k, f"{pregunta}\n{k}) {v}") for k, v in sorted(opciones.items())]
        return self.buscar(consulta_de(item), extras, opciones, pregunta)

    def buscar(self, consulta: str, extras: list[tuple[str, str]] = (), opciones: dict | None = None,
               pregunta: str | None = None) -> Resultado:
        """`extras`: (nombre, consulta) por opción ("pregunta + opción X"); con `por_opcion` cada una
        aporta su lista de BM25 y de HNSW a la fusión, y con `rerank_opciones` el reranker también
        puntúa contra cada una. `opciones`: las de la cerrada (para `solo_opciones`). `pregunta`: el
        enunciado sin opciones, con el que se busca dentro de las normas citadas."""
        cfg, t, etapas = self.cfg, {}, {}
        t0 = time.perf_counter()
        citadas = chunks_citados(consulta, self.almacen) if cfg.usar_citas else []
        t["citas"] = time.perf_counter() - t0

        forzados = list(self._decreto_smlmv()) if cfg.smlmv and _PESOS_RE.search(consulta) else []
        etapas["forzados"] = forzados
        listas = [citadas] if citadas else []
        if self.bm25:
            t0 = time.perf_counter()
            etapas["bm25"] = [c for c, _ in self.bm25.buscar(consulta, cfg.candidatos)]
            t["bm25"] = time.perf_counter() - t0
            listas.append(etapas["bm25"])
        if self.denso:
            t0 = time.perf_counter()
            v = self.denso.vector(consulta)
            etapas["denso"] = [c for c, _ in self.denso.buscar_vector(v, cfg.candidatos)]
            t["denso"] = time.perf_counter() - t0
            listas.append(etapas["denso"])
        if self.bm25_normas or self.denso_normas:
            t0 = time.perf_counter()
            if self.bm25_normas:
                etapas["bm25_normas"] = [c for c, _ in self.bm25_normas.buscar(consulta, cfg.normas)]
                listas.append(etapas["bm25_normas"])
            if self.denso_normas:
                etapas["denso_normas"] = [c for c, _ in self.denso_normas.buscar_vector(v, cfg.normas)]
                listas.append(etapas["denso_normas"])
            t["normas"] = time.perf_counter() - t0
        if extras and cfg.por_opcion:
            t0 = time.perf_counter()
            for nombre, q in extras:
                if self.bm25:
                    etapas[f"opcion_{nombre}_bm25"] = [c for c, _ in self.bm25.buscar(q, cfg.por_opcion)]
                    listas.append(etapas[f"opcion_{nombre}_bm25"])
                if self.denso:
                    vq = self.denso.vector(q)
                    etapas[f"opcion_{nombre}_denso"] = [c for c, _ in self.denso.buscar_vector(vq, cfg.por_opcion)]
                    listas.append(etapas[f"opcion_{nombre}_denso"])
            t["opciones"] = time.perf_counter() - t0
        if cfg.en_citadas:
            t0 = time.perf_counter()
            # Las normas se toman de la consulta completa (también las que nombran las opciones); dentro
            # de cada una se busca con el enunciado solo: las demás opciones serían ruido.
            normas_citadas = self._citadas_sin_articulo(consulta)
            q = pregunta or consulta
            vq = None
            if normas_citadas and self.denso:
                vq = v if q == consulta else self.denso.vector(q)
            for did in normas_citadas:
                for nombre, lista in self._dentro_de(did, q, vq).items():
                    etapas[f"citada_{did}_{nombre}"] = lista
                    listas.append(lista)
            t["citadas"] = time.perf_counter() - t0
        if cfg.solo_opciones and opciones:
            t0 = time.perf_counter()
            q = "\n".join(str(o) for _, o in sorted(opciones.items()))
            if self.bm25_normas:
                etapas["solo_opciones_bm25"] = [c for c, _ in self.bm25_normas.buscar(q, cfg.solo_opciones)]
                listas.append(etapas["solo_opciones_bm25"])
            if self.denso_normas:
                etapas["solo_opciones_denso"] = [c for c, _ in self.denso_normas.buscar_vector(
                    self.denso.vector(q), cfg.solo_opciones)]
                listas.append(etapas["solo_opciones_denso"])
            t["solo_opciones"] = time.perf_counter() - t0
        if cfg.lideres:
            for nombre in ("bm25_normas", "bm25", "denso_normas", "denso"):
                forzados += [c for c in etapas.get(nombre, [])[:cfg.lideres] if c not in forzados]
            etapas["forzados"] = forzados
        fusion = rrf(listas)
        if cfg.seguir_citas:
            t0 = time.perf_counter()
            seguidas = self._citas_seguidas([c for c, _ in fusion[:cfg.seguir_desde]])
            t["seguir_citas"] = time.perf_counter() - t0
            if seguidas:
                etapas["citas_seguidas"] = seguidas
                listas.append(seguidas)
                fusion = rrf(listas)
        etapas["rrf"] = [c for c, _ in fusion]

        pool = [c for c, _ in fusion[:cfg.n_rerank]]
        pool += [c for c in forzados if c not in pool]
        datos = self.almacen.get(pool)
        pool = [c for c in pool if c in datos]
        if self.reranker:
            t0 = time.perf_counter()
            textos = [datos[c]["texto"] for c in pool]
            puntajes = self.reranker.puntuar(consulta, textos)
            if cfg.rerank_opciones and extras:
                for _, q in extras:
                    puntajes = [max(a, b) for a, b in zip(puntajes, self.reranker.puntuar(q, textos))]
            t["reranker"] = time.perf_counter() - t0
        else:  # sin reranker: el puntaje RRF, reescalado
            maximo = fusion[0][1] if fusion else 1.0
            puntajes = [round(dict(fusion)[c] / maximo, 4) for c in pool]

        ajustados = []
        rrf_de = dict(fusion)
        rrf_max = fusion[0][1] if fusion else 1.0
        for cid, s in zip(pool, puntajes):
            d = datos[cid]
            if cfg.peso_fusion and self.reranker:
                s += cfg.peso_fusion * rrf_de.get(cid, 0.0) / rrf_max
            if d.get("derogado") or d.get("vigencia") == "derogada":
                s -= cfg.penal_derogado
            if d.get("prioridad") == "baja":
                s -= cfg.penal_prioridad_baja
            if cid not in citadas:  # lo que la pregunta cita expresamente no se castiga
                s -= cfg.penal_tipo.get(d["tipo_chunk"], 0.0)
                if d.get("prioridad") == "alta" and not es_sentencia(d):
                    s += cfg.bonus_prioridad_alta
            ajustados.append((cid, round(s, 4)))
        ajustados.sort(key=lambda p: (-p[1], p[0]))
        etapas["rerank"] = [c for c, _ in ajustados]

        t0 = time.perf_counter()
        pasajes = self._seleccionar(ajustados, datos, set(citadas), forzados)
        t["seleccion"] = time.perf_counter() - t0
        etapas["final"] = [p["chunk_id"] for p in pasajes]
        return Resultado(pasajes, etapas, {k: round(v, 3) for k, v in t.items()})

    def _decreto_smlmv(self) -> list[str]:
        """Chunk del artículo que fija el salario mínimo en el decreto más reciente del corpus (se
        busca una vez con BM25 sobre las normas y se guarda)."""
        if not hasattr(self, "_smlmv"):
            self._smlmv = []
            if self.bm25_normas:
                q = "Fijar a partir del primero de enero como Salario Mínimo Legal Mensual la suma de pesos"
                cands = [c for c, _ in self.bm25_normas.buscar(q, 100)]
                datos = self.almacen.get(cands)
                fija = re.compile(r"fijar.{0,120}salario m[ií]nimo (legal )?mensual", re.I | re.S)
                anios = []
                for c in cands:
                    d = datos.get(c)
                    m = re.search(r"_(\d{4})$", c.split("/", 1)[0])
                    if d and m and d["tipo_chunk"] == "articulo" and fija.search(d["texto"]):
                        anios.append((int(m.group(1)), c))
                if anios:
                    self._smlmv = [max(anios)[1]]
        return self._smlmv

    def _citadas_sin_articulo(self, consulta: str) -> list[str]:
        """Normas (no sentencias) que la consulta cita sin artículo, en orden de doc_id."""
        docs = [did for did, arts in sorted(documentos_citados(consulta).items())
                if not did.startswith("jurisprudencia_") and not any(arts)]
        return docs[:self.cfg.max_citadas]

    def _posiciones(self, nombre: str, ids: list[str]) -> dict[str, int]:
        if not hasattr(self, "_pos"):
            self._pos = {}
        if nombre not in self._pos:
            self._pos[nombre] = {c: i for i, c in enumerate(ids)}
        return self._pos[nombre]

    def _dentro_de(self, did: str, consulta: str, v) -> dict[str, list[str]]:
        """Los `en_citadas` mejores chunks de la norma `did` para la consulta, con BM25 (máscara sobre
        el índice de normas) y con el denso exacto (producto punto con los vectores de esa norma)."""
        import numpy as np
        n, out = self.cfg.en_citadas, {}
        chunks = [c["chunk_id"] for c in self.almacen.por("doc_id", did)]
        if self.bm25_normas:
            pos = self._posiciones("bm25", self.bm25_normas.ids)
            idx = [pos[c] for c in chunks if c in pos]
            if idx:
                out["bm25"] = [c for c, _ in self.bm25_normas.buscar(consulta, min(n, len(idx)), mascara=idx)]
        if self.denso_normas and v is not None:
            pos = self._posiciones("denso", self.denso_normas.ids)
            pares = [(c, pos[c]) for c in chunks if c in pos]
            if pares:
                m = np.stack([self.denso_normas.indice.reconstruct(p) for _, p in pares])
                s = np.round(m @ v[0], 4)
                orden = sorted(zip((c for c, _ in pares), s.tolist()), key=lambda p: (-p[1], p[0]))
                out["denso"] = [c for c, _ in orden[:n]]
        return out

    def _citas_seguidas(self, top: list[str]) -> list[str]:
        """Chunks de los artículos (o fichas) que más citan los pasajes `top`, en orden de cuántos
        pasajes los citan (desempate por id). Un artículo partido trae todas sus partes."""
        datos = self.almacen.get(top)
        conteo: dict[str, int] = {}
        chunks_de: dict[str, list[str]] = {}
        for cid in top:
            if cid not in datos:
                continue
            vistos = set()
            for citado in chunks_citados(datos[cid]["texto"], self.almacen):
                unidad = citado.split("#", 1)[0]
                chunks_de.setdefault(unidad, [])
                if citado not in chunks_de[unidad]:
                    chunks_de[unidad].append(citado)
                if unidad not in vistos:
                    vistos.add(unidad)
                    conteo[unidad] = conteo.get(unidad, 0) + 1
        mejores = sorted(conteo, key=lambda u: (-conteo[u], u))[:self.cfg.seguir_citas]
        return [c for u in mejores for c in sorted(chunks_de[u])]

    def _seleccionar(self, ajustados: list[tuple[str, float]], datos: dict,
                     citadas: set[str] = frozenset(), forzados: list[str] = ()) -> list[dict]:
        cfg, elegidos, por_doc, articulos, n_sent, diferidos = self.cfg, [], {}, set(), 0, []

        tejas_elegidas: list[set] = []

        def tomar(cid: str, s: float) -> bool:
            d = datos[cid]
            es_articulo = d["tipo_chunk"] in ("articulo", "parte_articulo")
            unidad = d.get("articulo_id") if es_articulo else cid
            if cfg.una_ventana and d["tipo_chunk"] == "seccion":
                unidad = re.sub(r"#\d+$", "", cid)
            if unidad in articulos or por_doc.get(d["doc_id"], 0) >= cfg.max_por_doc:
                return False
            if cfg.dedup:
                t = tejas(d["texto"])
                # Un pasaje que repite a uno ya elegido no aporta evidencia nueva; los artículos de norma
                # se conservan siempre (son lo que se cita: una ley y la norma que modificó pueden decir
                # lo mismo y cualquiera de las dos puede ser la de referencia).
                if not es_articulo and any(contencion(t, e) >= cfg.dedup for e in tejas_elegidas):
                    return False
                tejas_elegidas.append(t)
            articulos.add(unidad)
            por_doc[d["doc_id"]] = por_doc.get(d["doc_id"], 0) + 1
            elegidos.append((cid, s))
            return True

        puntaje = dict(ajustados)
        for cid in forzados:  # entran primero; el orden final sigue siendo por puntaje
            if cid in puntaje:
                tomar(cid, puntaje[cid])
        for cid, s in ajustados:
            if len(elegidos) == cfg.k:
                break
            sentencia = es_sentencia(datos[cid])
            if sentencia and cfg.max_sentencias is not None and n_sent >= cfg.max_sentencias \
                    and cid not in citadas:
                diferidos.append((cid, s))  # vuelven solo si no alcanza para k pasajes
                continue
            n_sent += tomar(cid, s) and sentencia
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
