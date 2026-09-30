"""Utilidades HTML compartidas por los conversores de HTML y .doc."""
from __future__ import annotations

import codecs
import re
from pathlib import Path

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from ..normalizar import texto

TACHADO = {"s", "strike", "del"}
IGNORAR = {"script", "style", "select", "form", "noscript", "head", "title", "meta", "link"}
CHARSET = re.compile(r"""<meta[^>]*charset[^>]*>|(<\?xml[^>]*?)\s+encoding=["'][^"']*["']""", re.I)


def _cp1252_por_byte(e: UnicodeDecodeError) -> tuple[str, int]:
    """Lo que no es UTF-8 válido se lee como windows-1252 (bytes sin carácter: se omiten)."""
    return e.object[e.start:e.end].decode("cp1252", errors="replace").replace("�", ""), e.end


codecs.register_error("cp1252_por_byte", _cp1252_por_byte)


def leer(path: Path) -> str:
    """Decodifica el HTML y le quita la declaración de charset.

    El Senado y la Corte declaran windows-1252, pero hay páginas que mezclan trozos en
    UTF-8 (la relatoría de la Corte Constitucional) o que declaran ISO-8859-1 y vienen en
    UTF-8 (DIAN). Se lee cada secuencia como UTF-8 si lo es y, si no, byte a byte como
    windows-1252: en un archivo todo windows-1252 da lo mismo que decodificarlo así.
    La declaración se quita porque lxml, al verla, vuelve a decodificar el texto ya
    decodificado y corta el documento (la C-355 de 2006 quedaba en el 13 %).
    """
    texto_html = path.read_bytes().decode("utf-8", errors="cp1252_por_byte")
    return CHARSET.sub(lambda m: m.group(1) or "", texto_html)


def sopa(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def inline(el: Tag, _en_tachado: bool = False) -> str:
    """Texto de un elemento con el tachado marcado como ~~…~~."""
    out = []
    for n in el.children:
        if isinstance(n, Comment):
            continue
        if isinstance(n, NavigableString):
            out.append(str(n))
        elif not isinstance(n, Tag) or n.name in IGNORAR:
            continue
        elif n.name == "br":
            out.append(" ")
        elif n.name in TACHADO and not _en_tachado:
            t = inline(n, True)
            if t.strip():
                ini, fin = t[: len(t) - len(t.lstrip())], t[len(t.rstrip()):]
                out.append(f"{ini}~~{t.strip()}~~{fin}")
        else:
            out.append(inline(n, _en_tachado))
    return "".join(out)


def limpio(el: Tag) -> str:
    s = texto(inline(el))
    s = re.sub(r"~~\s*~~", "", s)          # tachados vacíos
    s = re.sub(r"~~(\s*)~~", r"\1", s)      # dos tachados seguidos se unen
    return texto(s)


def tabla_filas(tabla: Tag) -> list[list[str]]:
    """Celdas de una tabla de datos (no una caja), fila por fila, sin filas vacías."""
    filas = []
    for tr in tabla.find_all("tr"):
        if tr.find_parent("table") is not tabla:  # filas de tablas anidadas: las lee su tabla
            continue
        celdas = [limpio(td) for td in tr.find_all(["td", "th"], recursive=False)]
        if any(celdas):
            filas.append(celdas)
    return filas


def tabla_a_lineas(tabla: Tag) -> list[str]:
    """Una tabla de datos como filas "celda | celda" (texto plano)."""
    return [" | ".join(c for c in f if c) for f in tabla_filas(tabla)]
