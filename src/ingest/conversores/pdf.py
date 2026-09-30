"""PDF con capa de texto (Función Pública, Corte Suprema, CAN) vía PyMuPDF."""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from .. import jerarquia as jq
from .. import ocr
from ..normalizar import desguionar, texto
from ._texto import Parrafo, segmentar
from .base import Resultado

BANDA = 0.10          # franja inferior donde viven los pies de página
# Franja superior: Presidencia repite en cada hoja el epígrafe del decreto hasta ~14 % del alto.
BANDA_SUPERIOR = 0.18
MIN_REPETICION = 0.5  # fracción de páginas en que debe repetirse para ser encabezado/pie


@dataclass
class Linea:
    pagina: int
    y0: float
    y1: float
    texto: str
    negrita: bool


def _lineas_pagina(n: int, page: pymupdf.Page, tp: pymupdf.TextPage | None = None) -> list[Linea]:
    """Líneas visuales: PyMuPDF parte en varias "lines" lo que está a la misma altura
    (texto justificado, "I." + "ANTECEDENTES"); aquí se vuelven a unir. `tp` es la
    capa de texto del OCR cuando la página es un escaneo."""
    crudas = []
    for bloque in page.get_text("dict", sort=True, textpage=tp)["blocks"]:
        for ln in bloque.get("lines", []):
            spans = [s for s in ln["spans"] if s["text"].strip()]
            if not spans:
                continue
            bold = all(s["flags"] & 16 or "bold" in s["font"].lower() for s in spans)
            x0, y0, _, y1 = ln["bbox"]
            crudas.append((y0, y1, x0, "".join(s["text"] for s in spans), bold))
    crudas.sort(key=lambda c: (round(c[0]), c[2]))
    lineas: list[Linea] = []
    for y0, y1, _, t, bold in crudas:
        prev = lineas[-1] if lineas else None
        if prev and abs(y0 - prev.y0) < 0.5 * (prev.y1 - prev.y0):
            prev.texto += " " + t
            prev.y1 = max(prev.y1, y1)
            prev.negrita = prev.negrita and bold
        else:
            lineas.append(Linea(n, y0, y1, t, bold))
    for ln in lineas:
        ln.texto = texto(ln.texto)
    return [ln for ln in lineas if ln.texto]


# Sellos, firmas y escudos leídos como texto ("t~SIOtNLII m e· :: ,·utsuG"): tokens con símbolos
# que no aparecen en texto jurídico, o solo puntuación.
_TOKEN_RUIDO = re.compile(r"[~·\\|^`´¬]|^[^\w]{2,}$")


def _ruido(t: str) -> bool:
    tokens = t.split()
    if not tokens or len(t) > 120:
        return False
    malos = sum(1 for x in tokens if _TOKEN_RUIDO.search(x))
    return malos >= 2 and malos / len(tokens) > 0.4


def _clave(t: str) -> str:
    # Solo las palabras, sin números ni orden: "SCLAJPT-10 V.00" y "SCLAJPT-10 V.00 2" (con número
    # de página) son el mismo pie, y también "107 del Hoja No. 2 .. Decreto No." y "Hoja No. 4 del
    # Decreto No. 107" (Presidencia, que cambia el orden de las palabras en cada hoja).
    return " ".join(sorted(re.findall(r"[^\W\d_]+", t.lower())))


def _quitar_encabezados(paginas: list[list[Linea]], alto: list[float]) -> tuple[list[Linea], int]:
    """Quita líneas de la franja superior/inferior que se repiten en muchas páginas
    (ignorando números: "Página 3 de 20") y los números de página sueltos."""
    en_banda = lambda ln, h: ln.y0 < h * BANDA_SUPERIOR or ln.y1 > h * (1 - BANDA)  # noqa: E731
    cuenta = collections.Counter()
    for pag, h in zip(paginas, alto):
        cuenta.update({_clave(ln.texto) for ln in pag if en_banda(ln, h)})
    umbral = max(2, MIN_REPETICION * len(paginas))
    quitadas, out = 0, []
    for pag, h in zip(paginas, alto):
        for ln in pag:
            if _ruido(ln.texto) or en_banda(ln, h) and (
                    re.fullmatch(r"[\d\s\-–/]+|p[áa]g(ina)?\.?\s*\d+.*", ln.texto, re.I)
                    or (len(paginas) >= 3 and cuenta[_clave(ln.texto)] >= umbral)):
                quitadas += 1
                continue
            out.append(ln)
    return out, quitadas


def _abre_bloque(t: str) -> bool:
    return bool(jq.articulo(t) or jq.estructura(t) or jq.seccion_sentencia(t))


def _parrafos(lineas: list[Linea]) -> list[Parrafo]:
    grupos: list[list[Linea]] = []
    for ln in lineas:
        prev = grupos[-1][-1] if grupos else None
        nuevo = prev is None or _abre_bloque(ln.texto)
        if prev and not nuevo:
            if ln.pagina != prev.pagina:
                # Salto de página: sigue el párrafo si la frase no había terminado.
                nuevo = prev.texto.rstrip()[-1:] in ".:;" or not ln.texto[:1].islower()
            else:
                nuevo = (ln.y0 - prev.y1) > (prev.y1 - prev.y0)
        if nuevo:
            grupos.append([ln])
        else:
            grupos[-1].append(ln)
    return [Parrafo(desguionar([ln.texto for ln in g]), aislado=len(g) == 1,
                    negrita=all(ln.negrita for ln in g)) for g in grupos]


class Pdf:
    nombre = "pdf_pymupdf"

    def convertir(self, archivos: list[Path], sentencia: bool) -> Resultado:
        paginas, alto, chars, con_ocr = [], [], [], 0
        hay_ocr = ocr.disponible()
        for archivo in archivos:
            with pymupdf.open(archivo) as doc:
                for page in doc:
                    lineas = _lineas_pagina(len(paginas), page)
                    n = sum(len(ln.texto) for ln in lineas)
                    if n < ocr.MIN_CARACTERES_POR_PAGINA and hay_ocr:  # página escaneada
                        lineas = _lineas_pagina(len(paginas), page, ocr.textpage(page))
                        n = sum(len(ln.texto) for ln in lineas)
                        con_ocr += 1
                    paginas.append(lineas)
                    alto.append(page.rect.height)
                    chars.append(n)
        if ocr.necesita_ocr(chars):
            motivo = "PDF sin texto ni con OCR" if hay_ocr else "PDF sin capa de texto: requiere OCR"
            return Resultado(requiere_ocr=True, stats={"paginas": len(paginas), "caracteres": sum(chars),
                                                       "paginas_ocr": con_ocr}, advertencias=[motivo])
        lineas, quitadas = _quitar_encabezados(paginas, alto)
        bloques, stats = segmentar(_parrafos(lineas), sentencia)
        return Resultado(bloques=bloques, stats={"paginas": len(paginas), "paginas_ocr": con_ocr,
                                                 "lineas_encabezado_pie": quitadas, **stats})
