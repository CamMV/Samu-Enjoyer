"""OCR para PDF escaneados, con Tesseract (`spa`) a través de PyMuPDF.

Cerca del 13 % de los PDF de la Corte Suprema y ~1 % de los de Presidencia son
escaneos sin capa de texto. `conversores/pdf.py` pasa por OCR solo las páginas que
no traen texto, y luego sigue igual que con un PDF normal: quita encabezados y pies
repetidos y segmenta con `jerarquia`.

Requisitos: Tesseract y el modelo `spa.traineddata` (en el entorno conda `IA`:
`conda install -c conda-forge tesseract` y el modelo de tessdata_fast en
`<entorno>/share/tessdata`). La carpeta se toma de TESSDATA_PREFIX o del entorno.
Si no hay OCR, el PDF queda como `estado_conversion: "requiere_ocr"`.
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

import pymupdf

# Por debajo de esto (caracteres por página) la página se trata como escaneada.
MIN_CARACTERES_POR_PAGINA = 50
IDIOMA = "spa"
DPI = 300  # 200 pierde tildes en los escaneos de la Corte; 300 cuesta ~1,8 s por página


class OCRNoDisponible(RuntimeError):
    pass


@lru_cache(maxsize=1)
def tessdata() -> str | None:
    """Carpeta con el modelo de idioma, o None si no hay OCR en este equipo."""
    candidatos = [os.environ.get("TESSDATA_PREFIX"), Path(sys.prefix) / "share" / "tessdata",
                  Path(sys.prefix) / "Library" / "share" / "tessdata"]
    for c in candidatos:
        if c and (Path(c) / f"{IDIOMA}.traineddata").exists():
            return str(c)
    return None


def disponible() -> bool:
    return not os.environ.get("INGEST_SIN_OCR") and tessdata() is not None


def textpage(page: pymupdf.Page) -> pymupdf.TextPage:
    """Capa de texto de la página reconocida por OCR (página completa)."""
    if not disponible():
        raise OCRNoDisponible(f"falta Tesseract con {IDIOMA}.traineddata (ver src/ingest/ocr.py)")
    return page.get_textpage_ocr(language=IDIOMA, dpi=DPI, full=True, tessdata=tessdata())


def necesita_ocr(caracteres_por_pagina: list[int]) -> bool:
    if not caracteres_por_pagina:
        return True
    return sum(caracteres_por_pagina) / len(caracteres_por_pagina) < MIN_CARACTERES_POR_PAGINA
