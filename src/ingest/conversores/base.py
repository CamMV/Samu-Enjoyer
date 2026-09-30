"""Contrato de los conversores: archivos crudos de un documento -> bloques."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# Tipos de bloque. Los estructurales están en jerarquia.ESTRUCTURA.
PARRAFO = "parrafo"
CAJA = "caja"  # Concordancias, Notas de vigencia, etc. de la plantilla del Senado


@dataclass
class Bloque:
    tipo: str
    texto: str
    # articulo: número normalizado ("42", "240-1", "12A"); caja: su rótulo.
    etiqueta: str = ""


@dataclass
class Resultado:
    bloques: list[Bloque] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    requiere_ocr: bool = False
    # Conteos tomados de la fuente, para trazabilidad (los usa la auditoría).
    stats: dict = field(default_factory=dict)


class Conversor(Protocol):
    nombre: str

    def convertir(self, archivos: list[Path], sentencia: bool) -> Resultado:
        """`archivos` son las páginas de UN documento, en orden. `sentencia` activa
        la segmentación por secciones (antecedentes, consideraciones, decisión)
        en vez de por artículos."""
        ...
