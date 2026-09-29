"""Arma data/corpus_targets.json: la lista completa y verificada de documentos del corpus.

Une el seed oficial y la lista de enriquecimiento, aplica los criterios acordados
(excluir derecho ambiental, marcar derogados y pesados), resuelve la URL real de
cada documento, extrae su epígrafe como `tema`, y agrega el nivel 1: los
documentos enlazados desde las páginas y cajas del nivel 0 citados al menos
--min-citas veces. No guarda documentos a disco; solo el JSON.

Uso:
  python scraper/construir_targets.py --seed data/seed_targets.json data/corpus_nuevos_documentos.json
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import datetime as dt
import html
import json
import re
from pathlib import Path

import scrape_corpus as s

ROOT = Path(__file__).resolve().parent.parent

# ---- criterios acordados con el equipo
EXCLUIR = {  # fuera del alcance del banco: el enunciado excluye derecho ambiental
    "ley_99_1993": "derecho ambiental (fuera del banco)",
    "ley_1333_2009": "sancionatorio ambiental (fuera del banco)",
    "ley_2387_2024": "sancionatorio ambiental (fuera del banco)",
    "decreto_1076_2015": "DUR sector ambiente (fuera del banco)",
    "codigo_minas": "minero-ambiental (fuera del banco)",
    "ley_1715_2014": "energías renovables (fuera del banco)",
    "ley_1523_2012": "gestión del riesgo de desastres (fuera del banco)",
}
MARCAS = {  # se descargan, pero con metadatos de cuidado
    "ley_794_2003": ("revisar_vigencia", "baja", "Reforma al antiguo CPC; en buena parte reemplazada por el CGP."),
    "ley_1395_2010": ("revisar_vigencia", "baja", "Reforma procesal; varios artículos derogados por el CGP y el CPACA."),
    "ley_550_1999": ("revisar_vigencia", "baja", "Reestructuración empresarial; reemplazada en gran parte por la Ley 1116 de 2006."),
    "decreto_560_2020": ("transitoria", "baja", "Medidas transitorias de insolvencia por la emergencia COVID-19."),
    "decreto_772_2020": ("transitoria", "baja", "Medidas transitorias de insolvencia por la emergencia COVID-19."),
    "ley_1955_2019": (None, "baja", "Plan Nacional de Desarrollo: extenso y de bajo rendimiento para el banco."),
    "ley_2294_2023": (None, "baja", "Plan Nacional de Desarrollo: extenso y de bajo rendimiento para el banco."),
    "decreto_2420_2015": (None, "baja", "DUR normas contables (~8 MB): bajo rendimiento para el banco."),
    "decreto_2555_2010": (None, "baja", "DUR sector financiero (~5,5 MB): bajo rendimiento para el banco."),
}
ERRATAS_SEED = {  # entradas del seed que no existen tal como están escritas
    "ley_11500_2007": "Probable errata; la Ley 1150 de 2007 ya está en el seed.",
    "ley_1150_2005": "Probable errata; la Ley 1150 de 2007 ya está en el seed.",
    "ley_116_2006": "Probable errata; la Ley 1116 de 2006 ya está en el seed.",
    "ley_964_2006": "Probable errata; la Ley 964 es de 2005 y está en la lista de enriquecimiento.",
    "ley_2737_1989": "Probable errata: es el Decreto 2737 de 1989 (Código del Menor), derogado por la Ley 1098 de 2006.",
}


def texto_plano(fragmento: str) -> str:
    t = re.sub(r"<[^>]+>", " ", fragmento)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def decodificar(contenido: bytes) -> str:
    utf8 = re.search(rb"charset=[\"']?utf-8", contenido[:3000], re.I)
    return contenido.decode("utf-8" if utf8 else "latin-1", "replace")


def tema_de(contenido: bytes, fuente: str) -> str | None:
    """Epígrafe de la norma ("Por la cual se...") o descriptores de la sentencia."""
    if contenido[:4] in (b"%PDF", b"\xd0\xcf\x11\xe0", b"PK\x03\x04") or contenido.lstrip()[:4] == b"%PDF":
        return None
    t = decodificar(contenido)
    if "Corte Constitucional" in fuente:
        lineas = [texto_plano(x) for x in re.split(r"(?i)</p>|<br\s*/?>", t[:200_000])]
        desc = [x for x in lineas if len(x) > 20 and sum(c.isupper() for c in x) > 0.6 * sum(c.isalpha() for c in x)]
        return "; ".join(desc[:3])[:400] or None
    for p in re.findall(r'(?is)<p class="centrado">(.*?)</p>', t):
        x = texto_plano(p)
        if re.match(r"(?i)[\"“]?\s*por (el|la|medio de (la|el)) cual|[\"“]?\s*por (el|la) cual", x):
            return x.strip('"“” ')[:400]
    return None


def resolver_nivel0(doc: dict) -> dict:
    """Resuelve la URL real (sin guardar) y cuenta páginas, enlaces y tema."""
    try:
        fuente, partes, enlaces = s.resolver(doc, {})
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": True, "fuente": fuente, "url": partes[0][0], "archivos": len(partes),
            "formato": partes[0][2].replace("htm", "html").replace("htmll", "html"),
            "enlaces": enlaces, "base": partes[0][0].rsplit("/", 1)[0] + "/",
            "tema": tema_de(partes[0][1], fuente)}


def resolver_enlace(stem: str, bases: list[str]) -> dict:
    """Ubica un documento enlazado leyendo solo su página principal."""
    for base in dict.fromkeys([s.SENADO, s.COLPENSIONES, *bases]):
        ext = "html" if base == s.SENADO else "htm"
        try:
            r = s.get(f"{base}{stem}.{ext}")
        except Exception:  # noqa: BLE001
            continue
        if r.status_code == 200 and len(r.content) >= 3_000:
            t = r.content.decode("latin-1")
            paginas = {stem} | {p.lower() for p in re.findall(r'<option value="(_pr\d+)', t)} | \
                {p.lower() for p in re.findall(rf"{re.escape(stem)}(_pr\d+)\.{ext}\b", t, re.I)}
            fuente = next(f for d, f in s.FUENTES_PLANTILLA.items() if d in base)
            return {"ok": True, "fuente": fuente, "url": f"{base}{stem}.{ext}", "archivos": len(paginas),
                    "tema": tema_de(r.content, fuente)}
    return {"ok": False}


def canonico_de_stem(stem: str) -> list:
    stem = stem.lower()
    if m := re.fullmatch(r"(c|t|su)-0*(\d+)_(\d{4})", stem):
        return ["jurisprudencia", f"{m[1].upper()}-{int(m[2])}", m[3]]
    if m := re.fullmatch(r"([a-z_]+?)_0*(\d+)_(\d{4})", stem):
        return [m[1], str(int(m[2])), m[3]]
    return [stem, None, None]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", nargs="+", type=Path, required=True,
                    help="primero el seed oficial; después listas de enriquecimiento")
    ap.add_argument("--salida", type=Path, default=ROOT / "data" / "corpus_targets.json")
    ap.add_argument("--min-citas", type=int, default=3)
    ap.add_argument("--hilos", type=int, default=6)
    args = ap.parse_args()

    manuales = json.loads((ROOT / "data" / "urls_manuales.json").read_text(encoding="utf-8"))
    docs, vistos, excluidos, no_encontrados = [], set(), [], []
    for i, f in enumerate(args.seed):
        for d in json.loads(f.read_text(encoding="utf-8"))["documentos"]:
            did = s.canonico(s.doc_id(d["canonico"]))
            if did in vistos:
                continue
            vistos.add(did)
            d = {**d, "doc_id": did, "origen": "seed" if i == 0 else "enriquecimiento", "profundidad": 0}
            if did in EXCLUIR:
                excluidos.append({"doc_id": did, "norma": d["norma"], "motivo": EXCLUIR[did]})
                continue
            if did in manuales:
                d["donde_buscar_original"], d["donde_buscar"] = d.get("donde_buscar"), manuales[did]
            docs.append(d)

    print(f"nivel 0: resolviendo {len(docs)} documentos...", flush=True)
    with cf.ThreadPoolExecutor(args.hilos) as ex:
        res0 = list(ex.map(resolver_nivel0, docs))

    salida, citas, areas_enl, bases_enl = [], collections.Counter(), collections.defaultdict(set), \
        collections.defaultdict(set)
    for d, r in zip(docs, res0):
        did = d["doc_id"]
        if not r["ok"]:
            no_encontrados.append({"doc_id": did, "norma": d["norma"], "origen": d["origen"],
                                   "items_del_banco": d.get("items_del_banco", 0),
                                   "motivo": ERRATAS_SEED.get(did, r["error"])})
            continue
        vigencia, prioridad, nota = MARCAS.get(did, (None, "alta" if d["origen"] == "seed" else "normal", None))
        e = {"doc_id": did, "norma": d["norma"], "canonico": d["canonico"], "nivel": 0, "profundidad": 0,
             "origen": d["origen"], "items_del_banco": d.get("items_del_banco", 0), "areas": d["areas"],
             "areas_inferidas": False, "tema": r["tema"], "fuente": r["fuente"], "donde_buscar": r["url"],
             "formato": r["formato"], "archivos_estimados": r["archivos"], "prioridad": prioridad}
        if d.get("donde_buscar") and d["donde_buscar"] != r["url"]:
            e["donde_buscar_original"] = d.get("donde_buscar_original") or d["donde_buscar"]
        if vigencia:
            e["vigencia"] = vigencia
        if nota:
            e["nota"] = nota
        salida.append(e)
        for stem, n in r["enlaces"].items():
            citas[stem] += n
            areas_enl[stem] |= set(d["areas"])
            bases_enl[stem].add(r["base"])

    ids0 = {e["doc_id"] for e in salida} | {x["doc_id"] for x in excluidos}
    cand = {}
    for stem, n in citas.most_common():
        did = s.canonico(s.doc_id_senado(stem))
        if n < args.min_citas or did in ids0 or did in cand or did in EXCLUIR:
            continue
        cand[did] = (stem, n)
    print(f"nivel 1: {len(cand)} documentos con >= {args.min_citas} citas; ubicándolos...", flush=True)
    with cf.ThreadPoolExecutor(args.hilos) as ex:
        res1 = list(ex.map(lambda sn: resolver_enlace(sn[0], sorted(bases_enl[sn[0]])), cand.values()))
    for (did, (stem, n)), r in zip(cand.items(), res1):
        if not r["ok"]:
            no_encontrados.append({"doc_id": did, "norma": s.titulo_senado(stem), "origen": "enlace",
                                   "citado_por": n, "motivo": "no está en Senado, Colpensiones ni en el sitio que lo enlaza"})
            continue
        salida.append({"doc_id": did, "norma": s.titulo_senado(stem), "canonico": canonico_de_stem(stem),
                       "nivel": 1, "profundidad": 1, "origen": "enlace", "items_del_banco": 0,
                       "areas": sorted(areas_enl[stem]), "areas_inferidas": True, "tema": r["tema"],
                       "fuente": r["fuente"], "donde_buscar": r["url"], "formato": "html",
                       "archivos_estimados": r["archivos"], "citado_por": n,
                       "tipo_enlace": "sentencia" if s.es_sentencia(stem) else "norma",
                       "prioridad": "normal" if n >= 5 else "baja"})

    resumen = {
        "documentos": len(salida),
        "archivos_estimados": sum(e["archivos_estimados"] for e in salida),
        "por_nivel_y_origen": dict(collections.Counter(f"nivel{e['nivel']}:{e['origen']}" for e in salida)),
        "por_fuente": dict(collections.Counter(e["fuente"] for e in salida)),
        "por_formato": dict(collections.Counter(e["formato"] for e in salida)),
        "excluidos": len(excluidos), "no_encontrados": len(no_encontrados),
    }
    out = {
        "version": 1,
        "generado": dt.date.today().isoformat(),
        "criterios": {
            "unidad": "1 norma o sentencia = 1 documento (doc_id). Las páginas _prNNN se guardan por separado "
                      "en raw y se unen al convertir a Markdown; luego se segmenta por artículo.",
            "nivel_0": "seed oficial + lista de enriquecimiento, sin derecho ambiental.",
            "nivel_1": f"normas y sentencias enlazadas desde páginas y cajas del nivel 0, citadas >= {args.min_citas} veces.",
            "marcados": "revisar_vigencia/transitoria/prioridad baja: se descargan igual, con metadatos de cuidado.",
            "areas_inferidas": "en el nivel 1, las áreas son la unión de las áreas de los documentos que lo citan.",
        },
        "resumen": resumen,
        "documentos": salida,
        "excluidos": excluidos,
        "no_encontrados": no_encontrados,
    }
    args.salida.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
