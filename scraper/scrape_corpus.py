"""Descarga los documentos de data/seed_targets.json, sigue sus hipervínculos y
arma corpus_manifest.json.

Los enlaces `donde_buscar` del seed son búsquedas `?q=` que esos sitios no
atienden (redirigen a un índice). En su lugar, cada norma se resuelve a su URL
real según el tipo:

  jurisprudencia C/T/SU  -> Corte Constitucional  relatoria/<año>/C-355-06.htm
                            (las C, si faltan, se buscan en el Senado: c-355_2006.html)
  jurisprudencia SC/SL/SP-> Corte Suprema, API de consultaprovidencias (PDF)
  ley / decreto / códigos -> Secretaría del Senado basedoc; si no está, Colpensiones
  si nada de lo anterior -> búsqueda en Bing filtrada a Función Pública / SUIN
  Decisión Andina 486    -> PDF oficial de la Comunidad Andina

Si `donde_buscar` ya es la URL del documento (no una búsqueda `?q=`), se usa
tal cual: Senado, Colpensiones, DIAN, Cancillería, Corte Constitucional y
Función Pública.

Senado, Colpensiones, DIAN y Cancillería publican con la misma plantilla: cada
norma está partida en <stem>.htm(l) + <stem>_prNNN.htm(l). Las páginas se toman
del selector "Artículo" (mapa artículo -> página) y de los enlaces
Anterior/Siguiente, así no se pierde ninguna. Las cajas Concordancias,
Jurisprudencia, Notas de Vigencia, etc. vienen vacías en el HTML y se llenan
desde js/<página>.js: se incrustan en el HTML guardado. Todas las páginas de una
norma son UN documento (un doc_id); se guardan como <doc_id>_pNNN.html.

Expansión: los hipervínculos de esas páginas y cajas apuntan a otras normas y
sentencias. Con --profundidad N se descargan también (las más citadas primero),
buscándolas en el Senado, luego en Colpensiones y luego en el sitio que las
enlazó. Cada documento se guarda una sola vez: se deduplica por doc_id canónico
(ley_0080_1993 == ley_80_1993, ley_1564_2012 == codigo_general_proceso) y por
hash de contenido.

Uso:
  python scraper/scrape_corpus.py                          # seed + enlaces directos (profundidad 1)
  python scraper/scrape_corpus.py --profundidad 0          # solo el seed
  python scraper/scrape_corpus.py --expandir normas        # no seguir sentencias enlazadas
  python scraper/scrape_corpus.py --max-enlazados 300      # solo los 300 más citados por nivel
  python scraper/scrape_corpus.py --solo "Ley 80"          # filtra el seed por nombre
  python scraper/scrape_corpus.py --seed a.json b.json     # varios archivos de documentos
  python scraper/scrape_corpus.py --pdf                    # además imprime los HTML a PDF (Playwright)

Se puede cortar y volver a correr: lo ya descargado se salta. Lo que falle queda
con "estado": "falla" en corpus_manifest.json; pon su URL en
data/urls_manuales.json ({"ley_50_1990": "https://..."}) y vuelve a correr.
"""
from __future__ import annotations

import argparse
import base64
import collections
import concurrent.futures as cf
import datetime as dt
import hashlib
import html
import json
import re
import threading
import time
import urllib.parse as up
from pathlib import Path

import requests
import urllib3

ROOT = Path(__file__).resolve().parent.parent
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
SENADO = "http://www.secretariasenado.gov.co/senado/basedoc/"
CC = "https://www.corteconstitucional.gov.co/relatoria/"
CSJ_API = "https://consultaprovidenciasbk.cortesuprema.gov.co"
COLPENSIONES = "https://normativa.colpensiones.gov.co/colpens/docs/"
FUENTE_SENADO = "Secretaría del Senado - Base documental"
# Sitios con la plantilla del Senado (páginas _prNNN + cajas en js/<página>.js).
FUENTES_PLANTILLA = {
    "secretariasenado.gov.co": FUENTE_SENADO,
    "normativa.colpensiones.gov.co": "Colpensiones - Normativa",
    "normograma.dian.gov.co": "DIAN - Normograma",
    "cancilleria.gov.co": "Cancillería - Normograma",
}
# funcionpublica.gov.co sirve una cadena de certificados incompleta.
SIN_VERIFICAR_SSL = ("funcionpublica.gov.co",)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Códigos que en el Senado viven con otro nombre de archivo.
SENADO_CODIGOS = {
    "constitucion": "constitucion_politica_1991",
    "codigo_general_proceso": "ley_1564_2012",
    "codigo_sustantivo_trabajo": "codigo_sustantivo_trabajo",
    "estatuto_tributario": "estatuto_tributario",
    "estatuto_consumidor": "ley_1480_2011",
    "codigo_infancia": "ley_1098_2006",
    "codigo_disciplinario": "ley_1952_2019",
    "codigo_nacional_policia": "ley_1801_2016",
    "codigo_civil": "codigo_civil",
    "codigo_comercio": "codigo_comercio",
    "codigo_penal": "ley_0599_2000",
    "codigo_procedimiento_penal": "ley_0906_2004",
    "codigo_procedimiento_administrativo": "ley_1437_2011",
    "codigo_penitenciario": "ley_0065_1993",
    "codigo_penal_militar": "ley_1407_2010",
    "codigo_disciplinario_abogado": "ley_1123_2007",
    "codigo_minas": "ley_0685_2001",
    "codigo_regimen_municipal": "decreto_1333_1986",  # solo en Colpensiones
}
PDF_DIRECTOS = {
    "decision_andina_486": ("Comunidad Andina",
                            "https://www.comunidadandina.org/StaticFiles/DocOf/DEC486.pdf"),
}
CSJ_SALAS = {"SC": "Civil", "SL": "Laboral", "SP": "Penal", "STC": "Tutelas",
             "STL": "Tutelas", "STP": "Tutelas", "AC": "Civil", "AL": "Laboral", "AP": "Penal"}
# Dominios aceptados cuando se recurre al buscador, en orden de preferencia.
DOMINIOS_FALLBACK = ("suin-juriscol.gov.co", "funcionpublica.gov.co", "secretariasenado.gov.co")

# Enlace relativo a otro documento del mismo sitio: "ley_1648_2013.html#1", "c-541_1992.htm".
ENLACE_DOC = re.compile(
    r"""href=['"](?:https?://www\.secretariasenado\.gov\.co/senado/basedoc/)?"""
    r"""([a-z][a-z0-9_\-]*?)(?:_pr\d+)?\.html?(?:#[^'"]*)?['"]""", re.I)
NO_DOCUMENTOS = {"index", "arbol", "busqueda", "basedoc", "doctrina", "herramientas_busqueda",
                 "indice_por_temas_misionales"}
# Caja que js/<página>.js inserta en <table id="TableN">.
CAJA_JS = re.compile(
    r"""function insRow\d+\(\)\s*\{\s*var description = new Array\(\);\s*"""
    r"""description\[0\] = "(.*?)";\s*var z=document\.getElementById\('([^']+)'\)""", re.S)

_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "es-CO,es;q=0.9"})


class NoEncontrado(Exception):
    pass


def get(url: str, *, intentos: int = 4, **kw) -> requests.Response:
    """GET/POST con reintentos: el Senado corta conexiones con frecuencia."""
    metodo = kw.pop("method", "GET")
    verify = not any(d in url for d in SIN_VERIFICAR_SSL)
    for i in range(intentos):
        try:
            r = _session.request(metodo, url, timeout=90, verify=verify, **kw)
            if r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code}")
            return r
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
            if i == intentos - 1:
                raise
            time.sleep(2 * (i + 1))
    raise AssertionError


# --------------------------------------------------------------- identificadores

def _num(p: str) -> str:
    return str(int(p)) if p.isdigit() else p


def doc_id(canonico: list) -> str:
    return "_".join(_num(str(p)) for p in canonico if p).lower()


def doc_id_senado(stem: str) -> str:
    """ley_0080_1993 -> ley_80_1993 ; c-055_2022 -> jurisprudencia_c-55_2022."""
    stem = stem.lower()
    if m := re.fullmatch(r"(c|t|su)-0*(\d+)_(\d{4})", stem):
        return f"jurisprudencia_{m[1]}-{int(m[2])}_{m[3]}"
    if m := re.fullmatch(r"([a-z_]+?)_0*(\d+)_(\d{4})", stem):
        return f"{m[1]}_{int(m[2])}_{m[3]}"
    return stem


# Una misma norma con dos nombres: ley_1564_2012 es el codigo_general_proceso del seed.
ALIAS = {doc_id_senado(stem): did for did, stem in SENADO_CODIGOS.items()}


def canonico(did: str) -> str:
    return ALIAS.get(did, did)


def titulo_senado(stem: str) -> str:
    stem = stem.lower()
    if m := re.fullmatch(r"(c|t|su)-0*(\d+)_(\d{4})", stem):
        return f"Sentencia {m[1].upper()}-{int(m[2])} de {m[3]}"
    if m := re.fullmatch(r"([a-z_]+?)_0*(\d+)_(\d{4})", stem):
        return f"{m[1].replace('_', ' ').capitalize()} {int(m[2])} de {m[3]}"
    return stem.replace("_", " ").capitalize()


def es_sentencia(stem: str) -> bool:
    return bool(re.match(r"(c|t|su)-\d", stem, re.I))


# --------------------------------------------------------------- resolvers
# Cada resolver devuelve (fuente, [(url, bytes, extension), ...], enlaces) o lanza
# NoEncontrado. `enlaces` es un Counter de stems del Senado citados por el documento.

def corte_constitucional(tipo: str, num: str, anio: str):
    yy = anio[-2:]
    n = int(num)
    candidatos = ([f"SU{n:03d}-{yy}", f"SU-{n:03d}-{yy}", f"SU{n}-{yy}"] if tipo == "SU"
                  else [f"{tipo}-{n:03d}-{yy}", f"{tipo}-{n}-{yy}"])
    for nombre in candidatos:
        url = f"{CC}{anio}/{nombre}.htm"
        r = get(url)
        # Una sentencia inexistente devuelve 200 con una página genérica de ~8 KB.
        if r.status_code == 200 and len(r.content) > 20_000:
            return "Corte Constitucional - Relatoría", [(url, r.content, "htm")], collections.Counter()
    if tipo == "C":  # el Senado replica las sentencias de constitucionalidad
        return senado(f"c-{n:03d}_{anio}")
    raise NoEncontrado(f"{tipo}-{num}-{anio} no está en la relatoría de la CC")


def corte_suprema(tipo: str, num: str, anio: str):
    sala = CSJ_SALAS.get(tipo)
    if not sala:
        raise NoEncontrado(f"prefijo {tipo} sin sala conocida")
    # Los títulos traen sufijos: "SP1680-2022(60875).pdf", "SC1121-2018 [2007-00128-01].docx".
    objetivo = re.compile(rf"^{tipo}0*{int(num)}-{anio}(?:[\s(\[].*)?\.(pdf|docx?)$", re.I)
    # Primero búsqueda exacta filtrada por año; si no aparece, búsqueda libre sin año.
    for exacta, filtro_anio, paginas in (("true", anio, 5), ("false", anio, 10), ("true", "", 10)):
        for start in range(0, 10 * paginas, 10):
            gql = ('{ getSearchResult(searchQuery:{ query: "%s%s-%s" typeOfQuery: "%s" start: %d '
                   'isExact: %s magistrate:"" year:"%s" autoSentencia: "" order: "" '
                   'roomTutelas: "" addedQueries: [] }) { searchResults { title onlinePath } numOfResults } }'
                   % (tipo, num, anio, sala, start, exacta, filtro_anio))
            data = get(f"{CSJ_API}/api", method="POST", json={"query": gql}).json()
            res = data["data"]["getSearchResult"]["searchResults"] or []
            hits = [x for x in res if objetivo.match(x["title"])]
            # Preferir PDF; si solo hay .doc el endpoint también lo convierte a PDF.
            hits.sort(key=lambda x: not x["title"].lower().endswith(".pdf"))
            # Algunas solo existen en Word: si no hay PDF se guarda el .doc/.docx original.
            for hit in hits:
                original = hit["onlinePath"]
                for path in dict.fromkeys([re.sub(r"\.docx?$", ".pdf", original), original]):
                    r = get(f"{CSJ_API}/downloadFile", method="POST", json={"path": path})
                    ext = path.rsplit(".", 1)[-1].lower()
                    es_valido = b"%PDF" in r.content[:20] if ext == "pdf" else r.content[:4] in (
                        b"\xd0\xcf\x11\xe0", b"PK\x03\x04")  # firmas de .doc (OLE) y .docx (zip)
                    if r.ok and es_valido:
                        url = f"{CSJ_API}/downloadFile?path={up.quote(path)}"
                        return "Corte Suprema de Justicia - Relatoría", [(url, r.content, ext)], collections.Counter()
            if len(res) < 10:
                break
    raise NoEncontrado(f"{tipo}{num}-{anio} no aparece en consultaprovidencias")


def incrustar_cajas(pagina: str, js: str) -> str:
    """Mete en cada <table id="TableN"> vacía el contenido que le asigna insRowN()."""
    cajas = {tabla: re.sub(r"\\(.)", r"\1", contenido) for contenido, tabla in CAJA_JS.findall(js)}

    def llenar(m: re.Match) -> str:
        return m[1] + cajas.get(m[2], "") + m[3]
    return re.sub(r'(<table id="(Table\d+)"[^>]*>)\s*(</table>)', llenar, pagina)


def plantilla(base: str, stem: str, ext: str = "html"):
    """Descarga todas las páginas de una norma con la plantilla del Senado.

    `base` es el directorio (p. ej. SENADO o COLPENSIONES) y `ext` "html" o "htm".
    Devuelve las páginas con sus cajas incrustadas y los documentos que enlazan.
    """
    stem = stem.lower()
    r = get(f"{base}{stem}.{ext}")
    if r.status_code != 200 or len(r.content) < 3_000:
        raise NoEncontrado(f"{stem}.{ext} no existe en {up.urlparse(base).netloc}")
    # Casi todos están en ISO-8859-1 (latin-1 ida y vuelta no pierde bytes); Cancillería en UTF-8.
    enc = "utf-8" if re.search(rb"charset=[\"']?utf-8", r.content[:3000], re.I) else "latin-1"
    principal = r.content.decode(enc, "replace")
    # Selector "Artículo": value="_pr001\xe7#33" -> el artículo 33 está en _pr001.
    paginas = {stem} | {stem + p.lower() for p in re.findall(r'<option value="(_pr\d+)', principal)}
    siguiente = re.compile(rf"({re.escape(stem)}_pr\d+)\.{ext}\b", re.I)
    textos = {stem: principal}
    paginas |= {p.lower() for p in siguiente.findall(principal)}
    cola = sorted(paginas - {stem})
    while cola:
        nombre = cola.pop(0)
        rp = get(f"{base}{nombre}.{ext}")
        if rp.status_code != 200:
            continue
        textos[nombre] = rp.content.decode(enc, "replace")
        for p in siguiente.findall(textos[nombre]):
            if p.lower() not in paginas:
                paginas.add(p.lower())
                cola.append(p.lower())

    partes, enlaces = [], collections.Counter()
    for nombre in sorted(textos, key=lambda n: (n != stem, n)):
        pagina = textos[nombre]
        rj = get(f"{base}js/{nombre}.js")
        if rj.status_code == 200:
            pagina = incrustar_cajas(pagina, rj.content.decode(enc, "replace"))
        for destino in ENLACE_DOC.findall(pagina):
            destino = destino.lower()
            if destino != stem and destino not in NO_DOCUMENTOS:
                enlaces[destino] += 1
        partes.append((f"{base}{nombre}.{ext}", pagina.encode(enc, "replace"), "html"))
    fuente = next(f for d, f in FUENTES_PLANTILLA.items() if d in base)
    return fuente, partes, enlaces


def senado(stem: str):
    return plantilla(SENADO, stem, "html")


def colpensiones(stem: str):
    return plantilla(COLPENSIONES, stem, "htm")


def senado_o_colpensiones(stem: str):
    try:
        return senado(stem)
    except NoEncontrado:
        return colpensiones(stem)


def _bing(q: str) -> list[str]:
    r = get("https://www.bing.com/search", params={"q": q, "setlang": "es"})
    links = []
    for href in re.findall(r'<h2[^>]*><a[^>]+href="([^"]+)"', r.text):
        href = html.unescape(href)
        m = re.search(r"[?&]u=a1([^&]+)", href)  # enlaces envueltos en bing.com/ck
        if m:
            s = m.group(1) + "=" * (-len(m.group(1)) % 4)
            href = base64.urlsafe_b64decode(s).decode("utf-8", "ignore")
        links.append(href)
    return links


def buscador(tipo: str, num: str, anio: str):
    """Último recurso: buscar la norma y quedarse con un resultado oficial verificable."""
    titulo = f"{tipo.capitalize()} {int(num)} de {anio}"
    verificar = re.compile(rf"{tipo}\s+0*{int(num)}\s+de\s+(?:\d+\s+de\s+\w+\s+de\s+)?{anio}", re.I)
    links = _bing(f'"{titulo}" norma')
    for dominio in DOMINIOS_FALLBACK:
        for url in links:
            if dominio not in url or "/arbol/" in url:
                continue
            url = url.replace("norma_pdf.php", "norma.php")  # verificar sobre el HTML
            r = get(url)
            texto = r.content.decode(r.encoding or "utf-8", "ignore")
            cab = re.sub(r"<[^>]+>", " ", texto[:60_000])
            if r.status_code == 200 and verificar.search(cab):
                return descargar_url(url)
    raise NoEncontrado(f"{titulo}: sin resultado oficial verificable")


def descargar_url(url: str):
    """Descarga una URL conocida; en Función Pública prefiere la versión PDF."""
    host = up.urlparse(url).netloc
    if any(d in host for d in FUENTES_PLANTILLA) and re.search(r"\.html?(#.*)?$", url):
        base, archivo = url.split("#")[0].rsplit("/", 1)
        stem, ext = re.fullmatch(r"(.+?)(?:_pr\d+)?\.(html?)", archivo).groups()
        return plantilla(base + "/", stem, ext)
    if url.startswith(f"{CSJ_API}/downloadFile"):  # la Corte Suprema descarga por POST
        path = up.unquote(up.parse_qs(up.urlparse(url).query)["path"][0])
        r = get(f"{CSJ_API}/downloadFile", method="POST", json={"path": path})
        if not r.ok or len(r.content) < 1_000:
            raise NoEncontrado(f"{path} no se pudo descargar de la Corte Suprema")
        return "Corte Suprema de Justicia - Relatoría", [(url, r.content, path.rsplit(".", 1)[-1].lower())], \
            collections.Counter()
    if "corteconstitucional.gov.co/relatoria/" in url:
        r = get(url)
        # Una sentencia inexistente devuelve 200 con una página genérica de ~8 KB.
        if r.status_code != 200 or len(r.content) < 20_000:
            raise NoEncontrado(f"{url} no es una sentencia publicada")
        return "Corte Constitucional - Relatoría", [(url, r.content, "htm")], collections.Counter()
    if "funcionpublica.gov.co" in url and (m := re.search(r"[?&]i=(\d+)", url)):
        pdf_url = f"https://www.funcionpublica.gov.co/eva/gestornormativo/norma_pdf.php?i={m.group(1)}"
        rp = get(pdf_url)
        if b"%PDF" in rp.content[:20]:
            return "Función Pública - Gestor Normativo", [(pdf_url, rp.content, "pdf")], collections.Counter()
    r = get(url)
    if r.status_code != 200:
        raise NoEncontrado(f"{url} respondió {r.status_code}")
    es_pdf = b"%PDF" in r.content[:20]
    return up.urlparse(url).netloc, [(url, r.content, "pdf" if es_pdf else "html")], collections.Counter()


def resolver(doc: dict, manuales: dict):
    t, num, anio = doc["canonico"]
    if (url := manuales.get(doc_id(doc["canonico"]))):
        return descargar_url(url)
    if "stem_enlace" in doc:  # documento descubierto por un enlace
        return enlazado(doc["stem_enlace"], doc.get("bases_enlace", []))
    url = doc.get("donde_buscar", "")
    if url and "?q=" not in url:  # ya es la URL del documento, no una búsqueda
        return descargar_url(url)
    if t in PDF_DIRECTOS:
        fuente, url = PDF_DIRECTOS[t]
        return fuente, [(url, get(url).content, "pdf")], collections.Counter()
    if t in SENADO_CODIGOS:
        return senado_o_colpensiones(SENADO_CODIGOS[t])
    if t == "jurisprudencia":
        tipo, n = num.split("-", 1)
        if tipo in ("C", "T", "SU", "A"):
            return corte_constitucional(tipo, n, anio)
        return corte_suprema(tipo, n, anio)
    if t in ("ley", "decreto") and num and anio:
        try:
            return senado_o_colpensiones(f"{t}_{int(num):04d}_{anio}")
        except NoEncontrado:
            return buscador(t, num, anio)
    if num and anio:
        return buscador(t, num, anio)
    raise NoEncontrado(f"sin resolver para {t}")


def enlazado(stem: str, bases: list[str]):
    """Documento descubierto por un enlace: Senado, Colpensiones y luego el sitio que lo enlazó."""
    for base in dict.fromkeys([SENADO, COLPENSIONES, *bases]):
        try:
            return plantilla(base, stem, "html" if base == SENADO else "htm")
        except NoEncontrado:
            continue
    raise NoEncontrado(f"{stem} no está en Senado, Colpensiones ni en el sitio que lo enlaza")


# --------------------------------------------------------------- pipeline

class Corpus:
    """Estado compartido entre hilos: manifest, hashes ya guardados y escritura."""

    def __init__(self, salida: Path, manuales: dict):
        self.salida = salida
        self.manuales = manuales
        self.path = salida / "corpus_manifest.json"
        self.registros: dict[str, dict] = {}
        if self.path.exists():
            self.registros = {r["doc_id"]: r for r in json.loads(self.path.read_text(encoding="utf-8"))}
        self.hashes = {h: r["doc_id"] for r in self.registros.values() for h in r.get("sha256", [])}
        self.lock = threading.Lock()

    def ya_listo(self, did: str) -> bool:
        r = self.registros.get(did)
        return bool(r and r["estado"] in ("ok", "duplicado")
                    and all((self.salida / a).exists() for a in r.get("archivos", [])))

    def guardar(self):
        with self.lock:
            datos = sorted(self.registros.values(), key=lambda r: r["doc_id"])
            self.path.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")

    def procesar(self, doc: dict) -> dict:
        did = canonico(doc_id(doc["canonico"]) if "stem_enlace" not in doc else doc_id_senado(doc["stem_enlace"]))
        registro = {"doc_id": did, "titulo": doc["norma"], "areas": sorted(doc["areas"]),
                    "origen": doc.get("origen", "seed"), "profundidad": doc.get("profundidad", 0)}
        for k in ("items_del_banco", "citado_por", "prioridad", "vigencia", "nota", "tema", "areas_inferidas"):
            if k in doc:
                registro[k] = doc[k]
        if self.ya_listo(did):
            return self.registros[did]
        try:
            fuente, partes, enlaces = resolver(doc, self.manuales)
        except Exception as e:  # noqa: BLE001 - se registra y se sigue con el resto
            registro |= {"estado": "falla", "error": f"{type(e).__name__}: {e}"}
            with self.lock:
                self.registros[did] = registro
            return registro

        hashes = [hashlib.sha256(c).hexdigest() for _, c, _ in partes]
        with self.lock:
            # Mismo contenido ya guardado con otro doc_id (p. ej. una URL manual repetida).
            if (previo := self.hashes.get(hashes[0])) and previo != did:
                registro |= {"estado": "duplicado", "duplicado_de": previo, "url": partes[0][0]}
                self.registros[did] = registro
                return registro
            for h in hashes:
                self.hashes.setdefault(h, did)

        carpeta = self.salida / did
        carpeta.mkdir(parents=True, exist_ok=True)
        archivos = []
        for i, (url, contenido, ext) in enumerate(partes):
            f = carpeta / (f"{did}.{ext}" if len(partes) == 1 else f"{did}_p{i:03d}.{ext}")
            f.write_bytes(contenido)
            archivos.append(f.relative_to(self.salida).as_posix())
        registro |= {"fuente": fuente, "url": partes[0][0], "urls": [p[0] for p in partes],
                     "fecha_consulta": dt.date.today().isoformat(), "archivos": archivos,
                     "sha256": hashes, "enlaces": dict(enlaces.most_common()),
                     "base_enlaces": partes[0][0].rsplit("/", 1)[0] + "/", "estado": "ok"}
        with self.lock:
            self.registros[did] = registro
        return registro

    def correr(self, docs: list[dict], hilos: int):
        with cf.ThreadPoolExecutor(hilos) as ex:
            for i, r in enumerate(ex.map(self.procesar, docs), 1):
                marca = {"ok": "OK ", "duplicado": "== "}.get(r["estado"], "XX ")
                print(marca, r["doc_id"].ljust(36), r.get("fuente") or r.get("duplicado_de") or r.get("error"),
                      flush=True)
                if i % 50 == 0:
                    self.guardar()
        self.guardar()


def candidatos(corpus: Corpus, nivel: int, tipos: set[str]) -> list[dict]:
    """Documentos enlazados desde el nivel anterior que aún no están en el corpus."""
    citas, areas, bases = collections.Counter(), collections.defaultdict(set), collections.defaultdict(set)
    for r in corpus.registros.values():
        if r["estado"] != "ok" or r.get("profundidad", 0) != nivel - 1:
            continue
        for stem, n in r.get("enlaces", {}).items():
            citas[stem] += n
            areas[stem] |= set(r.get("areas", []))
            if r.get("base_enlaces"):
                bases[stem].add(r["base_enlaces"])
    docs, vistos = [], set(corpus.registros)
    for stem, n in citas.most_common():
        did = canonico(doc_id_senado(stem))
        tipo = "sentencias" if es_sentencia(stem) else "normas"
        if did in vistos or tipo not in tipos:
            continue
        vistos.add(did)
        docs.append({"norma": titulo_senado(stem), "canonico": [did, None, None], "stem_enlace": stem,
                     "bases_enlace": sorted(bases[stem]), "areas": sorted(areas[stem]), "origen": "enlace",
                     "profundidad": nivel, "citado_por": n})
    return docs


def html_a_pdf(archivos: list[Path]):
    from playwright.sync_api import sync_playwright  # opcional: pip install playwright
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page()
        for f in archivos:
            pag.goto(f.resolve().as_uri(), wait_until="domcontentloaded")
            pag.pdf(path=str(f.with_suffix(".pdf")), format="A4")
        nav.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", nargs="+", default=[ROOT / "data" / "seed_targets.json"], type=Path,
                    help="uno o más JSON con la forma de seed_targets.json")
    ap.add_argument("--salida", default=ROOT / "corpus" / "raw", type=Path)
    ap.add_argument("--solo", help="procesa solo normas del seed cuyo nombre contenga este texto")
    ap.add_argument("--manuales", default=ROOT / "data" / "urls_manuales.json", type=Path,
                    help="JSON {doc_id: url} para normas que no se resuelven solas")
    ap.add_argument("--profundidad", type=int, default=1,
                    help="niveles de hipervínculos a seguir desde el seed (0 = solo seed)")
    ap.add_argument("--expandir", default="normas,sentencias",
                    help="qué enlaces seguir: normas, sentencias o ambos separados por coma")
    ap.add_argument("--max-enlazados", type=int, default=0,
                    help="máximo de documentos enlazados por nivel, los más citados primero (0 = todos)")
    ap.add_argument("--hilos", type=int, default=4)
    ap.add_argument("--pdf", action="store_true", help="convierte también cada HTML a PDF con Playwright")
    args = ap.parse_args()

    docs = [d for f in args.seed for d in json.loads(f.read_text(encoding="utf-8"))["documentos"]]
    if args.solo:
        docs = [d for d in docs if args.solo.lower() in d["norma"].lower()]
    manuales = json.loads(args.manuales.read_text(encoding="utf-8")) if args.manuales.exists() else {}
    args.salida.mkdir(parents=True, exist_ok=True)
    corpus = Corpus(args.salida, manuales)

    print(f"== nivel 0: {len(docs)} documentos de {', '.join(f.name for f in args.seed)}")
    corpus.correr(docs, args.hilos)
    tipos = {t.strip() for t in args.expandir.split(",")}
    for nivel in range(1, args.profundidad + 1):
        nuevos = candidatos(corpus, nivel, tipos)
        if args.max_enlazados:
            nuevos = nuevos[:args.max_enlazados]
        print(f"\n== nivel {nivel}: {len(nuevos)} documentos enlazados nuevos")
        if not nuevos:
            break
        corpus.correr(nuevos, args.hilos)

    estados = collections.Counter(r["estado"] for r in corpus.registros.values())
    print(f"\n{dict(estados)} -> {corpus.path}")

    if args.pdf:
        htmls = [args.salida / a for r in corpus.registros.values() if r["estado"] == "ok"
                 for a in r["archivos"] if a.endswith((".html", ".htm"))]
        html_a_pdf([h for h in htmls if not h.with_suffix(".pdf").exists()])


if __name__ == "__main__":
    main()
