"""Audita corpus/raw contra data/corpus_targets.json: completitud, integridad y repetidos.

    python scraper/auditar_descarga.py            # reporte en pantalla y en corpus/descarga/auditoria.json
    python scraper/auditar_descarga.py --arreglar # además corrige lo que es seguro corregir (ver abajo)

Revisa, para cada documento de la lista maestra:
- estado en el manifest (ok, duplicado, falla o ausente) y que sus archivos existan;
- integridad por formato: PDF con firma y %%EOF (no truncado), .docx como zip válido,
  .doc con firma OLE, HTML que cierra </html>;
- normas de la plantilla del Senado: que cada artículo del selector "Artículo" aparezca
  como ancla en alguna de sus páginas y que no queden cajas <table id="TableN"> vacías;
- repetidos: el mismo contenido guardado con dos doc_id;
- sobrantes: carpetas o archivos en disco que el manifest no lista.

Con --arreglar: renombra .doc que en realidad son .docx (y al revés), borra archivos
sobrantes dentro de las carpetas de documentos y marca en el manifest como "falla" los
documentos con archivos dañados, para que `descargar.py iniciar` los vuelva a bajar.
"""
from __future__ import annotations

import argparse
import collections
import html
import json
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "corpus" / "raw"
TARGETS = ROOT / "data" / "corpus_targets.json"
SALIDA = ROOT / "corpus" / "descarga" / "auditoria.json"

OPCION = re.compile(r'<option value="[^"]*#([^"]+)"')
ANCLA = re.compile(r'name="([^"]+)"', re.I)  # artículos y encabezados (Título, Capítulo…)
CAJA_VACIA = re.compile(r'<table id="Table\d+"[^>]*>\s*</table>')


def formato_real(cabeza: bytes) -> str | None:
    if b"%PDF" in cabeza[:1024]:
        return "pdf"
    if cabeza[:4] == b"\xd0\xcf\x11\xe0":
        return "doc"
    if cabeza[:4] == b"PK\x03\x04":
        return "docx"
    return None


def problema_archivo(f: Path) -> str | None:
    """Motivo por el que un archivo parece dañado o incompleto, o None si está bien."""
    if not f.exists():
        return "no existe"
    datos = f.read_bytes()
    if len(datos) < 1024:
        return f"muy pequeño ({len(datos)} B)"
    ext = f.suffix.lower().lstrip(".")
    real = formato_real(datos[:1024])
    if ext == "pdf":
        if real != "pdf":
            return "no es un PDF"
        if b"%%EOF" not in datos[-4096:]:  # Función Pública genera PDF sin %%EOF: se prueba abrirlo
            try:
                import io
                import logging
                import pypdf
                logging.disable(logging.CRITICAL)
                if not pypdf.PdfReader(io.BytesIO(datos), strict=False).pages[-1].extract_text():
                    return "PDF truncado (última página vacía)"
            except ImportError:
                return "PDF sin %%EOF (instala pypdf para verificarlo)"
            except Exception as e:  # noqa: BLE001
                return f"PDF dañado ({type(e).__name__})"
    elif ext in ("doc", "docx"):
        if real not in ("doc", "docx"):
            return "no es un documento de Word"
        if real == "docx":
            try:
                with zipfile.ZipFile(f) as z:
                    if z.testzip() is not None:
                        return "docx dañado"
            except zipfile.BadZipFile:
                return "docx dañado"
    elif ext in ("html", "htm"):
        if real:
            return f"es un {real} guardado como {ext}"
        if b"</html>" not in datos[-4096:].lower():
            return "HTML truncado (sin </html>)"
    return None


def revisar_plantilla(archivos: list[Path]) -> dict | None:
    """Artículos del selector que no aparecen en ninguna página y cajas vacías."""
    textos = [a.read_bytes().decode("latin-1") for a in archivos if a.suffix in (".html", ".htm")]
    if not textos or 'name="listabookmarks"' not in textos[0]:
        return None
    # Las anclas vienen con entidades (T&Iacute;TULO) y el selector no: se comparan decodificadas.
    selector = dict.fromkeys(html.unescape(o).strip() for o in OPCION.findall(textos[0]))
    anclas = {html.unescape(a).strip() for t in textos for a in ANCLA.findall(t)}
    faltan = [a for a in selector if a not in anclas]
    vacias = sum(len(CAJA_VACIA.findall(t)) for t in textos)
    return {"articulos": len(selector), "faltan": faltan, "cajas_vacias": vacias}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arreglar", action="store_true")
    args = ap.parse_args()

    docs = json.loads(TARGETS.read_text(encoding="utf-8"))["documentos"]
    ruta_man = RAW / "corpus_manifest.json"
    manifest = json.loads(ruta_man.read_text(encoding="utf-8"))
    man = {r["doc_id"]: r for r in manifest}
    objetivo = {d["doc_id"]: d for d in docs}

    estados = collections.Counter()
    fallas, ausentes, danados, renombrar, plantilla_mal = [], [], [], [], []
    por_hash = collections.defaultdict(list)
    n_archivos, bytes_total = 0, 0

    for did, d in objetivo.items():
        r = man.get(did)
        if r is None:
            estados["ausente"] += 1
            ausentes.append({"doc_id": did, "fuente": d["fuente"], "url": d["donde_buscar"]})
            continue
        estados[r["estado"]] += 1
        if r["estado"] == "falla":
            fallas.append({"doc_id": did, "fuente": d["fuente"], "error": r.get("error", "")})
            continue
        if r["estado"] != "ok":
            continue
        rutas = [RAW / a for a in r.get("archivos", [])]
        malos = {}
        for f in rutas:
            if f.exists():
                n_archivos += 1
                bytes_total += f.stat().st_size
                real = formato_real(f.read_bytes()[:1024])
                if f.suffix in (".doc", ".docx") and real in ("doc", "docx") and f.suffix != f".{real}":
                    renombrar.append((did, f, real))
                    continue
            if (m := problema_archivo(f)):
                malos[f.name] = m
        if malos:
            danados.append({"doc_id": did, "fuente": d["fuente"], "problemas": malos})
        if (p := revisar_plantilla(rutas)) and (p["faltan"] or p["cajas_vacias"]):
            plantilla_mal.append({"doc_id": did, **p, "faltan": p["faltan"][:20], "n_faltan": len(p["faltan"])})
        if r.get("sha256"):
            por_hash[tuple(r["sha256"])].append(did)

    repetidos = [ids for ids in por_hash.values() if len(ids) > 1]
    marcados_dup = [{"doc_id": r["doc_id"], "duplicado_de": r.get("duplicado_de")}
                    for r in manifest if r["estado"] == "duplicado"]
    fuera_de_lista = [r["doc_id"] for r in manifest if r["doc_id"] not in objetivo]

    listados = {a for r in manifest if r["estado"] == "ok" for a in r.get("archivos", [])}
    carpetas_validas = {r["doc_id"] for r in manifest if r["estado"] == "ok"}
    sobrantes, carpetas_huerfanas = [], []
    for c in RAW.iterdir():
        if not c.is_dir():
            continue
        if c.name not in carpetas_validas:
            carpetas_huerfanas.append(c.name)
            continue
        sobrantes += [f.relative_to(RAW).as_posix() for f in c.iterdir()
                      if f.relative_to(RAW).as_posix() not in listados]

    if args.arreglar:
        for did, f, real in renombrar:
            nuevo = f.with_suffix(f".{real}")
            f.rename(nuevo)
            r = man[did]
            r["archivos"] = [nuevo.relative_to(RAW).as_posix() if a == f.relative_to(RAW).as_posix() else a
                             for a in r["archivos"]]
        for s in sobrantes:
            (RAW / s).unlink(missing_ok=True)
        for c in carpetas_huerfanas:  # restos de documentos que quedaron como falla o duplicado
            shutil.rmtree(RAW / c, ignore_errors=True)
        # Las normas con anclas faltantes solo se reportan: el Senado a veces escribe mal el ancla
        # (p. ej. "#9#9*") aunque el texto del artículo esté; volver a bajarlas no lo cambia.
        for x in danados:
            man[x["doc_id"]] |= {"estado": "falla", "error": "auditoría: archivo dañado o norma incompleta"}
        ruta_man.write_text(json.dumps(sorted(man.values(), key=lambda r: r["doc_id"]), ensure_ascii=False,
                                       indent=1), encoding="utf-8")

    reporte = {
        "documentos_lista": len(objetivo), "estados": dict(estados),
        "archivos": n_archivos, "gb": round(bytes_total / 1e9, 2),
        "fallas_por_fuente": dict(collections.Counter(f["fuente"].split(" - ")[0] for f in fallas)),
        "fallas_por_motivo": dict(collections.Counter(re.sub(r"[:(].*", "", f["error"]).strip()
                                                      for f in fallas)),
        "ausentes": ausentes, "fallas": fallas, "danados": danados,
        "plantilla_incompleta": plantilla_mal, "renombrados_doc_docx": len(renombrar),
        "repetidos_mismo_contenido": repetidos, "marcados_duplicado": marcados_dup,
        "en_manifest_fuera_de_lista": fuera_de_lista, "archivos_sobrantes": len(sobrantes),
        "carpetas_huerfanas": carpetas_huerfanas, "arreglado": args.arreglar,
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(reporte, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v if not isinstance(v, list) else len(v) for k, v in reporte.items()},
                     ensure_ascii=False, indent=1))
    print(f"Detalle: {SALIDA}")


if __name__ == "__main__":
    main()
