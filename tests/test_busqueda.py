"""Búsqueda por opción y seguimiento de citas del recuperador. Sin índices ni modelos."""
from src.knowledge.hybrid_search import Config, Recuperador


class BM25Falso:
    """Devuelve un chunk propio para cada término que reconoce."""

    def __init__(self, por_termino):
        self.por_termino = por_termino
        self.consultas = []

    def buscar(self, consulta, k=100):
        self.consultas.append(consulta)
        return [(cid, 1.0) for t, cid in self.por_termino.items() if t in consulta.lower()][:k]


class AlmacenFalso:
    def __init__(self, textos, articulos=()):
        self.textos = textos
        self.articulos = set(articulos)

    def get(self, ids):
        return {i: {"chunk_id": i, "doc_id": i.split("/")[0], "texto": self.textos.get(i, i),
                    "tipo_chunk": "articulo", "articulo_id": i.split("#")[0]} for i in ids}

    def por(self, campo, valor):
        return [{"chunk_id": valor, "tipo_chunk": "articulo"}] if valor in self.articulos else []


def _rec(cfg, bm25, almacen):
    r = object.__new__(Recuperador)
    r.cfg, r.almacen, r.bm25, r.denso, r.reranker = cfg, almacen, bm25, None, None
    r.bm25_normas = r.denso_normas = None
    return r


ITEM = {"pregunta": "¿Quiénes otorgan leasing?", "opciones": {"A": "Bancos", "B": "Bancos y Fintech"}}


def test_busqueda_por_opcion_agrega_una_lista_por_opcion():
    bm25 = BM25Falso({"leasing": "ley_1/art_1", "fintech": "decreto_1068_2025/art_2.26.3"})
    almacen = AlmacenFalso({})
    apagado = _rec(Config(normas=0, por_opcion=0, usar_citas=False), bm25, almacen).buscar_item(ITEM)
    assert not any(e.startswith("opcion_") for e in apagado.etapas)
    r = _rec(Config(normas=0, por_opcion=50, usar_citas=False), bm25, almacen).buscar_item(ITEM)
    assert {"opcion_A_bm25", "opcion_B_bm25"} <= set(r.etapas)
    assert "decreto_1068_2025/art_2.26.3" in r.etapas["opcion_B_bm25"]
    assert bm25.consultas[-1] == "¿Quiénes otorgan leasing?\nB) Bancos y Fintech"
    # Solo las cerradas: una pregunta sin opciones no agrega búsquedas.
    sin = _rec(Config(normas=0, por_opcion=50, usar_citas=False), bm25, almacen).buscar_item({"pregunta": "leasing"})
    assert not any(e.startswith("opcion_") for e in sin.etapas)


def test_seguir_citas_trae_los_articulos_mas_citados():
    textos = {"jurisprudencia_t-1_2020/consideraciones#1": "Conforme al artículo 53 de la Constitución Política…",
              "jurisprudencia_t-2_2021/consideraciones#4": "El artículo 53 de la Constitución y el artículo 23 "
                                                            "del Código Sustantivo del Trabajo…"}
    bm25 = BM25Falso({"cooperativa": "jurisprudencia_t-1_2020/consideraciones#1",
                      "trabajo": "jurisprudencia_t-2_2021/consideraciones#4"})
    almacen = AlmacenFalso(textos, articulos={"constitucion/art_53", "codigo_sustantivo_trabajo/art_23"})
    r = _rec(Config(normas=0, seguir_citas=10, usar_citas=False), bm25, almacen).buscar(
        "Cooperativa de trabajo asociado")
    # El art. 53 lo citan dos pasajes y va primero; el 23 del CST, uno.
    assert r.etapas["citas_seguidas"] == ["constitucion/art_53", "codigo_sustantivo_trabajo/art_23"]
    assert "constitucion/art_53" in r.etapas["rrf"]
    apagado = _rec(Config(normas=0, seguir_citas=0, usar_citas=False), bm25, almacen).buscar(
        "Cooperativa de trabajo asociado")
    assert "citas_seguidas" not in apagado.etapas
