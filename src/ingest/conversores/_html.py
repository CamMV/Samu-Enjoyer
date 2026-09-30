"""Utilidades HTML compartidas por los conversores de HTML y .doc."""
from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from ..normalizar import texto

TACHADO = {"s", "strike", "del"}
IGNORAR = {"script", "style", "select", "form", "noscript", "head", "title", "meta", "link"}


def leer(path: Path) -> str:
    """Decodifica según el charset declarado; el Senado y la Corte usan windows-1252."""
    crudo = path.read_bytes()
    m = re.search(rb"""charset=["']?([\w-]+)""", crudo[:5000], re.I)
    enc = m.group(1).decode().lower() if m else "cp1252"
    if enc in ("iso-8859-1", "latin-1", "latin1", "windows-1252"):
        enc = "cp1252"  # superconjunto práctico: trae las comillas “ ” y la raya —
    try:
        return crudo.decode(enc)
    except (UnicodeDecodeError, LookupError):
        return crudo.decode("latin-1")


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


def tabla_a_lineas(tabla: Tag) -> list[str]:
    """Una tabla de datos (no una caja) como filas "celda | celda"."""
    filas = []
    for tr in tabla.find_all("tr"):
        celdas = [limpio(td) for td in tr.find_all(["td", "th"], recursive=False)]
        celdas = [c for c in celdas if c]
        if celdas:
            filas.append(" | ".join(celdas))
    return filas
