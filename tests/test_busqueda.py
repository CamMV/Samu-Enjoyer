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


def test_dedup_salta_casi_duplicados_pero_no_articulos():
    parrafo = "En efecto existen casos en los cuales hay sujetos colectivos que pretenden la proteccion de intereses individuales " * 3
    distinto = "La accion de tutela procede contra particulares encargados de la prestacion de un servicio publico " * 3
    datos = {
        "jurisprudencia_t-1_2012/resuelve#14": {"doc_id": "jurisprudencia_t-1_2012", "tipo_chunk": "seccion",
                                               "tipo_documento": "sentencia", "texto": "T-1 › Resuelve\n" + parrafo},
        "jurisprudencia_t-2_2013/resuelve#6": {"doc_id": "jurisprudencia_t-2_2013", "tipo_chunk": "seccion",
                                              "tipo_documento": "sentencia", "texto": "T-2 › Resuelve\n" + parrafo},
        "ley_1_1976/art_25": {"doc_id": "ley_1_1976", "tipo_chunk": "articulo", "articulo_id": "ley_1_1976/art_25",
                              "texto": "Ley 1 de 1976\nArtículo 25.\n" + distinto},
        "codigo_civil/art_1820": {"doc_id": "codigo_civil", "tipo_chunk": "articulo", "articulo_id": "codigo_civil/art_1820",
                                  "texto": "Código Civil\nArtículo 1820.\n" + distinto},
    }
    orden = [(c, 1.0 - n / 10) for n, c in enumerate(datos)]
    con = _rec(Config(normas=0, dedup=0.5, expandir_articulo=False), None, None)._seleccionar(orden, datos)
    ids = [p["chunk_id"] for p in con]
    assert "jurisprudencia_t-2_2013/resuelve#6" not in ids              # la sentencia que repite el párrafo sale
    assert {"ley_1_1976/art_25", "codigo_civil/art_1820"} <= set(ids)    # los dos artículos se conservan
    sin = _rec(Config(normas=0, dedup=0.0, expandir_articulo=False), None, None)._seleccionar(orden, datos)
    assert len(sin) == 4
