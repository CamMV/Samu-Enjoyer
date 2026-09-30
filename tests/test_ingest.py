from pathlib import Path

import pytest

from src.ingest import jerarquia as jq
from src.ingest.conversores._texto import Parrafo, segmentar
from src.ingest.conversores.base import Bloque
from src.ingest.conversores.html_plantilla import HtmlPlantilla
from src.ingest.markdown import a_markdown, niveles
from src.ingest.normalizar import desguionar, texto


@pytest.mark.parametrize("linea,num,resto", [
    ("ARTICULO 1o.", "1", ""),
    ("ARTÍCULO 12-A. EPÍGRAFE", "12A", "EPÍGRAFE"),
    ("ARTÍCULO 240-1. OTRAS RENTAS", "240-1", "OTRAS RENTAS"),
    ("Artículo 5 bis. Texto", "5-bis", "Texto"),
    ("ARTÍCULO 2.2.1.1.1. Objeto", "2.2.1.1.1", "Objeto"),
    ("ARTICULO TRANSITORIO 1. Texto", "transitorio-1", "Texto"),
    ("ARTÍCULO  1º. El artículo 23", "1", "El artículo 23"),
    ("ARTICULO ÚNICO. Texto", "unico", "Texto"),
])
def test_articulo(linea, num, resto):
    assert jq.articulo(linea) == (num, resto)


@pytest.mark.parametrize("linea", ["Artículos 3 y 4 de la ley", "El artículo 5", "ARTICULADO"])
def test_no_es_articulo(linea):
    assert jq.articulo(linea) is None


@pytest.mark.parametrize("linea,tipo,nombre", [
    ("TITULO I.", "titulo", ""),
    ("TÍTULO PRELIMINAR.", "titulo", ""),
    ("TÍTULO TRANSITORIO.", "titulo", ""),
    ("PRIMERA PARTE.", "parte", ""),
    ("LIBRO PRIMERO", "libro", ""),
    ("CAPITULO X. DESCUENTOS TRIBUTARIOS", "capitulo", "DESCUENTOS TRIBUTARIOS"),
    ("SECCIÓN 2a", "seccion", ""),
])
def test_estructura(linea, tipo, nombre):
    assert jq.estructura(linea) == (tipo, nombre)


@pytest.mark.parametrize("linea", ["Título valor de algo", "Parte de la doctrina", "Capítulo aparte"])
def test_no_es_estructura(linea):
    assert jq.estructura(linea) is None


@pytest.mark.parametrize("linea,es", [
    ("I. ANTECEDENTES", True),
    ("II . Consideraciones y fundamentos", True),
    ("VI. CONSIDERACIONES Y FUNDAMENTOS DE LA CORTE", True),
    ("RESUELVE:", True),
    ("SALVAMENTO DE VOTO DEL MAGISTRADO X", True),
    ("I. ANTECEDENTES (3)", False),  # entrada del índice
    ("III. Los artículos impugnados vulneran la igualdad", False),
    ("COMPAÑÍA DE SEGUROS S.A.", False),
])
def test_seccion_sentencia(linea, es):
    assert bool(jq.seccion_sentencia(linea)) is es


def test_normalizar():
    assert texto("modiﬁcado  por­la  ley") == "modificado porla ley"
    assert desguionar(["el contra-", "to de trabajo"]) == "el contrato de trabajo"
    assert desguionar(["Decreto-", "Ley 2351"]) == "Decreto- Ley 2351"


def test_niveles_dinamicos_sin_huecos():
    bloques = [Bloque("capitulo", "CAPÍTULO I."), Bloque(jq.ARTICULO, "Artículo 1.", "1")]
    assert niveles(bloques) == {"capitulo": 2, jq.ARTICULO: 3}


def test_segmentar_descarta_articulos_citados():
    parrafos = [Parrafo("ARTÍCULO 48. El artículo 369 del Código quedará así:"),
                Parrafo("ARTÍCULO 369. Modificación de los Estatutos. Toda modificación…"),
                Parrafo("Artículo 23. Elementos esenciales."),
                Parrafo("ARTÍCULO 49. Texto.")]
    bloques, stats = segmentar(parrafos, sentencia=False)
    assert [b.etiqueta for b in bloques if b.tipo == jq.ARTICULO] == ["48", "49"]
    assert stats["articulos_rechazados_por_secuencia"] == 1


def test_segmentar_parte_articulo_pegado():
    bloques, _ = segmentar([Parrafo("ARTÍCULO 59. Texto en lo pertinente. ARTICULO 60. El artículo 434.")], False)
    assert [b.etiqueta for b in bloques if b.tipo == jq.ARTICULO] == ["59", "60"]


PAGINA = """<html><body><div id="selector_aj"><select><option>menu</option></select></div>
<!--Inicio documento-->
<p class="centrado"><a class="bookmarkaj" name="Nivel001">TITULO I. </A></p>
<p class="centrado"><span class="b_aj">DE LOS PRINCIPIOS</span></p>
<p><a class="bookmarkaj" name="1">ARTICULO 1o.</A> Colombia es un <S>Estado</S> social.</p>
<div><a class="caja_vja_encabezado" href="javascript:insRow1()">Concordancias</a></div>
<table id="Table1"><tbody><tr><td><p>Ley 388 de 1997</p></td></tr></tbody></table>
<p class="centrado"><A name="Nivel002"></A></p>
<p class="centrado"><span class="b_aj">CAPITULO 1.</span></p>
<p class="centrado">DE LOS DERECHOS</p>
<p><span><A name="2">ARTICULO 2o. FINES.</A></span> Son fines.</p>
<p class="centrado">TÍTULO I OBJETO</p>
<!--Fin documento-->
<div id="logo_aj">Derechos de autor reservados</div></body></html>"""


def test_plantilla_senado(tmp_path: Path):
    f = tmp_path / "ley_p000.html"
    f.write_text(PAGINA, encoding="cp1252")
    res = HtmlPlantilla().convertir([f], sentencia=False)
    tipos = [(b.tipo, b.texto) for b in res.bloques]
    assert tipos[0] == ("titulo", "TITULO I. DE LOS PRINCIPIOS")
    assert tipos[1] == (jq.ARTICULO, "Artículo 1.")
    assert tipos[2] == ("parrafo", "Colombia es un ~~Estado~~ social.")
    assert tipos[3] == ("caja", "Ley 388 de 1997")
    assert tipos[4] == ("capitulo", "CAPITULO 1. DE LOS DERECHOS")
    assert tipos[5] == (jq.ARTICULO, "Artículo 2. FINES")
    # Encabezado sin ancla después del último artículo: texto anexo, no jerarquía.
    assert tipos[-1] == ("parrafo", "TÍTULO I OBJETO")
    assert res.stats["articulos_fuente"] == 2

    md = a_markdown({"doc_id": "ley"}, "Ley", res.bloques)
    assert "## TITULO I. DE LOS PRINCIPIOS" in md
    assert "### CAPITULO 1. DE LOS DERECHOS" in md
    assert "#### Artículo 2. FINES" in md
    assert "> **Concordancias:**" in md
    assert "menu" not in md and "Derechos de autor" not in md
