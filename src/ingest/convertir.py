"""Convierte corpus/raw a Markdown: un .md por documento (doc_id) en corpus/md/.

Cada .md trae front matter YAML con la procedencia (fuente, url, fecha de
consulta, archivos y sha256 de origen) y el cuerpo con la jerarquía como
encabezados: # título del documento, luego Parte/Libro/Título/Capítulo/Sección
y "Artículo N." con niveles asignados según lo que tenga cada norma. Las
sentencias se dividen por secciones (antecedentes, consideraciones, decisión).
Texto tachado en la fuente (inexequible o derogado) queda como ~~…~~ y las cajas
del Senado (concordancias, notas de vigencia…) como citas "> **Rótulo:**".

Uso:
  python -m src.ingest.convertir                       # todo lo que está "ok" en el manifest
  python -m src.ingest.convertir --solo constitucion ley_1581_2012
  python -m src.ingest.convertir --forzar              # reconvierte aunque el origen no cambió

Se puede cortar y relanzar: un .md cuyo sha256 de origen coincide se salta.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import datetime as dt
import json
import re
import traceback
from pathlib import Path

from . import jerarquia as jq
from .conversores import elegir
from .markdown import a_markdown

ROOT = Path(__file__).resolve().parents[2]


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


def convertir_doc(reg: dict, raw: Path, salida: Path, forzar: bool) -> dict:
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
    meta = {
        "doc_id": did, "titulo": reg.get("titulo"), "fuente": reg.get("fuente"), "url": reg.get("url"),
        "fecha_consulta": reg.get("fecha_consulta"), "areas": reg.get("areas"),
        "tipo_documento": "sentencia" if es_sentencia(did) else "norma",
        "vigencia": reg.get("vigencia"), "prioridad": reg.get("prioridad"),
        "formato_origen": archivos[0].suffix.lstrip(".").lower(), "archivos_origen": reg["archivos"],
        "sha256_origen": reg.get("sha256"), "conversor": conversor.nombre,
        "fecha_conversion": dt.date.today().isoformat(),
        "n_articulos": cuenta[jq.ARTICULO], "n_articulos_fuente": res.stats.get("articulos_fuente"),
        "n_secciones": cuenta[jq.SECCION_SENTENCIA],
    }
    salida.mkdir(parents=True, exist_ok=True)
    destino.write_text(a_markdown(meta, reg.get("titulo") or did, res.bloques), encoding="utf-8")
    return entrada | {
        "estado_conversion": "ok", "conversor": conversor.nombre, "formato_origen": meta["formato_origen"],
        "n_articulos": cuenta[jq.ARTICULO], "n_secciones": cuenta[jq.SECCION_SENTENCIA],
        "encabezados": {t: cuenta[t] for t in jq.ENCABEZADOS if cuenta[t]},
        "stats": res.stats, "advertencias": advertencias,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=ROOT / "corpus" / "raw")
    ap.add_argument("--salida", type=Path, default=ROOT / "corpus" / "md")
    ap.add_argument("--solo", nargs="+", help="doc_id a convertir")
    ap.add_argument("--forzar", action="store_true", help="reconvierte aunque el origen no haya cambiado")
    ap.add_argument("--hilos", type=int, default=4, help="procesos en paralelo")
    ap.add_argument("--ocr", action="store_true", help="reservado: OCR para PDF escaneados (no implementado)")
    args = ap.parse_args()
    if args.ocr:
        from .ocr import motor
        motor("tesseract")  # lanza OCRNoDisponible hasta que se implemente

    registros = json.loads((args.raw / "corpus_manifest.json").read_text(encoding="utf-8"))
    docs = [r for r in registros if r.get("estado") == "ok" and (not args.solo or r["doc_id"] in args.solo)]
    manifest_path = args.salida / "corpus_manifest.json"
    previo = {}
    if manifest_path.exists():
        previo = {e["doc_id"]: e for e in json.loads(manifest_path.read_text(encoding="utf-8"))}

    print(f"== {len(docs)} documentos de {args.raw}", flush=True)
    with cf.ProcessPoolExecutor(args.hilos) as ex:
        futuros = [ex.submit(convertir_doc, r, args.raw, args.salida, args.forzar) for r in docs]
        for fut in cf.as_completed(futuros):
            e = fut.result()
            marca = {"ok": "OK ", "sin_cambios": "== ", "requiere_ocr": "OCR"}.get(e["estado_conversion"], "XX ")
            if e["estado_conversion"] == "sin_cambios" and e["doc_id"] in previo:
                e = previo[e["doc_id"]]
            previo[e["doc_id"]] = e
            detalle = e.get("error") or "; ".join(e.get("advertencias", [])) or \
                f"{e.get('n_articulos', 0)} artículos, {e.get('n_secciones', 0)} secciones"
            print(marca, e["doc_id"].ljust(36), detalle, flush=True)

    args.salida.mkdir(parents=True, exist_ok=True)
    datos = sorted(previo.values(), key=lambda e: e["doc_id"])
    manifest_path.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(dict(collections.Counter(e["estado_conversion"] for e in datos)), "->", manifest_path)


if __name__ == "__main__":
    main()
