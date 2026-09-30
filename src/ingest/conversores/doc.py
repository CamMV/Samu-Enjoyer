"""Word 97-2003 (.doc), que algunas providencias de la Corte Suprema y del Consejo de
Estado solo tienen.

LibreOffice lo pasa a HTML y de ahí sigue el conversor genérico. Arrancar
LibreOffice cuesta ~1 minuto, así que `convertir.py` pasa antes todos los .doc a
HTML en lotes y los deja en una caché (variable INGEST_CACHE_DOC); aquí solo se
convierte uno a uno lo que no esté en ella.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .base import Resultado
from .html_generico import HtmlGenerico

CACHE_ENV = "INGEST_CACHE_DOC"


class SofficeNoDisponible(RuntimeError):
    pass


def soffice() -> str:
    """Ejecutable de LibreOffice: variable SOFFICE, el PATH o el desempacado en el entorno
    conda (envs/IA/libreoffice, ver README)."""
    en_entorno = Path(sys.prefix) / "libreoffice" / "program" / ("soffice.com" if os.name == "nt" else "soffice")
    exe = (os.environ.get("SOFFICE") or shutil.which("soffice") or shutil.which("libreoffice")
           or (str(en_entorno) if en_entorno.exists() else None))
    if not exe:
        raise SofficeNoDisponible("se necesita LibreOffice (soffice) para convertir .doc")
    return exe


def a_html(doc: Path, destino: Path) -> Path:
    # Perfil propio: dos soffice con el mismo perfil no corren a la vez (--hilos).
    perfil = destino / "perfil"
    subprocess.run([soffice(), f"-env:UserInstallation={perfil.resolve().as_uri()}", "--headless",
                    "--convert-to", "html:HTML (StarWriter):UTF8", "--outdir", str(destino), str(doc)],
                   check=True, capture_output=True, timeout=300)
    salida = destino / f"{doc.stem}.html"
    if not salida.exists():
        raise RuntimeError(f"LibreOffice no produjo {salida.name}")
    return salida


class Doc:
    nombre = "doc_libreoffice"

    def convertir(self, archivos: list[Path], sentencia: bool) -> Resultado:
        cache = Path(os.environ[CACHE_ENV]) if os.environ.get(CACHE_ENV) else None
        with tempfile.TemporaryDirectory() as tmp:
            htmls = []
            for a in archivos:
                en_cache = cache / f"{a.stem}.html" if cache else None
                htmls.append(en_cache if en_cache and en_cache.exists() else a_html(a, Path(tmp)))
            res = HtmlGenerico().convertir(htmls, sentencia)
        res.stats["via"] = "libreoffice"
        return res
