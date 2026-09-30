"""HTML sin la plantilla del Senado: relatoría de la Corte Constitucional (HTML
exportado de Word), Función Pública, SUIN y el HTML que produce LibreOffice a
partir de un .doc."""
from __future__ import annotations

from pathlib import Path

from bs4 import Tag

from ._html import IGNORAR, leer, limpio, sopa, tabla_filas
from ._texto import Parrafo, segmentar
from .base import Resultado

BLOQUES = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "pre", "blockquote")


def _parrafos(el: Tag):
    for c in el.children:
        if not isinstance(c, Tag) or c.name in IGNORAR:
            continue
        if c.name in BLOQUES:
            yield Parrafo(limpio(c))
        elif c.name == "table":
            # Tablas de maquetación de Word envuelven párrafos enteros: se recorren.
            if c.find(BLOQUES):
                yield from _parrafos(c)
            else:
                if filas := tabla_filas(c):
                    yield Parrafo("", aislado=False, filas=filas)
        else:
            yield from _parrafos(c)


def parrafos_html(html: str) -> list[Parrafo]:
    s = sopa(html)
    raiz = s.body or s
    return [p for p in _parrafos(raiz) if p.texto or p.filas]


class HtmlGenerico:
    nombre = "html_generico"

    def convertir(self, archivos: list[Path], sentencia: bool) -> Resultado:
        parrafos = [p for a in archivos for p in parrafos_html(leer(a))]
        bloques, stats = segmentar(parrafos, sentencia)
        return Resultado(bloques=bloques, stats={"paginas": len(archivos), **stats})
