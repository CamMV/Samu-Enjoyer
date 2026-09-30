"""Metadatos jurídicos de cada documento, a partir de su doc_id y de la lista maestra.

El enunciado (paso 1) pide que el texto limpio lleve tipo de norma, número, año,
artículo, órgano emisor y vigencia. El artículo va en cada encabezado "Artículo N."
del .md; el resto sale de aquí y se escribe en el front matter.

- `tipo_norma`: constitucion, ley, decreto, acto_legislativo, resolucion, decision,
  sentencia. Los códigos llevan el tipo, número y año de la norma que los expidió
  (el Código General del Proceso es la Ley 1564 de 2012).
- `organo_emisor`: quién la expide (Congreso, Presidencia, DIAN, cada corte y sala).
- `nombre_citable`: cómo se cita, con el nombre que reconoce el evaluador
  (scripts/citations.py) para los códigos.
- `vigencia`: la marca de la lista maestra (derogada, revisar_vigencia, transitoria);
  "sin_marca" si no se sabe nada en contra.
"""
from __future__ import annotations

import re

# doc_id -> (tipo, número, año, nombre con que se cita)
CODIGOS = {
    "constitucion": ("constitucion", None, "1991", "Constitución Política de Colombia"),
    "constitucion_politica_1986": ("constitucion", None, "1886", "Constitución Política de 1886"),
    "codigo_civil": ("ley", "57", "1887", "Código Civil"),
    "codigo_comercio": ("decreto", "410", "1971", "Código de Comercio"),
    "codigo_penal": ("ley", "599", "2000", "Código Penal"),
    "codigo_procedimiento_penal": ("ley", "906", "2004", "Código de Procedimiento Penal"),
    "codigo_general_proceso": ("ley", "1564", "2012", "Código General del Proceso"),
    "codigo_procedimiento_administrativo": (
        "ley", "1437", "2011",
        "Código de Procedimiento Administrativo y de lo Contencioso Administrativo (CPACA)"),
    "codigo_sustantivo_trabajo": ("decreto", "2663", "1950", "Código Sustantivo del Trabajo"),
    "codigo_procedimental_laboral": ("decreto", "2158", "1948",
                                     "Código Procesal del Trabajo y de la Seguridad Social"),
    "estatuto_tributario": ("decreto", "624", "1989", "Estatuto Tributario"),
    "estatuto_consumidor": ("ley", "1480", "2011", "Estatuto del Consumidor"),
    "codigo_infancia": ("ley", "1098", "2006", "Código de la Infancia y la Adolescencia"),
    "codigo_nacional_policia": ("ley", "1801", "2016", "Código Nacional de Seguridad y Convivencia Ciudadana"),
    "codigo_disciplinario": ("ley", "1952", "2019", "Código General Disciplinario"),
    "codigo_penitenciario": ("ley", "65", "1993", "Código Penitenciario y Carcelario"),
    "codigo_penal_militar": ("ley", "1407", "2010", "Código Penal Militar"),
    "codigo_disciplinario_abogado": ("ley", "1123", "2007", "Código Disciplinario del Abogado"),
    "codigo_minas": ("ley", "685", "2001", "Código de Minas"),
    "codigo_regimen_municipal": ("decreto", "1333", "1986", "Código de Régimen Municipal"),
    "codigo_procedimiento_civil": ("decreto", "1400", "1970", "Código de Procedimiento Civil"),
    "codigo_contencioso_administrativo": ("decreto", "1", "1984", "Código Contencioso Administrativo"),
    "codigo_menor": ("decreto", "2737", "1989", "Código del Menor"),
    "codigo_penal_1980": ("decreto", "100", "1980", "Código Penal de 1980"),
    "codigo_procedimiento_penal_1991": ("decreto", "2700", "1991", "Código de Procedimiento Penal de 1991"),
    "decision_andina_486": ("decision", "486", "2000",
                            "Decisión 486 de la Comisión de la Comunidad Andina"),
}

EMISOR = {
    "constitucion": "Asamblea Nacional Constituyente",
    "ley": "Congreso de la República",
    "acto_legislativo": "Congreso de la República",
    "decreto": "Presidencia de la República",
    "decision": "Comisión de la Comunidad Andina",
}
CORTE_CONSTITUCIONAL = {"C": "sentencia de constitucionalidad", "T": "sentencia de tutela",
                        "SU": "sentencia de unificación"}
CSJ_SALAS = {"SC": "Sala de Casación Civil", "SL": "Sala de Casación Laboral", "SP": "Sala de Casación Penal",
             "STC": "Sala de Casación Civil (tutela)", "STL": "Sala de Casación Laboral (tutela)",
             "STP": "Sala de Casación Penal (tutela)", "AC": "Sala de Casación Civil",
             "AL": "Sala de Casación Laboral", "AP": "Sala de Casación Penal"}
NOMBRE_TIPO = {"ley": "Ley", "decreto": "Decreto", "acto_legislativo": "Acto Legislativo",
               "resolucion": "Resolución", "decision": "Decisión"}


def _sentencia(did: str) -> dict:
    cuerpo = did.removeprefix("jurisprudencia_")
    if m := re.fullmatch(r"ce-([\d-]+)_(\d{4})", cuerpo):
        return {"tipo_norma": "sentencia", "numero": m[1], "anio": m[2], "organo_emisor": "Consejo de Estado",
                "tipo_providencia": "sentencia de unificación", "radicado": m[1],
                "nombre_citable": f"Consejo de Estado, sentencia de unificación, radicado {m[1]} de {m[2]}"}
    if m := re.fullmatch(r"([a-z]+)-(\d+[a-z]?)_(\d{4})", cuerpo):
        sala, num, anio = m[1].upper(), m[2].upper(), m[3]
        base = {"tipo_norma": "sentencia", "numero": f"{sala}-{num}", "anio": anio,
                "nombre_citable": f"Sentencia {sala}-{num} de {anio}"}
        if sala in CORTE_CONSTITUCIONAL:
            return base | {"organo_emisor": "Corte Constitucional", "tipo_providencia": CORTE_CONSTITUCIONAL[sala]}
        if sala in CSJ_SALAS:
            return base | {"organo_emisor": "Corte Suprema de Justicia", "sala": CSJ_SALAS[sala],
                           "tipo_providencia": "sentencia"}
        return base
    return {"tipo_norma": "sentencia"}


def metadatos(did: str, reg: dict, objetivo: dict | None = None) -> dict:
    """Campos jurídicos del documento. `reg` es su registro del manifest de raw y
    `objetivo` su entrada de data/corpus_targets.json (si está)."""
    objetivo = objetivo or {}
    if did.startswith("jurisprudencia_"):
        m = _sentencia(did)
    elif did in CODIGOS:
        tipo, num, anio, nombre = CODIGOS[did]
        m = {"tipo_norma": tipo, "numero": num, "anio": anio, "organo_emisor": EMISOR.get(tipo),
             "nombre_citable": nombre}
    elif mm := re.fullmatch(r"(ley|decreto|acto_legislativo|resolucion|decision)_(\d+)_(\d{4})", did):
        tipo, num, anio = mm[1], str(int(mm[2])), mm[3]
        emisor = EMISOR.get(tipo)
        fuente = reg.get("fuente") or ""
        if tipo == "resolucion" and "DIAN" in fuente:
            emisor = "Dirección de Impuestos y Aduanas Nacionales (DIAN)"
        m = {"tipo_norma": tipo, "numero": num, "anio": anio, "organo_emisor": emisor,
             "nombre_citable": f"{NOMBRE_TIPO[tipo]} {num} de {anio}"}
    else:
        m = {"tipo_norma": "otro"}
    canonico = objetivo.get("canonico")
    return m | {
        "canonico": canonico,
        "epigrafe": objetivo.get("tema"),
        "vigencia": objetivo.get("vigencia") or reg.get("vigencia") or "sin_marca",
        "nivel": objetivo.get("nivel"),
        "origen": objetivo.get("origen") or reg.get("origen"),
        "citado_por": objetivo.get("citado_por") or None,
        "items_del_banco": objetivo.get("items_del_banco") or None,
    }
