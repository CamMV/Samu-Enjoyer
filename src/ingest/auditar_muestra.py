"""Audita una muestra aleatoria de los .md convertidos contra su fuente en corpus/raw.

Toma N documentos al azar (50 por defecto) de corpus/md, los copia a
corpus/md/_auditoria/<fecha>_s<semilla>/muestra/ y escribe ahí reporte.md y
reporte.json con el veredicto de cada uno. La semilla queda en el nombre de la
carpeta y en el reporte: con --semilla se repite exactamente la misma muestra.

Chequeos (FALLA = error, REVISAR = aviso):
  front_matter   campos de procedencia completos y doc_id = nombre del archivo
  titulo         un único "# " y es el primer encabezado
  jerarquia      cada tipo (Libro, Título, Capítulo, Artículo…) usa siempre el mismo
                 nivel y un tipo mayor nunca queda debajo de uno menor; sin
                 encabezados vacíos; normas con artículos y sentencias con secciones
  trazabilidad   nº de artículos del .md vs. los de la fuente, contados aparte
                 (anclas del HTML del Senado, o "ARTÍCULO N" en el texto del PDF)
  secuencia      números de artículo crecientes y sin repetir
  vacios         artículos sin texto
  residuos       etiquetas HTML, cajas sin llenar, menú del Senado, ligaduras, �
  cobertura      caracteres del .md / caracteres de texto de la fuente
  tachado        si la fuente tiene <s>/<strike>/<del>, el .md tiene ~~

Uso:
  python -m src.ingest.auditar_muestra                   # 50 al azar, semilla nueva
  python -m src.ingest.auditar_muestra --semilla 1234    # repetir una muestra
  python -m src.ingest.auditar_muestra --estratificar    # repartir por formato de origen
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import html as htmlmod
import json
import random
import re
import shutil
from pathlib import Path

import pymupdf

from . import jerarquia as jq
from .markdown import ORDEN

ROOT = Path(__file__).resolve().parents[2]
CAMPOS = ("doc_id", "titulo", "fuente", "url", "fecha_consulta", "areas", "archivos_origen", "sha256_origen")
COBERTURA_AVISO = (0.80, 1.20)
COBERTURA_ERROR = 0.50
RESIDUOS = {
    # "<del Decreto 2351 de 1965>" o "3 <b>" son texto del editor, no etiquetas: se exigen
    # cierres, atributos o etiquetas de bloque.
    "etiqueta_html": re.compile(r"</(?:p|a|span|div|table|td|tr|b|i|u|s|strike|del|font|sup)>"
                                r"|<(?:p|a|span|div|table|td|tr|img|font|script|style)(?:\s+[\w-]+\s*=[^>]*)?\s*/?>"
                                r"|<br\s*/?>", re.I),
    "caja_sin_llenar": re.compile(r'id="?Table\d+|insRow\d+|javascript:', re.I),
    "menu_senado": re.compile(r"Ir al inicio|Anterior \| Siguiente|Derechos de autor reservados|Imprimir"),
    "ligadura": re.compile("[ﬀﬁﬂﬃﬄﬅﬆ]"),
    "reemplazo": re.compile("�"),
}
ANCLA = re.compile(r"<a\b[^>]*\bname\s*=\s*[\"']?([^\"'>]+)[\"']?[^>]*>(.*?)</a>", re.I | re.S)
TACHADO = re.compile(r"<(?:s|strike|del)\b", re.I)
# "ARTÍCULO 1", "Artículo 1.-" (Presidencia, CAN) y "ARTÍCULO PRIMERO".
ARTICULO_PDF = re.compile(r"^\s*ART[ÍI]CULO\s+(?:\d|[ÚU]NICO|PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|"
                          r"S[ÉE]PTIMO|OCTAVO|NOVENO|D[ÉE]CIMO)", re.M | re.I)


# --------------------------------------------------------------- lectura

def leer_md(path: Path) -> tuple[dict, list[str]]:
    lineas = path.read_text(encoding="utf-8").split("\n")
    meta = {}
    if lineas and lineas[0] == "---":
        fin = lineas.index("---", 1)
        for ln in lineas[1:fin]:
            k, _, v = ln.partition(": ")
            try:
                meta[k] = json.loads(v)
            except json.JSONDecodeError:
                meta[k] = v
        lineas = lineas[fin + 1:]
    return meta, lineas


def tipo_encabezado(texto: str, sentencia: bool) -> str:
    if texto.startswith("Artículo "):
        return jq.ARTICULO
    if est := jq.estructura(texto):
        return est[0]
    if sentencia:
        return jq.SECCION_SENTENCIA
    return "subtitulo"


def texto_md(lineas: list[str]) -> str:
    s = "\n".join(ln for ln in lineas if not ln.startswith("# "))
    s = re.sub(r"^#+ |^> ?|\*\*|~~|\\(?=[#>])", "", s, flags=re.M)
    return s


def html_fuente(path: Path) -> str:
    from .conversores._html import leer
    h = leer(path)
    if (i := h.find("<!--Inicio documento-->")) >= 0:
        h = h[i: h.find("<!--Fin documento-->", i) if "<!--Fin documento-->" in h[i:] else None]
    return h


def texto_de_html(h: str) -> str:
    h = re.sub(r"<(script|style|select|head)\b.*?</\1>", " ", h, flags=re.I | re.S)
    h = re.sub(r"<p[^>]*>\s*<a class=antsig.*?</p>", " ", h, flags=re.I | re.S)
    h = re.sub(r"<!--.*?-->|<[^>]+>", " ", h, flags=re.S)
    return htmlmod.unescape(h)


def fuente(raw: Path, meta: dict) -> dict:
    """Conteos de la fuente hechos sin pasar por los conversores."""
    archivos = [raw / a for a in meta.get("archivos_origen", [])]
    fmt = meta.get("formato_origen")
    out = {"articulos": None, "chars": None, "tachado": False, "metodo": ""}
    if not archivos or not all(a.exists() for a in archivos):
        out["metodo"] = "fuente no disponible"
        return out
    if fmt in ("html", "htm"):
        paginas = [html_fuente(a) for a in archivos]
        anclas = {(i, nombre) for i, h in enumerate(paginas) for nombre, txt in ANCLA.findall(h)
                  if jq.articulo(htmlmod.unescape(re.sub(r"<[^>]+>", "", txt)).strip())}
        plantilla = meta.get("conversor") == "html_plantilla"
        out["articulos"] = len(anclas) if plantilla else None
        out["metodo"] = "anclas <a name> del HTML" if plantilla else "sin anclas (texto)"
        out["chars"] = sum(len(re.sub(r"\s", "", texto_de_html(h))) for h in paginas)
        out["tachado"] = any(TACHADO.search(h) for h in paginas)
    elif fmt == "pdf":
        textos = []
        for a in archivos:
            with pymupdf.open(a) as d:
                textos.extend(p.get_text() for p in d)
        t = "\n".join(textos)
        out["articulos"] = len(ARTICULO_PDF.findall(t))
        out["metodo"] = "líneas 'ARTÍCULO N' del PDF (cota superior: incluye citas)"
        out["chars"] = len(re.sub(r"\s", "", t))
    else:
        out["metodo"] = f"formato {fmt}: sin conteo independiente"
    return out


# --------------------------------------------------------------- chequeos

def auditar(md: Path, raw: Path) -> dict:
    meta, lineas = leer_md(md)
    sentencia = meta.get("tipo_documento") == "sentencia"
    errores, avisos = collections.defaultdict(list), collections.defaultdict(list)

    # front_matter
    faltan = [c for c in CAMPOS if not meta.get(c)]
    if faltan:
        errores["front_matter"].append(f"faltan {', '.join(faltan)}")
    if meta.get("doc_id") != md.stem:
        errores["front_matter"].append(f"doc_id {meta.get('doc_id')!r} ≠ archivo {md.stem!r}")

    # titulo + jerarquia
    encabezados = []  # (linea, nivel, texto, tipo)
    for i, ln in enumerate(lineas):
        if m := re.match(r"^(#{1,6})(?: (.*))?$", ln):
            texto = (m[2] or "").strip()
            encabezados.append((i, len(m[1]), texto, None if len(m[1]) == 1 else tipo_encabezado(texto, sentencia)))
    h1 = [e for e in encabezados if e[1] == 1]
    if len(h1) != 1 or (encabezados and encabezados[0][1] != 1):
        errores["titulo"].append(f"{len(h1)} encabezados H1" + ("" if not encabezados or encabezados[0][1] == 1
                                                               else "; el primero no es H1"))
    vacios = [e for e in encabezados if not e[2]]
    if vacios:
        errores["jerarquia"].append(f"{len(vacios)} encabezados vacíos (líneas {[e[0] for e in vacios[:5]]})")
    niveles = collections.defaultdict(set)
    for _, nivel, _, tipo in encabezados:
        if tipo:
            niveles[tipo].add(nivel)
    for tipo, ns in niveles.items():
        if len(ns) > 1:
            errores["jerarquia"].append(f"{tipo} aparece en varios niveles {sorted(ns)}")
    presentes = [t for t in ORDEN if t in niveles]
    for a, b in zip(presentes, presentes[1:]):
        if min(niveles[a]) >= min(niveles[b]):
            errores["jerarquia"].append(f"{a} (H{min(niveles[a])}) no queda por encima de {b} (H{min(niveles[b])})")
    arts = [e for e in encabezados if e[3] == jq.ARTICULO]
    secciones = [e for e in encabezados if e[3] == jq.SECCION_SENTENCIA]
    if sentencia and not secciones:
        avisos["jerarquia"].append("sentencia sin secciones reconocidas")
    if not sentencia and not arts:
        errores["jerarquia"].append("norma sin artículos")

    # trazabilidad
    src = fuente(raw, meta)
    n_md = len(arts)
    if not sentencia and src["articulos"] is not None:
        if meta.get("conversor") == "html_plantilla":
            if n_md != src["articulos"]:
                errores["trazabilidad"].append(f"{n_md} artículos en el .md vs {src['articulos']} anclas en la fuente")
        elif n_md > src["articulos"]:
            errores["trazabilidad"].append(f"{n_md} artículos en el .md > {src['articulos']} líneas ARTÍCULO del PDF")
        elif src["articulos"] and n_md < 0.5 * src["articulos"]:
            avisos["trazabilidad"].append(f"solo {n_md} de {src['articulos']} líneas ARTÍCULO del PDF "
                                          "(el resto deberían ser citas)")

    # secuencia
    nums = [re.match(r"Artículo (\S+?)\.?(?: |$)", e[2]) for e in arts]
    nums = [m[1] for m in nums if m and m[1][:1].isdigit()]
    repetidos = [n for n, c in collections.Counter(nums).items() if c > 1]
    if repetidos:
        avisos["secuencia"].append(f"{len(repetidos)} números repetidos: {', '.join(repetidos[:8])}")
    retrocesos = 0
    for a, b in zip(nums, nums[1:]):
        try:
            retrocesos += jq.clave_articulo(b) < jq.clave_articulo(a)
        except TypeError:
            pass
    if nums and retrocesos > max(1, 0.02 * len(nums)):
        avisos["secuencia"].append(f"{retrocesos} retrocesos en la numeración")

    # vacios: un artículo seguido directamente de otro encabezado
    sin_texto = 0
    idx ={e[0]: k for k, e in enumerate(encabezados)}
    for e in arts:
        k = idx[e[0]]
        fin = encabezados[k + 1][0] if k + 1 < len(encabezados) else len(lineas)
        if not any(ln.strip() for ln in lineas[e[0] + 1: fin]):
            sin_texto += 1
    if sin_texto:
        (errores if sin_texto > 0.1 * len(arts) else avisos)["vacios"].append(f"{sin_texto} artículos sin texto")

    # residuos
    cuerpo = "\n".join(lineas)
    for nombre, rx in RESIDUOS.items():
        if hits := rx.findall(cuerpo):
            avisos["residuos"].append(f"{nombre}: {len(hits)} (p. ej. {hits[0]!r})")

    # cobertura
    chars_md = len(re.sub(r"\s", "", texto_md(lineas)))
    cobertura = round(chars_md / src["chars"], 3) if src["chars"] else None
    if cobertura is not None:
        if cobertura < COBERTURA_ERROR:
            errores["cobertura"].append(f"el .md tiene {cobertura:.0%} del texto de la fuente")
        elif not COBERTURA_AVISO[0] <= cobertura <= COBERTURA_AVISO[1]:
            avisos["cobertura"].append(f"el .md tiene {cobertura:.0%} del texto de la fuente")

    # tachado
    if src["tachado"] and "~~" not in cuerpo:
        errores["tachado"].append("la fuente tiene texto tachado y el .md no lo marca")

    tipos = collections.Counter(e[3] for e in encabezados if e[3])
    veredicto = "FALLA" if errores else "REVISAR" if avisos else "OK"
    return {
        "doc_id": md.stem, "titulo": meta.get("titulo"), "fuente": meta.get("fuente"),
        "formato_origen": meta.get("formato_origen"), "conversor": meta.get("conversor"),
        "tipo_documento": meta.get("tipo_documento"), "veredicto": veredicto,
        "encabezados": {t: tipos[t] for t in (*ORDEN,) if tipos[t]},
        "niveles": {t: sorted(n) for t, n in niveles.items()},
        "articulos_md": n_md, "articulos_fuente": src["articulos"], "metodo_fuente": src["metodo"],
        "cobertura": cobertura, "errores": dict(errores), "avisos": dict(avisos),
        "esquema": [f"{'#' * n} {t}" for _, n, t, tp in encabezados if tp not in (jq.ARTICULO,)][:25],
    }


# --------------------------------------------------------------- muestra y reporte

def muestrear(entradas: list[dict], n: int, semilla: int, estratificar: bool) -> list[dict]:
    rnd = random.Random(semilla)
    if len(entradas) <= n:
        return sorted(entradas, key=lambda e: e["doc_id"])
    if not estratificar:
        return sorted(rnd.sample(entradas, n), key=lambda e: e["doc_id"])
    grupos = collections.defaultdict(list)
    for e in entradas:
        grupos[e.get("formato_origen", "?")].append(e)
    # Al menos 1 por formato; el resto proporcional al tamaño del grupo.
    cuota = {g: max(1, round(n * len(v) / len(entradas))) for g, v in grupos.items()}
    while sum(cuota.values()) > n:
        cuota[max(cuota, key=cuota.get)] -= 1
    while sum(cuota.values()) < n:
        g = max(grupos, key=lambda g: len(grupos[g]) - cuota[g])
        cuota[g] += 1
    elegidos = [x for g, v in grupos.items() for x in rnd.sample(v, min(cuota[g], len(v)))]
    return sorted(elegidos, key=lambda e: e["doc_id"])


def _celda(s) -> str:
    return str(s if s is not None else "—").replace("|", "\\|")


def reporte_md(res: list[dict], cabecera: dict) -> str:
    ver = collections.Counter(r["veredicto"] for r in res)
    por_chequeo = collections.Counter()
    for r in res:
        por_chequeo.update({f"{k} (error)": 1 for k in r["errores"]})
        por_chequeo.update({f"{k} (aviso)": 1 for k in r["avisos"]})
    por_formato = collections.defaultdict(collections.Counter)
    for r in res:
        por_formato[r["formato_origen"]][r["veredicto"]] += 1
    abrev = {"parte": "P", "libro": "L", "titulo": "T", "capitulo": "C", "seccion": "S", "subseccion": "SS",
             "subtitulo": "st", jq.SECCION_SENTENCIA: "Sec", jq.ARTICULO: "A"}

    out = [f"# Auditoría de conversión a Markdown — {cabecera['fecha']}", "",
           f"- Muestra: **{len(res)}** de {cabecera['total']} documentos convertidos"
           f" ({'estratificada por formato' if cabecera['estratificar'] else 'aleatoria simple'})",
           f"- Semilla: `{cabecera['semilla']}` (repetir con `--semilla {cabecera['semilla']}`)",
           f"- Origen: `{cabecera['md']}` contra `{cabecera['raw']}`", "",
           "## Resumen", "",
           "| Veredicto | Documentos |", "|---|---:|",
           *[f"| {v} | {ver[v]} |" for v in ("OK", "REVISAR", "FALLA")], "",
           "| Formato | OK | REVISAR | FALLA |", "|---|---:|---:|---:|",
           *[f"| {f} | {c['OK']} | {c['REVISAR']} | {c['FALLA']} |" for f, c in sorted(por_formato.items())], ""]
    if por_chequeo:
        out += ["| Chequeo | Documentos |", "|---|---:|",
                *[f"| {k} | {v} |" for k, v in por_chequeo.most_common()], ""]
    out += ["## Documentos", "",
            "Encabezados: P=Parte, L=Libro, T=Título, C=Capítulo, S=Sección, st=subtítulo, "
            "A=Artículo, Sec=sección de sentencia.", "",
            "| doc_id | formato | encabezados | artículos .md / fuente | cobertura | veredicto | problemas |",
            "|---|---|---|---|---:|---|---|"]
    for r in res:
        enc = " ".join(f"{abrev.get(t, t)}{n}" for t, n in r["encabezados"].items())
        probs = "; ".join([f"**{k}**: {' / '.join(v)}" for k, v in r["errores"].items()]
                          + [f"{k}: {' / '.join(v)}" for k, v in r["avisos"].items()])
        cob = f"{r['cobertura']:.0%}" if r["cobertura"] is not None else "—"
        out.append(f"| [{r['doc_id']}](muestra/{r['doc_id']}.md) | {r['formato_origen']} | {_celda(enc)} | "
                   f"{r['articulos_md']} / {_celda(r['articulos_fuente'])} | {cob} | {r['veredicto']} | "
                   f"{_celda(probs) if probs else ''} |")
    out += ["", "## Esquema por documento", "",
            "Encabezados distintos de artículo (máx. 25), para revisar la jerarquía a ojo.", ""]
    for r in res:
        out += [f"### {r['doc_id']}", "", f"{r['titulo']} — {r['fuente']} — conversor `{r['conversor']}`, "
                f"niveles {r['niveles']}", "", "```", *(r["esquema"] or ["(sin encabezados)"]), "```", ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--md", type=Path, default=ROOT / "corpus" / "md")
    ap.add_argument("--raw", type=Path, default=ROOT / "corpus" / "raw")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--semilla", type=int, help="por defecto una nueva al azar (queda en el reporte)")
    ap.add_argument("--estratificar", action="store_true", help="repartir la muestra por formato de origen")
    ap.add_argument("--salida", type=Path, help="por defecto <md>/_auditoria/<fecha>_s<semilla>")
    args = ap.parse_args()

    manifest = json.loads((args.md / "corpus_manifest.json").read_text(encoding="utf-8"))
    entradas = [e for e in manifest if e.get("estado_conversion") in ("ok", "sin_cambios")
                and (args.md / e["archivo"]).exists()]
    if not entradas:
        raise SystemExit(f"no hay .md convertidos en {args.md}; corre antes src.ingest.convertir")
    semilla = args.semilla if args.semilla is not None else random.SystemRandom().randrange(10**6)
    elegidos = muestrear(entradas, args.n, semilla, args.estratificar)
    if len(elegidos) < args.n:
        print(f"!! solo hay {len(entradas)} documentos convertidos: se auditan todos")

    fecha = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    salida = args.salida or args.md / "_auditoria" / f"{fecha}_s{semilla}"
    (salida / "muestra").mkdir(parents=True, exist_ok=True)
    resultados = []
    for e in elegidos:
        md = args.md / e["archivo"]
        shutil.copy2(md, salida / "muestra" / md.name)
        r = auditar(md, args.raw)
        resultados.append(r)
        print(f"{r['veredicto']:8} {r['doc_id']:38} " +
              "; ".join(f"{k}: {' / '.join(v)}" for k, v in {**r["errores"], **r["avisos"]}.items()))

    cabecera = {"fecha": fecha, "semilla": semilla, "total": len(entradas), "estratificar": args.estratificar,
                "md": str(args.md), "raw": str(args.raw)}
    (salida / "reporte.json").write_text(json.dumps({**cabecera, "documentos": resultados},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    (salida / "reporte.md").write_text(reporte_md(resultados, cabecera), encoding="utf-8")
    print(dict(collections.Counter(r["veredicto"] for r in resultados)), "->", salida / "reporte.md")


if __name__ == "__main__":
    main()
