"""Registro de conversores: elige uno según la extensión y el contenido."""
from __future__ import annotations

from pathlib import Path

from ._html import leer
from .base import Bloque, Conversor, Resultado
from .doc import Doc
from .docx import Docx
from .html_generico import HtmlGenerico
from .html_plantilla import HtmlPlantilla, es_plantilla
from .pdf import Pdf

__all__ = ["Bloque", "Conversor", "Resultado", "elegir"]


def elegir(archivos: list[Path]) -> Conversor:
    ext = archivos[0].suffix.lower()
    if ext in (".html", ".htm"):
        return HtmlPlantilla() if es_plantilla(leer(archivos[0])) else HtmlGenerico()
    if ext == ".pdf":
        return Pdf()
    if ext == ".doc":
        return Doc()
    if ext == ".docx":
        return Docx()
    raise ValueError(f"formato no soportado: {ext}")
