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


def test_normas_citadas_sin_articulo():
    r = _rec(Config(normas=0), None, None)
    q = "¿Qué regula la Ley 1564 de 2002?\nA) Ley 472 de 1998\nB) artículo 5 de la Ley 1581 de 2012\nC) Sentencia C-355 de 2006"
    # La 1564 (CGP, aunque el año esté errado) y la 472 van sin artículo; la 1581 trae artículo y la sentencia no es norma.
    assert r._citadas_sin_articulo(q) == ["codigo_general_proceso", "ley_472_1998"]


class BM25Mascara:
    def __init__(self, ids):
        self.ids, self.mascaras = ids, []

    def buscar(self, consulta, k=100, mascara=None):
        self.mascaras.append(sorted(mascara or []))
        return [(self.ids[i], 1.0) for i in sorted(mascara or [])][:k]


class AlmacenDoc(AlmacenFalso):
    def por(self, campo, valor):
        return [{"chunk_id": c} for c in self.textos if c.startswith(valor + "/")]


def test_busqueda_dentro_de_la_norma_citada():
    ids = ["ley_472_1998/art_1", "codigo_general_proceso/art_24#4", "constitucion/art_88", "codigo_general_proceso/art_1"]
    almacen = AlmacenDoc({c: c for c in ids})
    r = _rec(Config(normas=0, usar_citas=False, en_citadas=5), None, almacen)
    r.bm25_normas = BM25Mascara(ids)
    res = r.buscar_item({"pregunta": "¿Qué regula las funciones jurisdiccionales de la SIC?",
                         "opciones": {"A": "Ley 1564 de 2002", "B": "Ley 270 de 1996"}})
    assert r.bm25_normas.mascaras[-1] == [1, 3]  # solo los chunks del CGP
    assert res.etapas["citada_codigo_general_proceso_bm25"] == ["codigo_general_proceso/art_24#4",
                                                                 "codigo_general_proceso/art_1"]
    assert "codigo_general_proceso/art_24#4" in res.etapas["rrf"]


def test_solo_opciones_busca_con_el_texto_de_las_opciones():
    normas = BM25Falso({"motivación": "cpaca/art_137"})
    r = _rec(Config(normas=0, usar_citas=False, solo_opciones=20), None, AlmacenFalso({}))
    r.bm25_normas = normas
    res = r.buscar_item({"pregunta": "¿Qué vicio configura?", "opciones": {"A": "Falsa motivación", "B": "Desviación de poder"}})
    assert normas.consultas[-1] == "Falsa motivación\nDesviación de poder"
    assert res.etapas["solo_opciones_bm25"] == ["cpaca/art_137"]


def test_monto_en_pesos_asegura_el_decreto_del_salario_minimo():
    from src.knowledge.hybrid_search import _PESOS_RE
    assert _PESOS_RE.search("pretensiones por 30.000.000 COP") and _PESOS_RE.search("una multa de $1.500.000")
    assert not _PESOS_RE.search("la Ley 1564 de 2012, artículo 25") and not _PESOS_RE.search("30 salarios mínimos")
    datos = {f"ley_{i}_2000/art_1": {"doc_id": f"ley_{i}_2000", "tipo_chunk": "articulo",
                                     "articulo_id": f"ley_{i}_2000/art_1", "texto": f"Ley {i}\nArtículo 1.\n{i} " * 3}
             for i in range(12)}
    datos["decreto_1572_2024/art_1"] = {"doc_id": "decreto_1572_2024", "tipo_chunk": "articulo",
                                        "articulo_id": "decreto_1572_2024/art_1", "texto": "Decreto\nArtículo 1.\nsmlmv"}
    orden = [(c, 1.0 - n / 100) for n, c in enumerate(datos)]  # el decreto, último
    r = _rec(Config(normas=0), None, None)
    sin = [p["chunk_id"] for p in r._seleccionar(orden, datos)]
    con = [p["chunk_id"] for p in r._seleccionar(orden, datos, forzados=["decreto_1572_2024/art_1"])]
    assert "decreto_1572_2024/art_1" not in sin and con[-1] == "decreto_1572_2024/art_1" and len(con) == 10


def test_bm25_solo_en_las_cerradas():
    bm25 = BM25Falso({"leasing": "ley_1/art_1"})
    almacen = AlmacenFalso({})
    cfg = Config(normas=0, usar_citas=False, bm25_solo_cerradas=True)
    abierta = _rec(cfg, bm25, almacen).buscar_item({"pregunta": "¿Qué es el leasing?"})
    assert "bm25" not in abierta.etapas and not bm25.consultas
    cerrada = _rec(cfg, bm25, almacen).buscar_item(ITEM)
    assert cerrada.etapas["bm25"] == ["ley_1/art_1"]
    sin_opcion = _rec(Config(normas=0, usar_citas=False, bm25_solo_cerradas=False), bm25, almacen).buscar_item(
        {"pregunta": "leasing"})
    assert sin_opcion.etapas["bm25"] == ["ley_1/art_1"]  # apagada: BM25 en todas


def test_siglas_se_expanden_una_vez_y_solo_en_mayusculas():
    from src.knowledge.siglas import con_siglas
    assert con_siglas("¿Qué norma regula las actuaciones ante la SIC?") == \
        "¿Qué norma regula las actuaciones ante la SIC (Superintendencia de Industria y Comercio)?"
    assert con_siglas("La DIAN y otra vez la DIAN") == \
        "La DIAN (Dirección de Impuestos y Aduanas Nacionales) y otra vez la DIAN"
    # Minúsculas, parte de otra palabra o de un id ("SU-123"): no se tocan.
    assert con_siglas("sic transit; SICARIO; Sentencia SU-123; EPSx") == "sic transit; SICARIO; Sentencia SU-123; EPSx"
    # Si el nombre completo ya está, no se repite.
    texto = "la Superintendencia de Industria y Comercio (SIC)"
    assert con_siglas(texto) == texto


def test_siglas_en_la_busqueda():
    bm25 = BM25Falso({"superintendencia de industria": "codigo_general_proceso/art_24"})
    almacen = AlmacenFalso({})
    item = {"pregunta": "¿Qué normativa regula las actuaciones ante la SIC?", "opciones": {"A": "Ley 1564"}}
    apagado = _rec(Config(normas=0, usar_citas=False, siglas=False), bm25, almacen).buscar_item(item)
    assert apagado.etapas["bm25"] == []
    con = _rec(Config(normas=0, usar_citas=False), bm25, almacen).buscar_item(item)  # activada por defecto
    assert con.etapas["bm25"] == ["codigo_general_proceso/art_24"]


def test_sin_instrucciones_de_examen():
    from src.knowledge.siglas import sin_instrucciones
    p = ("Habiendo hecho la lectura previa de la Resolución No. 368 de 2014 expedida por el Ministerio de "
         "Ambiente, lea con atención cada pregunta y responda la siguiente pregunta. \n\nPregunta jurídica: "
         "No tener en cuenta lo presentado en la consulta previa puede configurar el vicio:")
    limpio = sin_instrucciones(p)
    assert "Resolución No. 368 de 2014" in limpio and "consulta previa puede configurar el vicio" in limpio
    assert "lea con" not in limpio and "responda" not in limpio and "Pregunta jurídica" not in limpio
    assert sin_instrucciones("¿Qué pregunta debe responder el testigo?") == "¿Qué pregunta debe responder el testigo?"


def test_hipotesis_sustituye_solo_pasajes_debiles():
    """RAG_HYDE: un artículo que la hipótesis trae y el reranker respalda (≥ tau) entra en lugar del pasaje
    más débil (< 0,15); nunca saca uno fuerte ni entra uno que solo la pregunta respalda o que no es artículo."""
    from src.knowledge.hybrid_search import Config, Recuperador

    datos = {
        "ley_1581_2012/art_5": {"doc_id": "ley_1581_2012", "tipo_chunk": "articulo", "texto": "datos sensibles"},
        "ley_1581_2012/notas#1": {"doc_id": "ley_1581_2012", "tipo_chunk": "notas", "texto": "datos sensibles nota"},
        "ley_9_1979/art_1": {"doc_id": "ley_9_1979", "tipo_chunk": "articulo", "texto": "otra cosa"},
    }

    class Almacen:
        def get(self, ids):
            return {c: datos[c] for c in ids if c in datos}

    class Reranker:
        def puntuar(self, q, textos):
            return [(0.95 if "sensibles" in t else 0.2) if q.startswith("HIP") else 0.3 for t in textos]

    class Normas:
        def buscar(self, q, k):
            return [(c, 1.0) for c in datos]

        def buscar_vector(self, v, k):
            return [(c, 1.0) for c in datos]

        def vector(self, q):
            return None

    r = Recuperador.__new__(Recuperador)
    r.cfg, r.almacen, r.reranker = Config(), Almacen(), Reranker()
    r.denso = r.denso_normas = r.bm25_normas = Normas()
    base = [{"doc_id": "constitucion", "chunk_id": "constitucion/art_15", "texto": "x", "score": 0.9},
            {"doc_id": "ley_x", "chunk_id": "ley_x/art_2", "texto": "x", "score": 0.05},
            {"doc_id": "ley_y", "chunk_id": "ley_y/art_3", "texto": "x", "score": 0.10}]
    out = r.sustituir_debiles(base, "pregunta", "HIP datos sensibles")
    ids = [p["chunk_id"] for p in out]
    assert "ley_1581_2012/art_5" in ids and "ley_x/art_2" not in ids          # el más débil sale
    assert "constitucion/art_15" in ids and "ley_y/art_3" in ids              # el fuerte y el 2.º débil quedan
    assert "ley_1581_2012/notas#1" not in ids and "ley_9_1979/art_1" not in ids  # nota y bajo tau no entran
    assert r.sustituir_debiles(base, "pregunta", "") == base                 # sin hipótesis, igual
