"""Convierte corpus/raw a Markdown: un .md por documento (doc_id) en corpus/md/.

Cada .md trae front matter YAML con la procedencia (fuente, url, fecha de
consulta, archivos y sha256 de origen), los metadatos jurídicos (tipo de norma,
número, año, órgano emisor, vigencia; ver metadatos.py) y el cuerpo con la
jerarquía como encabezados: # título del documento, luego Parte/Libro/Título/
Capítulo/Sección y "Artículo N." con niveles asignados según lo que tenga cada
norma. Las sentencias se dividen por secciones (antecedentes, consideraciones,
decisión). Texto tachado en la fuente (inexequible o derogado) queda como ~~…~~,
las cajas del Senado (concordancias, notas de vigencia…) como citas
"> **Rótulo:**" y las tablas de datos como tablas Markdown.

Uso:
  python -m src.ingest.convertir                       # todo lo que está "ok" en el manifest
  python -m src.ingest.convertir --solo constitucion ley_1581_2012
  python -m src.ingest.convertir --forzar              # reconvierte aunque el origen no cambió
  python -m src.ingest.convertir --fondo               # en segundo plano, desacoplado de la terminal
  python -m src.ingest.convertir --estado              # avance de la corrida en segundo plano
  python -m src.ingest.convertir --parar               # parada limpia (termina lo que está en curso)

Se puede cortar y relanzar: un .md cuyo sha256 de origen coincide se salta, y el
manifest del corpus convertido se guarda cada 200 documentos o 2 minutos.
Los .doc se pasan antes a HTML con LibreOffice en lotes (corpus/md/_cache_doc/):
arrancar LibreOffice por archivo cuesta ~1 minuto. Los PDF escaneados pasan por
OCR (Tesseract spa) si está disponible; `--sin-ocr` lo desactiva.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

from . import jerarquia as jq
from .conversores import elegir
from .conversores.base import TABLA
from .conversores.doc import CACHE_ENV, soffice
from .markdown import a_markdown
from .metadatos import metadatos

ROOT = Path(__file__).resolve().parents[2]
TARGETS = ROOT / "data" / "corpus_targets.json"
LOTE_DOC = 40  # archivos .doc por arranque de LibreOffice


def es_sentencia(doc_id: str) -> bool:
    return doc_id.startswith("jurisprudencia_")


def sha_en_md(path: Path) -> list[str] | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        for linea in f:
            if linea.startswith("sha256_origen:"):
                return json.loads(linea.split(":", 1)[1])
            if linea.startswith("# "):
                return None
    return None


def convertir_doc(reg: dict, objetivo: dict | None, raw: Path, salida: Path, forzar: bool) -> dict:
    did = reg["doc_id"]
    destino = salida / f"{did}.md"
    entrada = {k: reg.get(k) for k in ("doc_id", "titulo", "fuente", "url", "fecha_consulta", "areas")}
    entrada["archivo"] = destino.name
    if not forzar and sha_en_md(destino) == reg.get("sha256"):
        return entrada | {"estado_conversion": "sin_cambios"}

    archivos = [raw / a for a in reg["archivos"]]
    try:
        conversor = elegir(archivos)
        res = conversor.convertir(archivos, es_sentencia(did))
    except Exception as e:  # noqa: BLE001 - se registra y se sigue con el resto
        return entrada | {"estado_conversion": "falla", "error": f"{type(e).__name__}: {e}",
                          "traza": traceback.format_exc(limit=3)}
    if res.requiere_ocr:
        return entrada | {"estado_conversion": "requiere_ocr", "advertencias": res.advertencias}

    cuenta = collections.Counter(b.tipo for b in res.bloques)
    advertencias = list(res.advertencias)
    if not es_sentencia(did) and not cuenta[jq.ARTICULO]:
        advertencias.append("no se detectaron artículos")
    if es_sentencia(did) and not cuenta[jq.SECCION_SENTENCIA]:
        advertencias.append("no se detectaron secciones de sentencia")
    juridicos = metadatos(did, reg, objetivo)
    meta = {
        "doc_id": did, "titulo": reg.get("titulo"), "fuente": reg.get("fuente"), "url": reg.get("url"),
        "fecha_consulta": reg.get("fecha_consulta"), "areas": reg.get("areas"),
        "tipo_documento": "sentencia" if es_sentencia(did) else "norma",
        **juridicos,
        "prioridad": reg.get("prioridad"),
        "formato_origen": archivos[0].suffix.lstrip(".").lower(), "archivos_origen": reg["archivos"],
        "sha256_origen": reg.get("sha256"), "conversor": conversor.nombre,
        "ocr": bool(res.stats.get("paginas_ocr")),
        "fecha_conversion": dt.date.today().isoformat(),
        "n_articulos": cuenta[jq.ARTICULO], "n_articulos_fuente": res.stats.get("articulos_fuente"),
        "n_secciones": cuenta[jq.SECCION_SENTENCIA], "n_tablas": cuenta[TABLA],
    }
    salida.mkdir(parents=True, exist_ok=True)
    destino.write_text(a_markdown(meta, reg.get("titulo") or did, res.bloques), encoding="utf-8")
    return entrada | {
        "estado_conversion": "ok", "conversor": conversor.nombre, "formato_origen": meta["formato_origen"],
        **{k: juridicos.get(k) for k in ("tipo_norma", "numero", "anio", "organo_emisor", "vigencia")},
        "ocr": meta["ocr"], "n_articulos": cuenta[jq.ARTICULO], "n_secciones": cuenta[jq.SECCION_SENTENCIA],
        "n_tablas": cuenta[TABLA], "encabezados": {t: cuenta[t] for t in jq.ENCABEZADOS if cuenta[t]},
        "stats": res.stats, "advertencias": advertencias,
    }


def preparar_doc(docs: list[dict], raw: Path, cache: Path, hilos: int):
    """Pasa a HTML, en lotes y en paralelo, los .doc que aún no están en la caché."""
    pendientes = [raw / a for r in docs for a in r["archivos"]
                  if a.lower().endswith(".doc") and not (cache / f"{Path(a).stem}.html").exists()]
    if not pendientes:
        return
    exe = soffice()
    cache.mkdir(parents=True, exist_ok=True)
    lotes = [pendientes[i:i + LOTE_DOC] for i in range(0, len(pendientes), LOTE_DOC)]
    print(f"== .doc -> HTML con LibreOffice: {len(pendientes)} archivos en {len(lotes)} lotes", flush=True)

    def lote(archivos: list[Path]):
        with tempfile.TemporaryDirectory() as perfil:  # un perfil por proceso: si no, no corren a la vez
            subprocess.run([exe, f"-env:UserInstallation={Path(perfil).resolve().as_uri()}", "--headless",
                            "--convert-to", "html:HTML (StarWriter):UTF8", "--outdir", str(cache),
                            *map(str, archivos)], capture_output=True, timeout=3600)
        return len(archivos)

    with cf.ThreadPoolExecutor(max(1, min(hilos // 2, 6))) as ex:
        hechos = 0
        for n in ex.map(lote, lotes):
            hechos += n
            print(f"   .doc {hechos}/{len(pendientes)}", flush=True)


def guardar_manifest(path: Path, previo: dict):
    datos = sorted(previo.values(), key=lambda e: e["doc_id"])
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


# ------------------------------------------------------------- segundo plano

def _control(salida: Path) -> dict[str, Path]:
    d = salida / "_control"
    return {"dir": d, "parar": d / "PARAR", "pid": d / "pid.json", "log": d / "log.txt"}


def _vivo(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes  # en Windows os.kill mataría el proceso
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, pid)
    if not h:
        return False
    codigo = ctypes.c_ulong()
    k.GetExitCodeProcess(h, ctypes.byref(codigo))
    k.CloseHandle(h)
    return codigo.value == 259


def fondo(args, argv: list[str]):
    """Relanza esta misma orden desacoplada de la terminal, con salida a _control/log.txt."""
    c = _control(args.salida)
    c["dir"].mkdir(parents=True, exist_ok=True)
    c["parar"].unlink(missing_ok=True)
    if _vivo(json.loads(c["pid"].read_text()).get("pid") if c["pid"].exists() else None):
        print("Ya hay una conversión corriendo: python -m src.ingest.convertir --estado")
        return
    resto = [a for a in argv if a != "--fondo"] + ["--log", str(c["log"])]
    with open(c["log"], "a", encoding="utf-8") as log:
        log.write(f"\n##### {dt.datetime.now():%Y-%m-%d %H:%M} inicio: {' '.join(resto)}\n")
    if os.name == "nt":
        # Por WMI el proceso no cuelga del árbol de quien lo lanza (una terminal o una sesión de
        # Claude): si esa sesión termina, la conversión sigue. pythonw: sin ventana.
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        exe = pythonw if pythonw.exists() else Path(sys.executable)
        linea = subprocess.list2cmdline([str(exe), "-m", "src.ingest.convertir", *resto])
        ps = ("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
              f"@{{CommandLine='{linea}'; CurrentDirectory='{ROOT}'}}; $r.ReturnValue; $r.ProcessId")
        codigo, *pid = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                                      capture_output=True, text=True).stdout.split()
        if codigo != "0" or not pid:
            print(f"No se pudo lanzar en segundo plano (WMI devolvió {codigo})")
            return
        pid = int(pid[0])
    else:
        pid = subprocess.Popen([sys.executable, "-m", "src.ingest.convertir", *resto], cwd=ROOT,
                               start_new_session=True, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).pid
    c["pid"].write_text(json.dumps({"pid": pid, "inicio": dt.datetime.now().isoformat()}))
    print(f"Conversión en segundo plano (pid {pid}). Log: {c['log']}")


def estado(args):
    c = _control(args.salida)
    info = json.loads(c["pid"].read_text()) if c["pid"].exists() else {}
    corre = _vivo(info.get("pid"))
    total = sum(1 for r in json.loads((args.raw / "corpus_manifest.json").read_text(encoding="utf-8"))
                if r.get("estado") == "ok")
    hechos = sum(1 for _ in args.salida.glob("*.md"))
    print(f"{'CORRIENDO' if corre else 'detenida'}  {hechos}/{total} .md ({100 * hechos / max(total, 1):.1f} %)"
          f"{'  [PARAR pedido]' if c['parar'].exists() else ''}")
    if c["log"].exists():
        ultimas = c["log"].read_text(encoding="utf-8", errors="replace").splitlines()[-3:]
        print("\n".join("  " + ln[:150] for ln in ultimas))


def parar(args):
    c = _control(args.salida)
    c["dir"].mkdir(parents=True, exist_ok=True)
    c["parar"].touch()
    info = json.loads(c["pid"].read_text()) if c["pid"].exists() else {}
    print("Parada limpia pedida: termina los documentos en curso y guarda (1-3 min)...")
    fin = time.time() + 600
    while _vivo(info.get("pid")) and time.time() < fin:
        time.sleep(5)
    print("Detenida. Relanza con: python -m src.ingest.convertir --fondo" if not _vivo(info.get("pid"))
          else "Sigue viva; espera un poco más o ciérrala desde el Administrador de tareas.")


# ------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=ROOT / "corpus" / "raw")
    ap.add_argument("--salida", type=Path, default=ROOT / "corpus" / "md")
    ap.add_argument("--solo", nargs="+", help="doc_id a convertir")
    ap.add_argument("--forzar", action="store_true", help="reconvierte aunque el origen no haya cambiado")
    ap.add_argument("--hilos", type=int, default=max(2, (os.cpu_count() or 4) - 2), help="procesos en paralelo")
    ap.add_argument("--sin-ocr", action="store_true", help="no pasa por OCR los PDF escaneados")
    ap.add_argument("--fondo", action="store_true", help="corre en segundo plano, desacoplado de la terminal")
    ap.add_argument("--estado", action="store_true", help="avance de la corrida en segundo plano")
    ap.add_argument("--parar", action="store_true", help="parada limpia de la corrida en segundo plano")
    ap.add_argument("--log", type=Path, help=argparse.SUPPRESS)  # lo usa --fondo
    args = ap.parse_args()
    if args.log:  # en segundo plano no hay consola: la salida va al log
        sys.stdout = sys.stderr = open(args.log, "a", encoding="utf-8", buffering=1)
    if args.fondo:
        return fondo(args, sys.argv[1:])
    if args.estado:
        return estado(args)
    if args.parar:
        return parar(args)
    if args.sin_ocr:
        os.environ["INGEST_SIN_OCR"] = "1"

    registros = json.loads((args.raw / "corpus_manifest.json").read_text(encoding="utf-8"))
    docs = [r for r in registros if r.get("estado") == "ok" and (not args.solo or r["doc_id"] in args.solo)]
    objetivos = {d["doc_id"]: d for d in json.loads(TARGETS.read_text(encoding="utf-8"))["documentos"]} \
        if TARGETS.exists() else {}
    manifest_path = args.salida / "corpus_manifest.json"
    previo = {}
    if manifest_path.exists():
        previo = {e["doc_id"]: e for e in json.loads(manifest_path.read_text(encoding="utf-8"))}
    parada = _control(args.salida)["parar"]
    args.salida.mkdir(parents=True, exist_ok=True)

    cache = args.salida / "_cache_doc"
    os.environ[CACHE_ENV] = str(cache)  # los procesos hijos lo heredan
    preparar_doc(docs, args.raw, cache, args.hilos)

    print(f"== {len(docs)} documentos de {args.raw} con {args.hilos} procesos", flush=True)
    ultimo = time.time()
    with cf.ProcessPoolExecutor(args.hilos) as ex:
        # Un .md que no está en el manifest (corrida cortada a la fuerza) se reconvierte para
        # recuperar su registro completo.
        futuros = [ex.submit(convertir_doc, r, objetivos.get(r["doc_id"]), args.raw, args.salida,
                             args.forzar or r["doc_id"] not in previo or
                             previo[r["doc_id"]].get("estado_conversion") == "sin_cambios")
                   for r in docs]
        def registrar(e: dict) -> dict:
            if e["estado_conversion"] == "sin_cambios" and e["doc_id"] in previo:
                e = previo[e["doc_id"]]
            previo[e["doc_id"]] = e
            return e

        for i, fut in enumerate(cf.as_completed(futuros), 1):
            e = registrar(fut.result())
            if parada.exists():
                ex.shutdown(wait=True, cancel_futures=True)  # termina los que están en curso
                for f in futuros:
                    if f.done() and not f.cancelled() and f is not fut:
                        registrar(f.result())
                print("== parada pedida: se guardó lo convertido", flush=True)
                break
            marca = {"ok": "OK ", "sin_cambios": "== ", "requiere_ocr": "OCR"}.get(e["estado_conversion"], "XX ")
            if marca != "== ":
                detalle = e.get("error") or "; ".join(e.get("advertencias", [])) or \
                    f"{e.get('n_articulos', 0)} artículos, {e.get('n_secciones', 0)} secciones"
                print(marca, e["doc_id"].ljust(36), detalle, flush=True)
            if i % 200 == 0 or time.time() - ultimo > 120:  # checkpoint
                guardar_manifest(manifest_path, previo)
                ultimo = time.time()
                print(f"== {i}/{len(docs)}", flush=True)

    guardar_manifest(manifest_path, previo)
    print(dict(collections.Counter(e["estado_conversion"] for e in previo.values())), "->", manifest_path)


if __name__ == "__main__":
    main()
