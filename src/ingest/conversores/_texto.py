"""Segmentación de texto corrido en bloques (PDF, HTML genérico, .doc y, a futuro, OCR).

A diferencia de la plantilla del Senado, aquí no hay marcas: los artículos y
niveles se reconocen por el texto. Para no confundir un artículo citado ("ARTÍCULO
369. ..." dentro de una ley que modifica el Código) con uno propio se exige que
use la misma forma que los artículos del documento ("ARTÍCULO" vs. "Artículo") y
que su número siga la secuencia.
"""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass

from .. import jerarquia as jq
from .base import PARRAFO, Bloque

MAX_ENCABEZADO = 150   # un encabezado nunca es un párrafo largo
MAX_SALTO = 20         # "ARTÍCULO 48" -> "ARTÍCULO 369" es una cita, no el siguiente
ARTICULO_EN_LINEA = re.compile(r"(?<=[.;])\s+(?=ART[ÍI]CULO\s+\d+\s*[oº°]?\.)")


@dataclass
class Parrafo:
    texto: str
    # Una sola línea visual, separada de lo anterior y lo siguiente (PDF), o un <p> propio.
    aislado: bool = True
    negrita: bool = False


def _forma(s: str) -> str:
    return "MAYUS" if s.lstrip()[:3].isupper() else "otra"


def _sigue(num: str, ultimo: str | None) -> bool:
    if ultimo is None or not num[:1].isdigit() or not ultimo[:1].isdigit():
        return True
    a, b = jq.clave_articulo(num), jq.clave_articulo(ultimo)
    try:
        if a <= b:
            return False
    except TypeError:
        return True
    return len(a) > 1 or a[0] - b[0] <= MAX_SALTO


def _partir_articulos(parrafos: list[Parrafo]) -> list[Parrafo]:
    """"…en lo pertinente. ARTICULO 60. El artículo…": artículo pegado al anterior (PDF)."""
    out = []
    for p in parrafos:
        piezas = ARTICULO_EN_LINEA.split(p.texto)
        out.append(Parrafo(piezas[0], p.aislado, p.negrita))
        out.extend(Parrafo(x, False, p.negrita) for x in piezas[1:])
    return out


def segmentar(parrafos: list[Parrafo], sentencia: bool) -> tuple[list[Bloque], dict]:
    """Párrafos -> bloques. Devuelve también stats: artículos candidatos y aceptados."""
    if not sentencia:
        parrafos = _partir_articulos(parrafos)
    candidatos = [p for p in parrafos if not sentencia and jq.articulo(p.texto)]
    forma = collections.Counter(_forma(p.texto) for p in candidatos).most_common(1)
    forma = forma[0][0] if forma else None

    bloques: list[Bloque] = []
    ultimo: str | None = None
    nombre_pendiente = False
    rechazados = 0
    for p in parrafos:
        t = p.texto
        if not t:
            continue
        corto = p.aislado and len(t) <= MAX_ENCABEZADO
        if sentencia:
            if corto and (sec := jq.seccion_sentencia(t)):
                bloques.append(Bloque(jq.SECCION_SENTENCIA, sec))
            else:
                bloques.append(Bloque(PARRAFO, t))
            continue

        if nombre_pendiente and corto and not jq.articulo(t) and not jq.estructura(t):
            bloques[-1].texto = f"{bloques[-1].texto} {t}"
            nombre_pendiente = False
            continue
        nombre_pendiente = False

        if corto and (est := jq.estructura(t)):
            bloques.append(Bloque(est[0], t))
            nombre_pendiente = not est[1]
            continue
        if (art := jq.articulo(t)) and _forma(t) == forma:
            num, resto = art
            if _sigue(num, ultimo):
                bloques.append(Bloque(jq.ARTICULO, jq.titulo_articulo(num, ""), num))
                if resto:
                    bloques.append(Bloque(PARRAFO, resto))
                if num[:1].isdigit():
                    ultimo = num
                continue
            rechazados += 1
        bloques.append(Bloque(PARRAFO, t))
    stats = {"articulos_candidatos": len(candidatos), "articulos_rechazados_por_secuencia": rechazados}
    return bloques, stats
