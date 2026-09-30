"""Word 2007+ (.docx), que algunas providencias de la Corte Suprema solo tienen.

Se lee con python-docx recorriendo el cuerpo en orden (párrafos y tablas), sin
pasar por LibreOffice. El tachado de Word queda como ~~…~~ igual que en HTML.
"""
from __future__ import annotations

from pathlib import Path

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from ..normalizar import texto
from ._texto import Parrafo, segmentar
from .base import Resultado


def _texto_parrafo(p: Paragraph) -> tuple[str, bool]:
    """Texto con el tachado marcado y si todo el párrafo está en negrita."""
    partes, negritas = [], []
    for run in p.runs:
        t = run.text
        if not t:
            continue
        if run.font.strike or run.font.double_strike:
            t = f"~~{t.strip()}~~" if t.strip() else t
        partes.append(t)
        if t.strip():
            negritas.append(bool(run.bold))
    return texto("".join(partes).replace("~~~~", "")), bool(negritas) and all(negritas)


def _filas(tabla: Table) -> list[list[str]]:
    filas = []
    for fila in tabla.rows:
        celdas, previa = [], None
        for celda in fila.cells:
            if celda._tc is previa:  # celdas combinadas: python-docx repite la misma
                continue
            previa = celda._tc
            celdas.append(texto(" ".join(p.text for p in celda.paragraphs)))
        if any(celdas):
            filas.append(celdas)
    return filas


def parrafos_docx(archivo: Path) -> list[Parrafo]:
    d = docx.Document(str(archivo))
    out = []
    for el in d.element.body.iterchildren():
        etiqueta = el.tag.rsplit("}", 1)[-1]
        if etiqueta == "p":
            p = Paragraph(el, d)
            t, negrita = _texto_parrafo(p)
            if t:
                estilo = (p.style.name or "").lower() if p.style is not None else ""
                out.append(Parrafo(t, aislado=True, negrita=negrita or estilo.startswith(("heading", "título"))))
        elif etiqueta == "tbl":
            filas = _filas(Table(el, d))
            if not filas:
                continue
            # Tablas de maquetación (una columna o celdas largas): se leen como párrafos.
            if max(len(f) for f in filas) == 1 or max(len(c) for f in filas for c in f) > 400:
                out.extend(Parrafo(c, aislado=True) for f in filas for c in f if c)
            else:
                out.append(Parrafo("", aislado=False, filas=filas))
    return out


class Docx:
    nombre = "docx_python_docx"

    def convertir(self, archivos: list[Path], sentencia: bool) -> Resultado:
        parrafos = [p for a in archivos for p in parrafos_docx(a)]
        bloques, stats = segmentar(parrafos, sentencia)
        return Resultado(bloques=bloques, stats={"paginas": len(archivos), **stats})
