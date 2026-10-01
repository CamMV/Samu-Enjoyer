"""Verifica que los índices copiados (p. ej. al portátil) estén completos y concuerden.

  python -m src.knowledge.verify_indices
  python -m src.knowledge.verify_indices --sin-faiss     # sin cargar los HNSW (más rápido)

Comprueba: archivos presentes; chunks.sqlite, BM25 y HNSW de "todo" con los mismos ids;
los índices de "normas" iguales entre sí, contenidos en "todo" y sin sentencias; una
muestra de ids presente en chunks.sqlite; una búsqueda BM25 de prueba; y los resultados
del banco de pruebas que van al informe. No usa GPU ni torch.
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3

from .chunk_store import CHUNKS, INDICES, ROOT

RESULTADOS = ROOT / "evaluation" / "retrieval_benchmark" / "results"
GANADOR = "eval_todo__qwen3-emb-0.6b__bm25__bge-reranker-v2-m3__ganador_normas50"
DENSO = "qwen3-emb-0.6b"

fallos: list[str] = []


def check(ok: bool, msg: str):
    print(("  OK   " if ok else "  FALLA ") + msg)
    if not ok:
        fallos.append(msg)


def ids_de(d):
    return json.loads((d / "ids.json").read_text(encoding="utf-8"))


def info_de(d):
    return json.loads((d / "info.json").read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sin-faiss", action="store_true")
    args = ap.parse_args()

    print("== Archivos")
    dirs = {s: (INDICES / f"bm25_{s}", INDICES / f"{DENSO}_{s}") for s in ("todo", "normas")}
    requeridos = [CHUNKS / "chunks.sqlite", CHUNKS / "resumen.json", ROOT / "logs" / "diagnostico_fallos.log",
                  RESULTADOS / "comparacion.md", RESULTADOS / "comparacion_banco_normas_fichas.md",
                  RESULTADOS / f"{GANADOR}.json", RESULTADOS / f"{GANADOR}.md"]
    for b, d in dirs.values():
        requeridos += [b / "ids.json", b / "info.json", b / "params.index.json",
                       d / "ids.json", d / "info.json", d / "hnsw.faiss"]
    for p in requeridos:
        check(p.exists() and p.stat().st_size > 0,
              f"{p.relative_to(ROOT)} ({p.stat().st_size / 1e6:,.0f} MB)" if p.exists() else f"{p.relative_to(ROOT)} no está")
    if fallos:
        print(f"\nFaltan archivos ({len(fallos)}); el resto de la verificación no tiene sentido.")
        raise SystemExit(1)

    print("== Conteos e ids")
    db = sqlite3.connect(f"file:{CHUNKS / 'chunks.sqlite'}?mode=ro", uri=True)
    n_sql = db.execute("select count(*) from chunks").fetchone()[0]
    ids = {}
    for s, (b, d) in dirs.items():
        ib, idn = ids_de(b), ids_de(d)
        nb, nd = info_de(b)["n"], info_de(d)["n"]
        check(len(ib) == nb == len(idn) == nd, f"{s}: BM25 {len(ib)}/{nb}, HNSW {len(idn)}/{nd}")
        check(ib == idn, f"{s}: BM25 y HNSW con los mismos ids en el mismo orden")
        check(len(set(ib)) == len(ib), f"{s}: ids únicos")
        ids[s] = ib
    check(len(ids["todo"]) == n_sql, f"todo ({len(ids['todo'])}) = chunks.sqlite ({n_sql})")
    todo = set(ids["todo"])
    check(set(ids["normas"]) <= todo, f"normas ({len(ids['normas'])}) contenidas en todo")
    check(not any(c.startswith("jurisprudencia_") for c in ids["normas"]), "normas sin sentencias")
    check(info_de(dirs["normas"][1]).get("modelo") == info_de(dirs["todo"][1]).get("modelo") == DENSO,
          f"los dos HNSW son de {DENSO}")
    muestra = random.Random(0).sample(ids["todo"], 2000)
    q = f"select count(*) from chunks where chunk_id in ({','.join('?' * len(muestra))})"
    check(db.execute(q, muestra).fetchone()[0] == len(muestra), "muestra de 2000 ids presente en chunks.sqlite")

    if not args.sin_faiss:
        print("== HNSW (carga completa)")
        import faiss
        for s, (_, d) in dirs.items():
            idx = faiss.read_index(str(d / "hnsw.faiss"))
            check(idx.ntotal == len(ids[s]) and idx.d == info_de(d)["dim"],
                  f"{s}: hnsw.faiss con {idx.ntotal} vectores de dim {idx.d}")

    print("== BM25 (búsqueda de prueba)")
    from .bm25_store import IndiceBM25
    for s, (b, _) in dirs.items():
        top = [c for c, _ in IndiceBM25(b).buscar("artículo 42 Código General del Proceso deberes del juez", 50)]
        check(any(c.startswith("codigo_general_proceso/") for c in top), f"{s}: el CGP sale en los 50 primeros")

    print("== Resultados para el informe")
    res = json.loads((RESULTADOS / f"{GANADOR}.json").read_text(encoding="utf-8"))
    final = res["por_etapa"]["final"]
    check(res["n"] == 50 and res["n_chunks"].get("bm25") == len(ids["todo"]),
          f"ganador: {res['n']} preguntas sobre {res['n_chunks']}")
    check(round(final["recall_citas"], 3) == 0.919 and round(final["recall_docs"], 3) == 0.785,
          f"ganador: recall_citas {final['recall_citas']}, recall_docs {final['recall_docs']}")
    sobrantes = sorted(p.name for p in RESULTADOS.glob("eval_*ganador_d2*"))
    check(not sobrantes, "sin resultados descartados (ganador_d2*)" + (f": {sobrantes}" if sobrantes else ""))

    print(f"\n{'TODO CORRECTO' if not fallos else f'{len(fallos)} FALLAS'}")
    raise SystemExit(1 if fallos else 0)


if __name__ == "__main__":
    main()
