"""Siglas jurídicas colombianas: la consulta se busca también con el nombre completo.

La pregunta dice "SIC" y la norma dice "Superintendencia de Industria y Comercio": BM25 no los
empareja y el embedder no siempre. `con_siglas` agrega el nombre completo entre paréntesis después
de la primera aparición de cada sigla (en mayúsculas, como palabra completa). Sin LLM: determinista.

Solo siglas de un único significado en el derecho colombiano; las ambiguas (CC: Código Civil o
Corte Constitucional; CP: Constitución Política o Código Penal; CE) se dejan fuera.
"""
from __future__ import annotations

import re

SIGLAS = {
    # Autoridades
    "SIC": "Superintendencia de Industria y Comercio",
    "SFC": "Superintendencia Financiera de Colombia",
    "SSPD": "Superintendencia de Servicios Públicos Domiciliarios",
    "DIAN": "Dirección de Impuestos y Aduanas Nacionales",
    "ICBF": "Instituto Colombiano de Bienestar Familiar",
    "UGPP": "Unidad de Gestión Pensional y Parafiscales",
    "SENA": "Servicio Nacional de Aprendizaje",
    "DANE": "Departamento Administrativo Nacional de Estadística",
    "DNP": "Departamento Nacional de Planeación",
    "CNE": "Consejo Nacional Electoral",
    "RNEC": "Registraduría Nacional del Estado Civil",
    "CGR": "Contraloría General de la República",
    "PGN": "Procuraduría General de la Nación",
    "CSJ": "Corte Suprema de Justicia",
    "JEP": "Jurisdicción Especial para la Paz",
    "ANLA": "Autoridad Nacional de Licencias Ambientales",
    "CAR": "Corporación Autónoma Regional",
    "CRC": "Comisión de Regulación de Comunicaciones",
    "ANI": "Agencia Nacional de Infraestructura",
    # Códigos y estatutos
    "CGP": "Código General del Proceso",
    "CPACA": "Código de Procedimiento Administrativo y de lo Contencioso Administrativo",
    "CPC": "Código de Procedimiento Civil",
    "CPP": "Código de Procedimiento Penal",
    "CST": "Código Sustantivo del Trabajo",
    "CPTSS": "Código Procesal del Trabajo y de la Seguridad Social",
    "ET": "Estatuto Tributario",
    "POT": "Plan de Ordenamiento Territorial",
    # Seguridad social
    "EPS": "Entidad Promotora de Salud",
    "IPS": "Institución Prestadora de Servicios de Salud",
    "ARL": "Administradora de Riesgos Laborales",
    "AFP": "Administradora de Fondos de Pensiones",
    "SGSSS": "Sistema General de Seguridad Social en Salud",
    "UPC": "Unidad de Pago por Capitación",
    "IBC": "ingreso base de cotización",
    "IBL": "ingreso base de liquidación",
    "RAIS": "régimen de ahorro individual con solidaridad",
    "SOAT": "Seguro Obligatorio de Accidentes de Tránsito",
    # Tributario, comercial y otros
    "IVA": "impuesto sobre las ventas",
    "NIT": "Número de Identificación Tributaria",
    "RUT": "Registro Único Tributario",
    "ESAL": "entidades sin ánimo de lucro",
    "NNA": "niños, niñas y adolescentes",
    "SMLMV": "salario mínimo mensual legal vigente",
    "SMMLV": "salario mínimo mensual legal vigente",
}

# Palabra completa en mayúsculas; el guion queda fuera para no tocar ids como "SU-123".
_SIGLA_RE = re.compile(r"(?<![\w-])(" + "|".join(sorted(SIGLAS, key=len, reverse=True)) + r")(?![\w-])")


def con_siglas(texto: str) -> str:
    """`texto` con el nombre completo entre paréntesis tras la primera aparición de cada sigla.
    Si el nombre completo ya está en el texto, la sigla no se expande."""
    vistas: set[str] = set()
    minusculas = texto.lower()

    def expandir(m: re.Match) -> str:
        sigla = m.group(1)
        nombre = SIGLAS[sigla]
        if sigla in vistas or nombre.lower() in minusculas:
            return sigla
        vistas.add(sigla)
        return f"{sigla} ({nombre})"

    return _SIGLA_RE.sub(expandir, texto)


# Instrucciones de examen ("lea con atención cada pregunta y responda…"): no son contenido jurídico,
# pero BM25 las usa. En la 748, "pregunta" y "responda" traían artículos de interrogatorio de parte
# (CPC art. 208) y el art. 137 del CPACA quedaba en el puesto 258 de BM25 de normas (35 sin ellas).
# Se quitan solo las fórmulas de instrucción; lo que nombran (la resolución, el caso) se conserva.
_INSTRUCCIONES_RE = re.compile(
    r"(?i)\bhabiendo (?:hecho|realizado) (?:una |la )?lectura (?:previa )?del?\b"
    r"|,?\s*\blea con atenci[oó]n(?: cada| la| las)? preguntas?(?: y responda(?: la siguiente pregunta)?)?[.:]?"
    r"|\bresponda la siguiente pregunta[.:]?"
    r"|\bpregunta jur[ií]dica\s*:"
    r"|\b(?:seleccione|elija|marque) la (?:respuesta|opci[oó]n) correcta[.:]?")


def sin_instrucciones(texto: str) -> str:
    """`texto` sin las fórmulas de instrucción de examen (ver `_INSTRUCCIONES_RE`); sin ellas, intacto."""
    if not _INSTRUCCIONES_RE.search(texto):
        return texto
    return re.sub(r"[ \t]{2,}", " ", _INSTRUCCIONES_RE.sub(" ", texto)).strip()
