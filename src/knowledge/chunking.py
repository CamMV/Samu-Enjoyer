"""Parte corpus/md/<doc_id>.md en chunks: corpus/chunks/chunks.jsonl y chunks.sqlite.

Unidades (ver CLAUDE.md, "Chunking"):
- Normas: un chunk por artículo con su texto completo (incisos, numerales, parágrafos
  y lo tachado marcado ~~…~~) y sus notas de vigencia. Si pasa de MAX_CHARS se parte
  por párrafos en "parte_articulo"; cada parte guarda el id del artículo completo
  (`articulo_id`) para expandirla al recuperar. Las demás cajas del Senado
  (legislación anterior, notas del editor, concordancias…) van en un chunk "notas".
  Lo que va antes del primer artículo (epígrafe, considerandos) es "preambulo".
  Una norma sin artículos reconocidos se parte en ventanas ("texto").
- Sentencias: una "ficha" (inicio con descriptores/tesis + parte resolutiva) y
  ventanas de ~VENTANA caracteres por sección con un párrafo de traslape ("seccion").

Cada chunk empieza con un encabezado citable (nombre de la norma o sentencia y la
ruta Libro › Título › Capítulo): el evaluador saca las citas del texto de los
pasajes, y el modelo necesita saber de dónde viene cada uno. La jerarquía también
queda en metadatos (`ruta`, `ruta_ids`) para expandir a título o capítulo.

Uso:
  python -m src.knowledge.chunking                       # todo corpus/md
  python -m src.knowledge.chunking --solo ley_1581_2012 jurisprudencia_c-355_2006
  python -m src.knowledge.chunking --procesos 32
"""
from __future__ import annotations

import argparse
import collections
import json
import multiprocessing as mp
import re
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAX_CHARS = 2400      # ~550 tokens: por encima, el artículo se parte
VENTANA = 1700        # ~400 tokens por ventana de sentencia o texto sin artículos
MIN_CHARS = 40        # piezas más cortas se pegan a la anterior
FICHA_INICIO = 1500   # caracteres del inicio de la sentencia en la ficha
FICHA_RESUELVE = 1800
MAX_CAJA = 800        # de una nota de vigencia, lo que se queda en el chunk del artículo

# Cajas del Senado que se quedan con su artículo (responden preguntas de vigencia);
# las demás van al chunk "notas".
CAJAS_CON_ARTICULO = ("notas de vigencia", "jurisprudencia vigencia", "resumen de notas de vigencia")
ESTRUCTURA = {"parte": "parte", "libro": "libro", "titulo": "titulo", "título": "titulo",
              "capitulo": "capitulo", "capítulo": "capitulo", "seccion": "seccion", "sección": "seccion",
              "subseccion": "subseccion", "subsección": "subseccion"}
ENCABEZADO = re.compile(r"^(#{2,6}) (.+)$")
ARTICULO = re.compile(r"^Artículo (\S+?)\.?(?:\s+(.*))?$")
CAJA = re.compile(r"^> \*\*(.+?):\*\*")
RESUELVE = re.compile(r"resuelve|decisi[oó]n|decide|falla", re.I)
DOC_CAMPOS = ("titulo", "tipo_documento", "tipo_norma", "numero", "anio", "organo_emisor", "sala",
              "tipo_providencia", "radicado", "nombre_citable", "canonico", "epigrafe", "vigencia", "areas",
              "prioridad", "nivel", "origen", "citado_por", "ocr", "fuente", "url", "fecha_consulta")


# ----------------------------------------------------------------- lectura

def leer_md(path: Path) -> tuple[dict, str, int]:
    """Front matter (una clave por línea, valor JSON), cuerpo y posición del cuerpo."""
    texto = path.read_text(encoding="utf-8")
    meta, fin = {}, 0
    if texto.startswith("---\n"):
        fin = texto.index("\n---\n", 4) + 5
        for linea in texto[4:fin - 5].splitlines():
            k, _, v = linea.partition(": ")
            try:
                meta[k] = json.loads(v)
            except ValueError:
                meta[k] = v
    return meta, texto[fin:], fin


def bloques(cuerpo: str, base: int):
    """Bloques separados por línea en blanco: (inicio, fin, texto)."""
    for m in re.finditer(r"(?:[^\n]+\n?)+", cuerpo):
        t = m.group().strip("\n")
        if t.strip():
            yield base + m.start(), base + m.start() + len(t), t


def limpiar(t: str) -> str:
    """Texto de un bloque sin marcas de cita ni negrita, para leer y embeber."""
    lineas = [re.sub(r"^>\s?", "", ln) for ln in t.split("\n")]
    lineas = [ln for ln in lineas if ln.strip()]
    s = "\n".join(lineas)
    return re.sub(r"\*\*(.+?)\*\*", r"\1", s).replace("\\#", "#").replace("\\>", ">").strip()


# ------------------------------------------------------------- encabezados

def nombre_documento(meta: dict) -> str:
    """"Código Civil (Ley 57 de 1887)", "Ley 1581 de 2012", "Corte Constitucional, Sentencia C-355 de 2006"."""
    nombre = meta.get("nombre_citable") or meta.get("titulo") or meta.get("doc_id")
    if meta.get("tipo_documento") == "sentencia":
        emisor = meta.get("organo_emisor")
        sala = f", {meta['sala']}" if meta.get("sala") else ""
        return f"{emisor}{sala}, {nombre}" if emisor and not nombre.startswith(emisor) else nombre
    tipo, num, anio = meta.get("tipo_norma"), meta.get("numero"), meta.get("anio")
    if num and anio and tipo in ("ley", "decreto") and not re.search(rf"\b{num}\b", nombre):
        return f"{nombre} ({tipo.capitalize()} {num} de {anio})"
    return nombre


def encabezado(meta: dict, ruta: list[str], extra: str = "") -> str:
    partes = [nombre_documento(meta), *ruta]
    linea = " › ".join(p for p in partes if p)
    if meta.get("vigencia") and meta["vigencia"] not in ("sin_marca", None):
        linea += f" [vigencia: {meta['vigencia'].replace('_', ' ')}]"
    return f"{linea}\n{extra}".rstrip()


def tachado(t: str) -> float:
    total = len(t)
    return sum(len(x) for x in re.findall(r"~~.*?~~", t, re.S)) / total if total else 0.0


# ------------------------------------------------------------------ piezas

def partir(textos: list[tuple[int, int, str]], limite: int, traslape: bool) -> list[list[tuple[int, int, str]]]:
    """Agrupa bloques consecutivos hasta `limite` caracteres. Un bloque más largo que el
    límite se corta por oraciones. Con traslape, cada grupo repite el último bloque del anterior."""
    piezas = []
    for ini, fin, t in textos:
        if len(t) <= limite:
            piezas.append((ini, fin, t))
            continue
        pos = ini
        for trozo in re.findall(r".{1,%d}(?:[.;:]\s|\n|$)|.{1,%d}" % (limite, limite), t, re.S):
            if trozo.strip():
                piezas.append((pos, pos + len(trozo), trozo.strip()))
            pos += len(trozo)
    grupos, actual, largo = [], [], 0
    for p in piezas:
        if actual and largo + len(p[2]) > limite:
            grupos.append(actual)
            actual = [actual[-1]] if traslape and len(actual[-1][2]) < limite // 2 else []
            largo = sum(len(x[2]) for x in actual)
        actual.append(p)
        largo += len(p[2])
    if actual:
        if grupos and largo < MIN_CHARS * 5 and not traslape:
            grupos[-1].extend(actual)
        else:
            grupos.append(actual)
    return grupos


def chunk(meta: dict, cid: str, tipo: str, cabeza: str, cuerpo: list[tuple[int, int, str]], **extra) -> dict:
    texto_cuerpo = "\n\n".join(t for _, _, t in cuerpo)
    c = {"chunk_id": cid, "doc_id": meta["doc_id"], "tipo_chunk": tipo,
         "texto": f"{cabeza}\n{texto_cuerpo}".strip(),
         "inicio": cuerpo[0][0] if cuerpo else None, "fin": cuerpo[-1][1] if cuerpo else None}
    c.update(extra)
    c.update({k: meta.get(k) for k in DOC_CAMPOS if meta.get(k) not in (None, "", [])})
    c["n_chars"] = len(c["texto"])
    return c


# ------------------------------------------------------------------ normas

def chunks_norma(meta: dict, cuerpo: str, base: int) -> list[dict]:
    did = meta["doc_id"]
    out, ruta, ruta_ids = [], [], {}
    pila: list[tuple[int, str, str]] = []  # (nivel, tipo, texto)
    preambulo, anexo, articulo, usados = [], [], None, collections.Counter()

    def cerrar_articulo():
        if articulo is None:
            return
        num, titulo_art, cuerpo_art, notas, ruta_a, ids_a = articulo
        usados[num] += 1
        aid = f"{did}/art_{num}" + (f"~{usados[num]}" if usados[num] > 1 else "")
        linea_art = f"Artículo {num}." + (f" {titulo_art}" if titulo_art else "")
        cabeza = encabezado(meta, ruta_a, linea_art)
        comunes = {"articulo": num, "articulo_id": aid, "ruta": ruta_a, "ruta_ids": ids_a,
                   "derogado": tachado(" ".join(t for _, _, t in cuerpo_art)) > 0.6}
        grupos = partir(cuerpo_art, MAX_CHARS, traslape=False) if cuerpo_art else [[]]
        if len(grupos) == 1:
            out.append(chunk(meta, aid, "articulo", cabeza, grupos[0], **comunes))
        else:
            for i, g in enumerate(grupos, 1):
                out.append(chunk(meta, f"{aid}#{i}", "parte_articulo", f"{cabeza} (parte {i} de {len(grupos)})",
                                 g, parte=i, n_partes=len(grupos), **comunes))
        for i, g in enumerate(partir(notas, MAX_CHARS, traslape=False) if notas else [], 1):
            out.append(chunk(meta, f"{aid}/notas" + (f"#{i}" if i > 1 else ""), "notas",
                             f"{cabeza}\nNotas del artículo {num}:", g, **comunes))

    for ini, fin, t in bloques(cuerpo, base):
        if t.startswith("# "):
            continue
        if m := ENCABEZADO.match(t.split("\n")[0]):
            nivel, texto_h = len(m[1]), m[2].strip()
            if a := ARTICULO.match(texto_h):
                cerrar_articulo()
                articulo = (a[1].rstrip("."), (a[2] or "").strip(), [], [], list(ruta), dict(ruta_ids))
                continue
            cerrar_articulo()
            articulo = None
            primera = texto_h.split()[0].lower().rstrip(".") if texto_h.split() else ""
            tipo = ESTRUCTURA.get(primera, "subtitulo")
            pila = [p for p in pila if p[0] < nivel] + [(nivel, tipo, texto_h)]
            ruta = [p[2] for p in pila]
            ruta_ids = {p[1]: f"{did}/" + "/".join(re.sub(r"\W+", "_", q[2].lower())[:40] for q in pila[:i + 1])
                        for i, p in enumerate(pila)}
            continue
        if articulo is not None:
            caja = CAJA.match(t)
            if caja and not caja[1].lower().startswith(CAJAS_CON_ARTICULO):
                articulo[3].append((ini, fin, limpiar(t)))
            elif caja and len(t) > MAX_CAJA:
                # Nota de vigencia enorme (resúmenes de sentencias): el inicio va con el
                # artículo y la nota completa a "notas", para no inflar el artículo.
                articulo[2].append((ini, fin, limpiar(t)[:MAX_CAJA].rsplit(" ", 1)[0] + " …(sigue en notas)"))
                articulo[3].append((ini, fin, limpiar(t)))
            else:
                articulo[2].append((ini, fin, limpiar(t)))
        elif not usados and not out:
            preambulo.append((ini, fin, limpiar(t)))
        else:
            # Texto fuera de un artículo después del primero: anexos, la sentencia de revisión
            # de una ley estatutaria, tablas sueltas. Va en ventanas con su ruta.
            anexo.append((ini, fin, limpiar(t), tuple(ruta)))
    cerrar_articulo()

    tiene_articulos = any(c["tipo_chunk"] in ("articulo", "parte_articulo") for c in out)
    previos = []
    for i, g in enumerate(partir(preambulo, VENTANA, traslape=not tiene_articulos), 1):
        tipo = "preambulo" if tiene_articulos else "texto"
        previos.append(chunk(meta, f"{did}/{tipo}#{i}", tipo, encabezado(meta, []), g))
    # Anexos agrupados por ruta, en el orden en que aparecen.
    n = 0
    for ruta_a, grupo in _por_ruta(anexo):
        for g in partir(grupo, VENTANA, traslape=True):
            n += 1
            out.append(chunk(meta, f"{did}/anexo#{n}", "anexo", encabezado(meta, list(ruta_a)), g, ruta=list(ruta_a)))
    return previos + out


def _por_ruta(anexo: list[tuple]) -> list[tuple[tuple, list]]:
    grupos: list[tuple[tuple, list]] = []
    for ini, fin, t, ruta in anexo:
        if not grupos or grupos[-1][0] != ruta:
            grupos.append((ruta, []))
        grupos[-1][1].append((ini, fin, t))
    return grupos


# -------------------------------------------------------------- sentencias

def chunks_sentencia(meta: dict, cuerpo: str, base: int) -> list[dict]:
    did = meta["doc_id"]
    secciones: list[tuple[str, list]] = [("", [])]
    for ini, fin, t in bloques(cuerpo, base):
        if t.startswith("# "):
            continue
        if m := ENCABEZADO.match(t.split("\n")[0]):
            secciones.append((m[2].strip(), []))
            resto = t.split("\n", 1)[1:] if "\n" in t else []
            if resto and resto[0].strip():
                secciones[-1][1].append((ini, fin, limpiar(resto[0])))
            continue
        secciones[-1][1].append((ini, fin, limpiar(t)))

    out = []
    inicio = [b for b in secciones[0][1]]
    resuelve = next((s for s in reversed(secciones[1:]) if RESUELVE.search(s[0])), None)
    ficha = []
    for bl in inicio:
        if sum(len(x[2]) for x in ficha) >= FICHA_INICIO:
            break
        ficha.append(bl)
    if resuelve:
        texto_r = []
        for bl in resuelve[1]:
            if sum(len(x[2]) for x in texto_r) >= FICHA_RESUELVE:
                break
            texto_r.append(bl)
        ficha += [(texto_r[0][0] if texto_r else 0, texto_r[0][0] if texto_r else 0, f"{resuelve[0]}:")] + texto_r
    if ficha:
        out.append(chunk(meta, f"{did}/ficha", "ficha", encabezado(meta, ["Ficha"]), ficha))

    usados = collections.Counter()
    for k, (titulo_s, bls) in enumerate(secciones):
        nombre = titulo_s or "Inicio"
        clave = re.sub(r"\W+", "_", nombre.lower()).strip("_")[:30] or "inicio"
        usados[clave] += 1
        sid = f"{did}/{clave}" + (f"~{usados[clave]}" if usados[clave] > 1 else "")
        grupos = partir(bls, VENTANA, traslape=True)
        for i, g in enumerate(grupos, 1):
            cabeza = encabezado(meta, [nombre + (f" ({i}/{len(grupos)})" if len(grupos) > 1 else "")])
            out.append(chunk(meta, f"{sid}#{i}", "seccion", cabeza, g, seccion=nombre, seccion_id=sid,
                             ventana=i, n_ventanas=len(grupos), orden_seccion=k))
    return out


# -------------------------------------------------------------------- main

def chunks_de(path: Path) -> list[dict]:
    meta, cuerpo, base = leer_md(path)
    meta.setdefault("doc_id", path.stem)
    if meta.get("tipo_documento") == "sentencia" or meta["doc_id"].startswith("jurisprudencia_"):
        return chunks_sentencia(meta, cuerpo, base)
    return chunks_norma(meta, cuerpo, base)


def _trabajo(path: str) -> tuple[str, list[dict] | str]:
    try:
        return path, chunks_de(Path(path))
    except Exception as e:  # noqa: BLE001 - se registra y se sigue
        return path, f"{type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--md", type=Path, default=ROOT / "corpus" / "md")
    ap.add_argument("--salida", type=Path, default=ROOT / "corpus" / "chunks")
    ap.add_argument("--solo", nargs="+", help="doc_id a procesar")
    ap.add_argument("--procesos", type=int, default=max(1, mp.cpu_count() - 1))
    args = ap.parse_args()

    archivos = sorted(p for p in args.md.glob("*.md") if not args.solo or p.stem in args.solo)
    args.salida.mkdir(parents=True, exist_ok=True)
    jsonl, db_path = args.salida / "chunks.jsonl", args.salida / "chunks.sqlite"
    db_path.unlink(missing_ok=True)
    db = sqlite3.connect(db_path)
    db.execute("CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, doc_id TEXT, articulo_id TEXT, "
               "seccion_id TEXT, tipo_chunk TEXT, datos TEXT)")
    stats, fallas, t0 = collections.Counter(), [], time.time()
    print(f"== {len(archivos)} documentos -> {args.salida}", flush=True)
    with jsonl.open("w", encoding="utf-8", newline="\n") as f, mp.Pool(args.procesos) as pool:
        # imap conserva el orden: el archivo queda igual en cualquier máquina.
        for i, (path, res) in enumerate(pool.imap(_trabajo, map(str, archivos), chunksize=16), 1):
            if isinstance(res, str):
                fallas.append({"archivo": path, "error": res})
                continue
            filas = []
            for c in res:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
                stats[c["tipo_chunk"]] += 1
                stats["chars"] += c["n_chars"]
                filas.append((c["chunk_id"], c["doc_id"], c.get("articulo_id"), c.get("seccion_id"),
                              c["tipo_chunk"], json.dumps(c, ensure_ascii=False)))
            db.executemany("INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?,?)", filas)
            if i % 2000 == 0:
                db.commit()
                print(f"   {i}/{len(archivos)} documentos, {sum(v for k, v in stats.items() if k != 'chars')} "
                      f"chunks, {time.time() - t0:.0f} s", flush=True)
    for col in ("doc_id", "articulo_id", "seccion_id"):
        db.execute(f"CREATE INDEX idx_{col} ON chunks({col})")
    db.commit()
    db.close()
    resumen = {"documentos": len(archivos), "fallas": fallas, "chunks": {k: v for k, v in stats.items() if k != "chars"},
               "total_chunks": sum(v for k, v in stats.items() if k != "chars"), "chars": stats["chars"],
               "tokens_aprox": int(stats["chars"] / 4), "segundos": round(time.time() - t0)}
    (args.salida / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in resumen.items() if k != "fallas"}, ensure_ascii=False), f"fallas: {len(fallas)}")


if __name__ == "__main__":
    main()
