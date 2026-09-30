"""Recolecta listas de documentos de fuentes nuevas, con la forma de seed_targets.json.

Cada lista trae URL directa verificable (`donde_buscar`), `tema` y `areas`
inferidas. Luego se suman al JSON maestro con
`construir_targets.py --agregar <lista> --origen fuente_nueva`.

Fuentes:
  cc     Corte Constitucional: todas las sentencias SU y C (buscador de la relatoría).
  ce     Consejo de Estado: sentencias de unificación (lista oficial de la relatoría).
  csj    Corte Suprema: sentencias de las salas de casación Civil, Penal y Laboral
         (solo sala permanente) por rango de años (API de consultaprovidencias).
  dapre  Presidencia: decretos normativos a partir de los listados mensuales
         guardados por el navegador (ver --dapre-filas).

Uso:
  python scraper/fuentes_nuevas.py cc --salida data/fuente_cc.json
  python scraper/fuentes_nuevas.py csj --salida data/fuente_csj.json
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import html
import json
import re
import unicodedata
import urllib.parse as up
from pathlib import Path

import scrape_corpus as s

ROOT = Path(__file__).resolve().parent.parent
AREAS = {  # palabras clave (sin tildes, minúsculas) -> área del banco
    "Derecho laboral": r"trabaj|laboral|pension|salari|sindic|seguridad social|cesantia|despido|empleador|riesgos laborales",
    "Derecho penal": r"penal|delito|pena |punib|fiscal[ií]a|imputad|condena|carcel|reclusi|victima de",
    "Derecho de familia": r"famili|matrimoni|conyug|divorci|union marital|hij[oa]s|alimentos|adopci|menor de edad|nin[oa]s|patria potestad|filiaci",
    "Derecho tributario": r"tribut|impuesto|renta|iva\b|contribuci|gravam|dian|fiscal territorial|tasa ",
    "Derecho comercial y sociedades": r"sociedad(es)? comercial|mercantil|comerci|insolvenc|reorganizaci|fiduci|titulo valor|seguro|bancari|financier|accionist",
    "Derecho de los mercados [competencia, consumidor, datos personales y propiedad intelectual]":
        r"consumidor|competencia desleal|libre competencia|datos personales|habeas data|propiedad intelectual|marca|patente|derechos de autor|publicidad",
    "Derecho civil": r"civil|contrato|obligaci|propiedad|posesi|prescripci|responsabilidad extracontractual|sucesi|herencia|bienes|compraventa|arrendamiento",
    "Derecho procesal": r"proces|recurso|tutela contra providencia|competencia del juez|nulidad procesal|caducidad|prueba|casaci|debido proceso|jurisdicci",
    "Derecho administrativo": r"administrativ|contrataci|servidor publico|funcion publica|acto administrativo|entidad publica|disciplinari|municip|departament|estatal|reparacion directa",
    "Derecho constitucional": r"constituci|derecho fundamental|tutela|inexequib|exequib|dignidad|igualdad|libertad",
}


def sin_tildes(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def inferir_areas(texto: str, base: list[str] | None = None) -> list[str]:
    t = sin_tildes(texto or "")
    areas = {a for a, pat in AREAS.items() if re.search(pat, t)}
    return sorted(areas | set(base or [])) or ["Derecho constitucional"]


def texto(fragmento: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragmento))).strip()


# ------------------------------------------------------------------ Corte Constitucional

CC_BUSCADOR = "https://www.corteconstitucional.gov.co/relatoria/buscador_new/"


def cc_anio(tipo: str, anio: int) -> list[dict]:
    p = dict(searchOption="prov_sentencia", buscar_por=tipo, fini=f"{anio}-01-01", ffin=f"{anio}-12-31",
             accion="search", maxprov="3000", OrderbyOption="des__score", verform="si", slop="1")
    t = s.get(CC_BUSCADOR, params=p).text
    docs = {}
    for fila in re.findall(r"(?is)<tr>(.*?)</tr>", t):
        m = re.search(r'href="(https://www\.corteconstitucional\.gov\.co/relatoria/\d{4}/([^"]+)\.htm)"', fila)
        if not m:
            continue
        url, arch = m.groups()
        mm = re.fullmatch(rf"({tipo})-?0*(\d+)([A-Z]?)-(\d{{2}})", arch, re.I)
        if not mm:
            continue
        num = f"{mm[1].upper()}-{int(mm[2])}{mm[3].upper()}"
        tema = re.search(r"(?is)<b>TEMA:\s*</b>(.*?)(?:<br|<b>RESUMEN)", fila)
        resumen = re.search(r"(?is)<b>RESUMEN:\s*</b>(.*?)</td>", fila)
        tema_txt = texto(tema[1]) if tema else ""
        doc = {"norma": f"Sentencia {num} de {anio}", "canonico": ["jurisprudencia", num, str(anio)],
               "items_del_banco": 0, "areas": inferir_areas(tema_txt + " " + (texto(resumen[1]) if resumen else ""),
                                                             ["Derecho constitucional"]),
               "areas_inferidas": True, "donde_buscar": url, "tema": tema_txt[:400] or None,
               "fuente": "Corte Constitucional - Relatoría", "formato": "html"}
        docs[num] = doc
    return list(docs.values())


def recolectar_cc(anios: range, tipos: tuple[str, ...] = ("SU", "C")) -> list[dict]:
    trabajos = [(t, a) for t in tipos for a in anios]
    with cf.ThreadPoolExecutor(4) as ex:
        res = list(ex.map(lambda ta: cc_anio(*ta), trabajos))
    for (t, a), r in zip(trabajos, res):
        print(f"CC {t} {a}: {len(r)}", flush=True)
    return [d for r in res for d in r]


# ------------------------------------------------------------------ Consejo de Estado

CE_LISTA = "https://servicios.consejodeestado.gov.co/testmaster/nue_unifi.asp"
CE_DESCARGA = "https://servicios.consejodeestado.gov.co/WebRelatoria/FileReferenceServlet?corp=ce&ext=doc&file={}"


def recolectar_ce() -> list[dict]:
    t = s.get(CE_LISTA).content.decode("utf-8", "replace")
    docs = []
    for fila in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", t):
        m = re.search(r"FileReferenceServlet\?corp=ce&ext=doc&file=(\d+)", fila)
        if not m:
            continue
        c = [texto(x) for x in re.findall(r"(?is)<td[^>]*>(.*?)</td>", fila)]
        _, fecha, ponente, tema, actor, publicado, radicado = (c + [""] * 8)[:7]
        anio = fecha[-4:] if fecha[-4:].isdigit() and fecha[-4:] != "1900" else publicado[:4]
        rad = re.sub(r"[^0-9A-Za-z-]", "", radicado) or m[1]
        docs.append({
            "norma": f"Sentencia de unificación del Consejo de Estado, radicado {radicado or m[1]} ({fecha})",
            "canonico": ["jurisprudencia", f"CE-{rad}", anio], "items_del_banco": 0,
            "areas": inferir_areas(tema, ["Derecho administrativo"]), "areas_inferidas": True,
            "donde_buscar": CE_DESCARGA.format(m[1]), "tema": tema[:400],
            "fuente": "Consejo de Estado - Relatoría", "formato": "doc",
            "nota": f"Consejero ponente: {ponente}. Actor: {actor}."})
    return docs


# ------------------------------------------------------------------ Corte Suprema

def csj_pagina(sala: str, anio: int, start: int) -> tuple[list[dict], int]:
    g = ('{ getSearchResult(searchQuery:{ query: "sentencia" typeOfQuery: "%s" start: %d isExact: false '
         'magistrate:"" year:"%d" autoSentencia: "SENTENCIA" order: "" roomTutelas: "" addedQueries: [] }) '
         '{ searchResults { title onlinePath } numOfResults } }' % (sala, start, anio))
    d = s.get(f"{s.CSJ_API}/api", method="POST", json={"query": g}).json()["data"]["getSearchResult"]
    return d["searchResults"] or [], d["numOfResults"]


def csj_anio(sala: str, anio: int, solo_permanente: bool) -> list[dict]:
    prefijo = {"Civil": "SC", "Laboral": "SL", "Penal": "SP"}[sala]
    patron = re.compile(rf"^({prefijo})0*(\d+)-({anio})(?:[\s(\[].*)?\.(pdf|docx?)$", re.I)
    vistos: dict[str, dict] = {}
    res, total = csj_pagina(sala, anio, 0)
    starts = range(10, total, 10)
    paginas = [res]
    with cf.ThreadPoolExecutor(4) as ex:
        paginas += [r for r, _ in ex.map(lambda st: csj_pagina(sala, anio, st), starts)]
    for x in (x for p in paginas for x in p):
        m = patron.match(x["title"])
        if not m or (solo_permanente and "/PERMANENTE/" not in x["onlinePath"].upper()
                     and sala == "Laboral"):
            continue
        num = f"{prefijo}-{int(m[2])}"
        previo = vistos.get(num)
        if previo and previo["formato"] == "pdf":
            continue
        ext = m[4].lower()
        path = x["onlinePath"]
        vistos[num] = {
            "norma": f"Sentencia {num} de {anio}", "canonico": ["jurisprudencia", num, str(anio)],
            "items_del_banco": 0, "areas": [], "areas_inferidas": True,
            "donde_buscar": f"{s.CSJ_API}/downloadFile?path={up.quote(path)}",
            "tema": None, "fuente": "Corte Suprema de Justicia - Relatoría",
            "formato": "pdf" if ext == "pdf" else ext}
    area = {"Civil": ["Derecho civil", "Derecho procesal"], "Laboral": ["Derecho laboral"],
            "Penal": ["Derecho penal"]}[sala]
    for d in vistos.values():
        d["areas"] = area
    print(f"CSJ {sala} {anio}: {len(vistos)} sentencias (de {total} resultados)", flush=True)
    return list(vistos.values())


def recolectar_csj(rangos: dict[str, range]) -> list[dict]:
    out = []
    for sala, anios in rangos.items():
        for a in anios:
            out += csj_anio(sala, a, solo_permanente=True)
    return out


# ------------------------------------------------------------------ Presidencia (DAPRE)

# Decretos sin contenido normativo general: actos de personal, honores, presupuesto puntual.
DAPRE_EXCLUIR = re.compile(
    r"nombramiento|nombra |renuncia|encarg|comision (de servicios|al exterior|de estudios)|en comision|"
    r"traslad[oa] (a|de) |honores|ascens|retiro|vacaciones|licencia|insubsisten|reintegr|condecor|"
    r"cruz de boyaca|orden de boyaca|se designa|designacion|se acepta|posesion|embajador|consul|"
    r"presupuest|contracredit|se liquida|viaje|asigna(n)? (una )?prima|delega(n)? (una|unas|la|las) funcion|"
    r"separacion del cargo|suspension provisional del|declara(n)? insubsistente|vincula|planta de personal|"
    r"reubicacion|titulos de tesoreria|\btes\b|ambiental|ambiente y desarrollo|funcionario|servicio exterior|"
    r"se delegan|dia civico|duelo nacional|comision de personal|prorroga (la|el) (encargo|nombramiento)")
MESES = {m: i for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                      "septiembre", "octubre", "noviembre", "diciembre"], 1)}


def recolectar_dapre(filas: Path) -> tuple[list[dict], collections.Counter]:
    docs, vistos, conteo = {}, set(), collections.Counter()
    for linea in filas.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(linea)
        except json.JSONDecodeError:
            continue
        for archivo, epigrafe in d.get("rows", []):
            url = "https://dapre.presidencia.gov.co/normativa/normativa/" + archivo
            nombre = up.unquote(archivo)
            m = re.search(r"DECRETO\s+(?:No\.?\s*)?0*(\d+)\s+(?:DEL?\s+)?(\d{1,2})?\s*(?:DE\s+)?([A-ZÁÉÍÓÚ]+)?\s*(?:DE\s+)?(\d{4})",
                          nombre, re.I)
            if not m or url in vistos:
                continue
            vistos.add(url)
            conteo["listados"] += 1
            if DAPRE_EXCLUIR.search(sin_tildes(epigrafe)):
                conteo["excluidos_no_normativos"] += 1
                continue
            num, anio = str(int(m[1])), m[4]
            can = ["decreto", num, anio]
            did = s.doc_id(can)
            if did in docs:  # el listado repite algunos decretos con otro nombre de archivo
                continue
            docs[did] = {"norma": f"Decreto {num} de {anio}", "canonico": can, "items_del_banco": 0,
                         "areas": inferir_areas(epigrafe, ["Derecho administrativo"]), "areas_inferidas": True,
                         "donde_buscar": url, "tema": epigrafe.strip('"“”«» ')[:400] or None,
                         "fuente": "Presidencia de la República - Normativa", "formato": "pdf"}
    conteo["normativos"] = len(docs)
    return list(docs.values()), conteo


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fuente", choices=["cc", "ce", "csj", "dapre"])
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--dapre-filas", type=Path, help="JSONL con los listados mensuales de DAPRE")
    ap.add_argument("--tipos", default="SU,C", help="cc: tipos de sentencia, p. ej. T")
    ap.add_argument("--desde", type=int, default=1992, help="cc: primer año")
    ap.add_argument("--hasta", type=int, default=2026, help="cc: último año")
    args = ap.parse_args()
    if args.fuente == "cc":
        docs = recolectar_cc(range(args.desde, args.hasta + 1), tuple(args.tipos.split(",")))
    elif args.fuente == "ce":
        docs = recolectar_ce()
    elif args.fuente == "csj":
        docs = recolectar_csj({"Civil": range(2010, 2026), "Penal": range(2015, 2026),
                               "Laboral": range(2020, 2026)})
    else:
        docs, conteo = recolectar_dapre(args.dapre_filas)
        print(dict(conteo))
    args.salida.write_text(json.dumps({"fuente": args.fuente, "documentos": docs}, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    print(f"{len(docs)} documentos -> {args.salida}")


if __name__ == "__main__":
    main()
