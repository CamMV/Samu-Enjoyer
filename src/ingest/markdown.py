"""Serializa los bloques de un documento a Markdown con front matter YAML."""
from __future__ import annotations

import collections
import json
import re

from .conversores.base import CAJA, PARRAFO, TABLA, Bloque
from .jerarquia import ARTICULO, ESTRUCTURA, SECCION_SENTENCIA

# Orden de anidamiento para asignar niveles de encabezado.
ORDEN = (*ESTRUCTURA, SECCION_SENTENCIA, ARTICULO)
MAX_NIVELES = 5  # H2..H6; H1 es el título del documento


def niveles(bloques: list[Bloque]) -> dict[str, int]:
    """Nivel dinámico: solo cuentan los tipos presentes en el documento.

    Una ley con solo Capítulos y Artículos queda con Capítulo = ## y Artículo = ###,
    sin saltos. Si hay más de 5 tipos, los menos frecuentes (nunca el artículo)
    se escriben en negrita en vez de como encabezado.
    """
    frec = collections.Counter(b.tipo for b in bloques if b.tipo in ORDEN)
    presentes = [t for t in ORDEN if frec[t]]
    while len(presentes) > MAX_NIVELES:
        candidatos = [t for t in presentes if t != ARTICULO]
        presentes.remove(min(candidatos, key=lambda t: frec[t]))
    return {t: i + 2 for i, t in enumerate(presentes)}


def _yaml(meta: dict) -> str:
    # Un string JSON es un escalar YAML válido: evita depender de PyYAML.
    lineas = ["---"]
    for k, v in meta.items():
        if v is None or v == "" or v == []:
            continue
        lineas.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    lineas.append("---")
    return "\n".join(lineas)


def _escapar(s: str) -> str:
    # Un párrafo que empieza con "#" o ">" se leería como encabezado o cita.
    return re.sub(r"^([#>])", r"\\\1", s)


def _tabla(filas: list[list[str]]) -> str:
    """Tabla Markdown: la primera fila hace de encabezado; las filas cortas se rellenan."""
    ancho = max(len(f) for f in filas)
    celda = lambda c: c.replace("|", "\\|") or " "  # noqa: E731
    lineas = ["| " + " | ".join(celda(c) for c in f + [""] * (ancho - len(f))) + " |" for f in filas]
    lineas.insert(1, "|" + "---|" * ancho)
    return "\n".join(lineas)


def a_markdown(meta: dict, titulo: str, bloques: list[Bloque]) -> str:
    nivel = niveles(bloques)
    partes = [_yaml(meta), "", f"# {titulo}", ""]
    for b in bloques:
        if b.tipo in ORDEN:
            if b.tipo in nivel:
                partes.append(f"{'#' * nivel[b.tipo]} {b.texto}")
            else:
                partes.append(f"**{b.texto}**")
        elif b.tipo == CAJA:
            lineas = [ln for ln in b.texto.split("\n") if ln.strip()]
            cuerpo = "\n>\n".join(f"> {_escapar(ln)}" for ln in lineas)
            partes.append(f"> **{b.etiqueta}:**\n>\n{cuerpo}" if b.etiqueta else cuerpo)
        elif b.tipo == TABLA:
            ancho = max(len(f) for f in b.filas)
            # Una tabla de una sola columna es maquetación: se escribe como párrafos.
            partes.append(_tabla(b.filas) if ancho > 1 else "\n\n".join(_escapar(f[0]) for f in b.filas))
        elif b.tipo == PARRAFO:
            partes.append(_escapar(b.texto))
        partes.append("")
    return "\n".join(partes).rstrip() + "\n"
