"""Evalúa un brazo del banco de pruebas sobre las 50 preguntas de muestra.

Mide, por etapa (bm25, denso, rrf, rerank, final), qué queda entre los primeros k:
- recall_citas@k: normas del legal_basis (a nivel de cuerpo, como el evaluador
  oficial) citadas en el texto de los k pasajes. Base del componente de "calidad de
  citación": una norma correcta fuera de los pasajes vale la mitad.
- recall_docs@k, MRR y nDCG@k sobre los documentos del legal_basis.
- cobertura: documentos del legal_basis que existen en el índice (techo del recall).
- tiempos por etapa (media y p95), para dimensionar el portátil.

La muestra solo se usa para medir: nunca se indexa (descalifica).

  python -m evaluation.retrieval_benchmark.evaluate --bm25 corpus/indices/bm25_todo \\
      --denso corpus/indices/bge-m3_todo --reranker bge-reranker-v2-m3 --device cuda
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import statistics
from pathlib import Path

from evaluation.retrieval_benchmark.config import K, MUESTRA, RESULTS_ROOT
from evaluation.retrieval_benchmark.metrics import media, ndcg_at_k, recall, reciprocal_rank
from src.knowledge.citation_lookup import cuerpos, documentos_citados
from src.knowledge.hybrid_search import Config, Recuperador, consulta_de

ETAPAS = ["bm25", "denso", "rrf", "rerank", "final"]


def evaluar(rec: Recuperador, items: list[dict], k: int = K) -> dict:
    filas, tiempos = [], collections.defaultdict(list)
    ids_indice, n_chunks = set(), {}
    for nombre, idx in (("bm25", rec.bm25), ("denso", rec.denso)):
        if idx:
            ids_indice |= {c.split("/", 1)[0] for c in idx.ids}
            n_chunks[nombre] = len(idx.ids)
    for it in items:
        oro_cuerpos = cuerpos(it.get("legal_basis", ""))
        oro_docs = set(documentos_citados(it.get("legal_basis", "")))
        r = rec.buscar(consulta_de(it))
        for etapa, v in r.tiempos.items():
            tiempos[etapa].append(v)
        fila = {"id": it["id"], "formato": it["formato"], "area": it.get("area"),
                "legal_basis": it.get("legal_basis"), "n_oro": len(oro_cuerpos),
                "cobertura": recall(oro_docs, ids_indice), "etapas": {}}
        textos = rec.almacen.get(sorted({c for lista in r.etapas.values() for c in lista[:k]}))
        for etapa, lista in r.etapas.items():
            top = lista[:k]
            if etapa == "final":
                txt = " ".join(p["texto"] for p in r.pasajes)
            else:
                txt = " ".join(textos[c]["texto"] for c in top if c in textos)
            docs = [c.split("/", 1)[0] for c in top]
            fila["etapas"][etapa] = {
                "recall_citas": recall(oro_cuerpos, cuerpos(txt)),
                "recall_docs": recall(oro_docs, set(docs)),
                "rr": reciprocal_rank(docs, oro_docs),
                "ndcg": ndcg_at_k(docs, oro_docs, k) if oro_docs else None,
                "top": top}
        filas.append(fila)

    metricas = ("recall_citas", "recall_docs", "rr", "ndcg")
    etapas = [e for e in ETAPAS if any(e in f["etapas"] for f in filas)]
    return {
        "k": k, "n": len(filas), "n_chunks": n_chunks, "cobertura": media(f["cobertura"] for f in filas),
        "por_etapa": {e: {m: media(f["etapas"][e][m] for f in filas if e in f["etapas"]) for m in metricas}
                      for e in etapas},
        "final_por_formato": {fmt: {m: media(f["etapas"]["final"][m] for f in filas if f["formato"] == fmt)
                                    for m in ("recall_citas", "recall_docs")}
                              for fmt in sorted({f["formato"] for f in filas})},
        "tiempos_s": {e: {"media": round(statistics.mean(v), 3),
                          "p95": round(sorted(v)[int(0.95 * (len(v) - 1))], 3)} for e, v in tiempos.items()},
        "preguntas": filas,
    }


def tabla(res: dict, nombre: str) -> str:
    lin = [f"## {nombre}", "", f"k={res['k']}, n={res['n']}, chunks en el índice {res['n_chunks']}, "
           f"cobertura {res['cobertura']}", "",
           "| Etapa | recall_citas@k | recall_docs@k | MRR | nDCG@k |", "|---|---|---|---|---|"]
    for e, m in res["por_etapa"].items():
        lin.append(f"| {e} | {m['recall_citas']} | {m['recall_docs']} | {m['rr']} | {m['ndcg']} |")
    lin += ["", "| Formato (final) | recall_citas@k | recall_docs@k |", "|---|---|---|"]
    lin += [f"| {f} | {m['recall_citas']} | {m['recall_docs']} |" for f, m in res["final_por_formato"].items()]
    lin += ["", "| Tiempo (s) | media | p95 |", "|---|---|---|"]
    lin += [f"| {e} | {v['media']} | {v['p95']} |" for e, v in res["tiempos_s"].items()]
    return "\n".join(lin)


def correr(nombre: str, bm25: Path | None, denso: Path | None, reranker: str | None, cfg: Config,
           dispositivo: str | None = None, salida: Path = RESULTS_ROOT) -> dict:
    rec = Recuperador(bm25, denso, reranker, cfg, dispositivo=dispositivo)
    items = [json.loads(l) for l in MUESTRA.read_text(encoding="utf-8").splitlines() if l.strip()]
    res = evaluar(rec, items, cfg.k)
    res["config"] = {"nombre": nombre, "bm25": str(bm25), "denso": str(denso), "reranker": reranker,
                     **vars(cfg), "device": dispositivo, "fecha": dt.datetime.now().isoformat(timespec="seconds")}
    salida.mkdir(parents=True, exist_ok=True)
    (salida / f"eval_{nombre}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    md = tabla(res, nombre)
    (salida / f"eval_{nombre}.md").write_text(md + "\n", encoding="utf-8")
    print(md, flush=True)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bm25", type=Path)
    ap.add_argument("--denso", type=Path)
    ap.add_argument("--reranker", default="bge-reranker-v2-m3")
    ap.add_argument("--sin-reranker", action="store_true")
    ap.add_argument("--k", type=int, default=K)
    ap.add_argument("--candidatos", type=int, default=100)
    ap.add_argument("--n-rerank", type=int, default=50)
    ap.add_argument("--device", help="cuda, cuda:2, cpu")
    ap.add_argument("--nombre")
    args = ap.parse_args()
    if not (args.bm25 or args.denso):
        ap.error("hace falta --bm25 y/o --denso")
    reranker = None if args.sin_reranker else args.reranker
    nombre = args.nombre or "__".join([*(p.name for p in (args.bm25, args.denso) if p), reranker or "sin_reranker"])
    correr(nombre, args.bm25, args.denso, reranker,
           Config(candidatos=args.candidatos, n_rerank=args.n_rerank, k=args.k), args.device)


if __name__ == "__main__":
    main()
