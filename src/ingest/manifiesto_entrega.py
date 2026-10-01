"""corpus_manifest.json del entregable, con el formato del ejemplo oficial (docs_reto/entregables).

Une el manifiesto de DESCARGA (fuente, URL, fecha de consulta, áreas y sha256 de cada documento)
con los conteos del corpus indexado (chunks.sqlite): artículos y fragmentos por documento. Solo
entran los documentos descargados con éxito; todo doc_id que aparezca en submissions.jsonl
(pasajes_recuperados) existe aquí.

    python -m src.ingest.manifiesto_entrega --equipo "Samu Enjoyer" --enlace https://...
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESCARGA = (ROOT / "corpus" / "corpus_manifest.json", ROOT.parent / "Samu-Enjoyer-archivo" / "raw" / "corpus_manifest.json")
CHUNKS = ROOT / "corpus" / "chunks" / "chunks.sqlite"

LECTOR = {".html": "HTML (BeautifulSoup, plantilla por fuente)", ".htm": "HTML (BeautifulSoup, plantilla por fuente)",
          ".pdf": "PDF (PyMuPDF)", ".doc": "DOC (LibreOffice a DOCX, python-docx)", ".docx": "DOCX (python-docx)"}
SEGMENTACION = {
    "norma": "segmentación por artículo con ruta jerárquica (artículos largos en partes; notas, preámbulo y anexos aparte)",
    "sentencia": "ficha (descriptores, tesis y parte resolutiva) + ventanas de ~1.700 caracteres por sección",
}


def conteos(ruta: Path) -> dict[str, dict]:
    """doc_id -> fragmentos, artículos, tipo de documento y si hubo OCR."""
    db = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    q = """SELECT doc_id, COUNT(*),
                  COUNT(DISTINCT CASE WHEN tipo_chunk IN ('articulo', 'parte_articulo') THEN articulo_id END),
                  MAX(json_extract(datos, '$.tipo_documento')), MAX(json_extract(datos, '$.ocr')),
                  MAX(json_extract(datos, '$.nombre_citable'))
           FROM chunks GROUP BY doc_id"""
    return {d: {"n_fragmentos": n, "n_articulos": a, "tipo": t, "ocr": bool(o), "nombre": nom}
            for d, n, a, t, o, nom in db.execute(q)}


def metodo(archivos: list[str], tipo: str | None, ocr: bool) -> str:
    ext = Path(archivos[0]).suffix.lower() if archivos else ""
    lector = LECTOR.get(ext, "texto")
    if ocr:
        lector += " + OCR Tesseract (spa) en las capas de texto ilegibles"
    seg = SEGMENTACION["sentencia" if tipo == "sentencia" else "norma"]
    return f"{lector} -> Markdown con metadatos; {seg}"


def construir(descarga: list[dict], c: dict[str, dict], equipo: str, enlace: str) -> dict:
    documentos = []
    for r in sorted((r for r in descarga if r.get("estado") == "ok" and r["doc_id"] in c), key=lambda r: r["doc_id"]):
        k = c[r["doc_id"]]
        sha = r.get("sha256") or []
        documentos.append({
            "doc_id": r["doc_id"],
            "titulo": k["nombre"] or r.get("titulo"),  # el nombre citable del encabezado de los pasajes
            "fuente": r.get("fuente"),
            "url": r.get("url"),
            "fecha_consulta": r.get("fecha_consulta"),
            "areas": r.get("areas") or [],
            "n_articulos": k["n_articulos"] or None,
            "n_fragmentos": k["n_fragmentos"],
            "metodo_ingesta": metodo(r.get("archivos") or [], k["tipo"], k["ocr"]),
            "sha256": sha[0] if len(sha) == 1 else sha,
        })
    return {
        "equipo": equipo,
        "licencia": "CC-BY-4.0",
        "fecha_generacion": dt.date.today().isoformat(),
        "enlace_nube": enlace,
        "encoder": "Qwen/Qwen3-Embedding-0.6B",
        "dimension": 1024,
        "indice": "faiss.IndexHNSWSQ (8 bits, M=32, efConstruction=200, efSearch=256) + BM25 (bm25s, raíces Snowball)",
        "reranker": "BAAI/bge-reranker-v2-m3",
        "n_documentos": len(documentos),
        "n_fragmentos": sum(d["n_fragmentos"] for d in documentos),
        "documentos": documentos,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--descarga", type=Path, help="manifiesto de descarga (por defecto corpus/ o ../Samu-Enjoyer-archivo/raw/)")
    ap.add_argument("--chunks", type=Path, default=CHUNKS)
    ap.add_argument("--equipo", required=True)
    ap.add_argument("--enlace", default="", help="enlace de descarga del zip del corpus e índice")
    ap.add_argument("--salida", type=Path, default=ROOT / "corpus_manifest.json")
    args = ap.parse_args()
    ruta = args.descarga or next((p for p in DESCARGA if p.is_file()), None)
    if ruta is None:
        raise SystemExit("No se encontró el manifiesto de descarga; pásalo con --descarga")
    descarga = json.loads(ruta.read_text(encoding="utf-8"))
    c = conteos(args.chunks)
    m = construir(descarga, c, args.equipo, args.enlace)
    faltan = sorted(set(c) - {d["doc_id"] for d in m["documentos"]})
    if faltan:  # todo doc_id indexado debe estar en el manifiesto (lo exige el esquema de la entrega)
        raise SystemExit(f"{len(faltan)} doc_id del índice no están en el manifiesto de descarga: {faltan[:10]}")
    args.salida.write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{args.salida}: {m['n_documentos']} documentos, {m['n_fragmentos']} fragmentos"
          f"{'' if args.enlace else ' (falta --enlace del zip)'}")


if __name__ == "__main__":
    main()
