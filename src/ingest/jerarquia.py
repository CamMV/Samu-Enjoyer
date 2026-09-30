"""Reconocimiento de la jerarquía de normas y sentencias colombianas.

Lo usan todos los conversores (HTML, PDF y, a futuro, OCR), así que las reglas de
qué es un Libro, un Título o un Artículo viven en un solo lugar.
"""
from __future__ import annotations

import re

# De mayor a menor. "subtitulo" son encabezados sin palabra clave que agrupan
# artículos (p. ej. en el Estatuto Tributario: "INGRESOS QUE NO CONSTITUYEN RENTA").
ESTRUCTURA = ("parte", "libro", "titulo", "capitulo", "seccion", "subseccion", "subtitulo")
ARTICULO = "articulo"
SECCION_SENTENCIA = "seccion_sentencia"
ENCABEZADOS = (*ESTRUCTURA, ARTICULO, SECCION_SENTENCIA)

_ORDINAL = (r"(?:primer[oa]?|segund[oa]|tercer[oa]?|cuart[oa]|quint[oa]|sext[oa]|s[eé]ptim[oa]|"
            r"octav[oa]|noven[oa]|d[eé]cim[oa](?:\s*(?:primer[oa]?|segund[oa]|tercer[oa]?|cuart[oa]|"
            r"quint[oa]|sext[oa]|s[eé]ptim[oa]|octav[oa]|noven[oa]))?|und[eé]cim[oa]|duod[eé]cim[oa]|"
            r"[uú]nic[oa]|preliminar|final|transitori[oa])")
_ROMANO = r"(?:[IVXLCDM]+)"
_TIPOS = {"parte": "parte", "libro": "libro", "titulo": "titulo", "capitulo": "capitulo",
          "seccion": "seccion", "subseccion": "subseccion"}

# "TITULO I.", "CAPÍTULO 1", "LIBRO PRIMERO", "PRIMERA PARTE.", "TÍTULO PRELIMINAR",
# "SECCIÓN 2a". Tiene que haber un número u ordinal: "Título valor" no es un título.
_ESTRUCTURA = re.compile(
    rf"""^\s*(?:(?P<ord_antes>{_ORDINAL})\s+)?
    (?P<tipo>PARTE|LIBRO|T[IÍ]TULO|CAP[IÍ]TULO|SUBSECCI[OÓ]N|SECCI[OÓ]N)\b\.?
    \s*(?P<num>{_ROMANO}\b|\d+[a-zº°ª]?\b|{_ORDINAL}\b)?\s*[\.\-–:]?\s*(?P<resto>.*)$""",
    re.I | re.X)

# "ARTICULO 1o.", "ARTÍCULO 12-A.", "ARTÍCULO 240-1.", "Artículo 5 bis", "ART. 3",
# "ARTÍCULO 2.2.1.1.1.", "ARTÍCULO TRANSITORIO 1.", "ARTICULO ÚNICO.".
_ARTICULO = re.compile(
    r"""^\s*(?:ART[IÍ]CULO|ART\.)\s*
    (?P<trans>TRANSITORIO\b\s*)?
    (?P<num>\d+(?:\.\d+)*(?:\s*-\s*\d+)*(?:\s*-?\s*(?-i:[A-Z])(?![\wÁÉÍÓÚÑáéíóúñ]))?
          |[UÚ]NICO|PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|S[EÉ]PTIMO|OCTAVO|NOVENO|D[EÉ]CIMO)?
    \s*(?:[oº°ª](?![\wÁÉÍÓÚÑáéíóúñ])\.?)?
    \s*(?P<suf>bis|ter|quater|quinquies)?\b
    (?P<resto>.*)$""",
    re.I | re.X | re.S)

_SECCIONES_SENTENCIA = (
    r"antecedentes|hechos|consideraciones|fundamentos|decisi[oó]n|resuelve|salvamento(?:\s+parcial)?\s+de\s+voto|"
    r"aclaraci[oó]n\s+de\s+voto|normas?\s+demandadas?|texto\s+de\s+la\s+norma|la\s+demanda|demandas?|"
    r"intervenci[oó]n(?:es)?|concepto\s+del?\s+(?:procurador|ministerio)|problema\s+jur[ií]dico|pruebas|"
    r"competencia|tr[aá]mite|sentencia\s+(?:de\s+primera|de\s+segunda|impugnada|del\s+tribunal|recurrida)|"
    r"(?:el\s+)?recurso|(?:la\s+)?(?:demanda\s+de\s+)?casaci[oó]n|cargos?\s+\w+|s[ií]ntesis|r[eé]plica|"
    r"alegatos|anexo|actuaci[oó]n\s+procesal|decisiones?\s+de\s+instancia|consideraciones\s+de\s+la\s+(?:corte|sala)")
_SECCION_ROMANO = re.compile(rf"^\s*(?P<num>{_ROMANO})\s*[\.\-–)]\s*(?P<resto>\S.*)$")
_SECCION_CLAVE = re.compile(rf"^\s*(?:{_SECCIONES_SENTENCIA})\b", re.I)
# Índices al inicio de algunas sentencias: "I. ANTECEDENTES (3)".
_ENTRADA_INDICE = re.compile(r"\(\d+\)\s*$|\.{4,}\s*\d+\s*$")


def _proporcion_mayusculas(s: str) -> float:
    letras = [c for c in s if c.isalpha()]
    return sum(c.isupper() for c in letras) / len(letras) if letras else 0.0


def estructura(linea: str) -> tuple[str, str] | None:
    """("titulo", nombre) si la línea abre un nivel ("TITULO I. DE LOS PRINCIPIOS ...").

    `nombre` es lo que sigue al número; vacío cuando el nombre viene en la línea
    siguiente, como en el Senado: "TITULO I." / "DE LOS PRINCIPIOS FUNDAMENTALES".
    """
    m = _ESTRUCTURA.match(linea)
    if not m or not (m["ord_antes"] or m["num"]):
        return None
    tipo = m["tipo"].lower().translate(str.maketrans("íó", "io"))
    return _TIPOS[tipo], m["resto"].strip()


def articulo(linea: str) -> tuple[str, str] | None:
    """("42", resto) si la línea empieza un artículo; el número queda normalizado."""
    m = _ARTICULO.match(linea)
    if not m or not (m["num"] or m["trans"]):
        return None
    num = re.sub(r"\s+", "", m["num"] or "")
    num = re.sub(r"-(?=[A-Z]$)", "", num).upper() if re.search(r"[A-Z]$", num, re.I) and num[:1].isdigit() else num
    if num and not num[:1].isdigit():
        num = num.lower().translate(str.maketrans("úé", "ue"))
    if m["suf"]:
        num = f"{num}-{m['suf'].lower()}"
    if m["trans"]:
        num = f"transitorio-{num}" if num else "transitorio"
    return num, m["resto"].strip(" .-–")


def clave_articulo(num: str) -> tuple:
    """Clave de orden: "240-1" -> (240, 1); "2.2.1.1" -> (2, 2, 1, 1); "12A" -> (12, 'A')."""
    partes = re.findall(r"\d+|[A-Za-z]+", num)
    return tuple(int(p) if p.isdigit() else p for p in partes)


def seccion_sentencia(linea: str) -> str | None:
    """Encabezado de sección de una sentencia ("I. ANTECEDENTES", "RESUELVE")."""
    s = linea.strip()
    if not s or len(s) > 150 or _ENTRADA_INDICE.search(s):
        return None
    if m := _SECCION_ROMANO.match(s):
        resto = m["resto"]
        if _proporcion_mayusculas(resto) >= 0.8 or _SECCION_CLAVE.match(resto):
            return s
        return None
    if _SECCION_CLAVE.match(s) and _proporcion_mayusculas(s) >= 0.8 and len(s) <= 100:
        return s
    return None


def titulo_articulo(num: str, resto: str) -> str:
    """Texto del encabezado de un artículo: "Artículo 42. EPÍGRAFE" (el chunker deriva art_42)."""
    if num.startswith("transitorio"):
        rotulo = "Artículo transitorio" + (f" {num.split('-', 1)[1]}" if "-" in num else "")
    else:
        rotulo = f"Artículo {num}"
    return f"{rotulo}. {resto}".strip() if resto else f"{rotulo}."
