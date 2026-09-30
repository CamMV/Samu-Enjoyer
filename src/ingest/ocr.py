"""Punto de entrada para OCR (no implementado todavía).

Hoy solo se detecta qué PDF lo necesitan: los escaneados no traen capa de texto y
`conversores.pdf` los marca con `requiere_ocr`. Para implementarlo:

1. Escribir una clase que cumpla `MotorOCR` (p. ej. con Tesseract `spa` vía
   `pytesseract`, o `page.get_textpage_ocr()` de PyMuPDF, que también usa Tesseract).
2. Devolver una lista de líneas por página; `conversores/pdf.py` ya sabe quitar
   encabezados y pies repetidos y segmentar con `jerarquia`.
3. Registrar el motor en `MOTORES` y quitar el error de `convertir.py --ocr`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

# Por debajo de esto (caracteres por página, en promedio) el PDF se trata como escaneado.
MIN_CARACTERES_POR_PAGINA = 50


class MotorOCR(Protocol):
    nombre: str

    def extraer(self, pdf: Path) -> list[list[str]]:
        """Líneas de texto por página, en orden de lectura."""
        ...


MOTORES: dict[str, MotorOCR] = {}


class OCRNoDisponible(RuntimeError):
    pass


def necesita_ocr(caracteres_por_pagina: list[int]) -> bool:
    if not caracteres_por_pagina:
        return True
    return sum(caracteres_por_pagina) / len(caracteres_por_pagina) < MIN_CARACTERES_POR_PAGINA


def motor(nombre: str) -> MotorOCR:
    if nombre not in MOTORES:
        raise OCRNoDisponible("OCR no implementado: ver src/ingest/ocr.py")
    return MOTORES[nombre]
