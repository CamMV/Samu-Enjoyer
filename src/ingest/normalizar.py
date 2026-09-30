"""Limpieza de texto común a todos los formatos."""
from __future__ import annotations

import re
import unicodedata

# NFKC arreglaría las ligaduras pero también convierte "1º" en "1o" y "2ª" en "2a";
# por eso se reemplazan a mano.
LIGADURAS = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
_LIGADURAS = re.compile("|".join(LIGADURAS))
# Espacios raros que vienen de Word y de las plantillas HTML.
_ESPACIOS = re.compile(r"[ \t  -   　]+")
_INVISIBLES = re.compile(r"[­​-‍⁠﻿]")


def texto(s: str) -> str:
    """Una línea limpia: NFC, sin ligaduras, sin invisibles, espacios simples."""
    s = unicodedata.normalize("NFC", s)
    s = _LIGADURAS.sub(lambda m: LIGADURAS[m[0]], s)
    s = _INVISIBLES.sub("", s)
    s = s.replace("�", "")  # carácter perdido en la propia fuente (Cancillería): no se recupera
    s = s.replace("\r", " ").replace("\n", " ")
    return _ESPACIOS.sub(" ", s).strip()


def desguionar(lineas: list[str]) -> str:
    """Une líneas de un mismo párrafo (PDF), quitando el guion de corte de palabra."""
    out = ""
    for linea in lineas:
        linea = linea.strip()
        if not linea:
            continue
        if out.endswith("-") and len(out) > 1 and out[-2].isalpha() and linea[:1].islower():
            out = out[:-1] + linea
        else:
            out = f"{out} {linea}" if out else linea
    return texto(out)


def tachado(s: str) -> str:
    """Marca texto tachado (inexequible o derogado) como ~~…~~ sin espacios pegados."""
    s = texto(s)
    return f"~~{s}~~" if s else ""
