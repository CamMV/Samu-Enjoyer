"""Word 97-2003 (.doc), que algunas providencias de la Corte Suprema solo tienen.

LibreOffice lo pasa a HTML y de ahí sigue el conversor genérico.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import Resultado
from .html_generico import HtmlGenerico


class SofficeNoDisponible(RuntimeError):
    pass


def a_html(doc: Path, destino: Path) -> Path:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise SofficeNoDisponible("se necesita LibreOffice (soffice) para convertir .doc")
    # Perfil propio: dos soffice con el mismo perfil no corren a la vez (--hilos).
    perfil = destino / "perfil"
    subprocess.run([soffice, f"-env:UserInstallation=file://{perfil}", "--headless",
                    "--convert-to", "html:HTML (StarWriter):UTF8", "--outdir", str(destino), str(doc)],
                   check=True, capture_output=True, timeout=300)
    salida = destino / f"{doc.stem}.html"
    if not salida.exists():
        raise RuntimeError(f"LibreOffice no produjo {salida.name}")
    return salida


class Doc:
    nombre = "doc_libreoffice"

    def convertir(self, archivos: list[Path], sentencia: bool) -> Resultado:
        with tempfile.TemporaryDirectory() as tmp:
            htmls = [a_html(a, Path(tmp)) for a in archivos]
            res = HtmlGenerico().convertir(htmls, sentencia)
        res.stats["via"] = "libreoffice"
        return res
