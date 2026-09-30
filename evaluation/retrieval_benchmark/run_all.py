"""Orquesta el banco de pruebas de recuperación: chunks -> BM25 -> HNSW -> evaluación -> comparación.

Reanudable: cada etapa persiste su salida (corpus/chunks, corpus/indices/<brazo>,
results/eval_<brazo>.json) y se salta si ya existe; --force la rehace. Pensado para el
servidor con GPU (A40); el portátil solo recibe los índices del ganador.

    # 1. Banco de pruebas sobre el subcorpus (normas + fichas de sentencias)
    python -m evaluation.retrieval_benchmark.run_all --seleccion normas_fichas --device cuda:0
    # 2. El ganador sobre el corpus completo
    python -m evaluation.retrieval_benchmark.run_all --seleccion todo --embedders bge-m3 \\
        --rerankers bge-reranker-v2-m3 --bm25 con --device cuda:0

Etapas sueltas: --stages chunks,bm25  |  --stages index  |  --stages evaluate,compare
"""
from __future__ import annotations

import argparse
import os

from evaluation.retrieval_benchmark import compare as compare_mod
from evaluation.retrieval_benchmark import evaluate as eval_mod
from evaluation.retrieval_benchmark import index_variants as idx_mod
from evaluation.retrieval_benchmark.config import (BM25_BANCO, EMBEDDERS_BANCO, K, RERANKERS_BANCO, RESULTS_ROOT,
                                                   dir_bm25, dir_denso, nombre_brazo)
from src.knowledge.hybrid_search import Config


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--stages", default="chunks,bm25,index,evaluate,compare")
    p.add_argument("--seleccion", default="normas_fichas", choices=["normas_fichas", "todo"])
    p.add_argument("--embedders", default=",".join(EMBEDDERS_BANCO))
    p.add_argument("--rerankers", default=",".join(r or "ninguno" for r in RERANKERS_BANCO),
                   help="separados por coma; 'ninguno' = sin reranker")
    p.add_argument("--bm25", default="con,sin", help="con,sin = BM25 con y sin raíces")
    p.add_argument("--device", default=None, help="cuda, cuda:2, cpu")
    p.add_argument("--lote-gpu", type=int, default=128)
    p.add_argument("--procesos", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--candidatos", type=int, default=100)
    p.add_argument("--n-rerank", type=int, default=50)
    p.add_argument("--force", action="store_true")
    return p


def main():
    args = build_parser().parse_args()
    stages = set(args.stages.split(","))
    embedders = [e for e in args.embedders.split(",") if e]
    rerankers = [None if r == "ninguno" else r for r in args.rerankers.split(",") if r]
    raices = [{"con": True, "sin": False}[b] for b in args.bm25.split(",") if b]
    assert set(raices) <= set(BM25_BANCO)

    if "chunks" in stages:
        idx_mod.chunks(args.procesos, args.force)
    if "bm25" in stages:
        for r in raices:
            idx_mod.bm25(args.seleccion, r, args.force)
    if "index" in stages:
        for e in embedders:
            idx_mod.denso(e, args.seleccion, args.device, args.lote_gpu, args.force)
    if "evaluate" in stages:
        cfg = Config(candidatos=args.candidatos, n_rerank=args.n_rerank, k=K)
        for e in embedders:
            for r in raices:
                for rr in rerankers:
                    nombre = nombre_brazo(e, r, rr, args.seleccion)
                    if (RESULTS_ROOT / f"eval_{nombre}.json").exists() and not args.force:
                        print(f"[evaluate] ya existe {nombre}")
                        continue
                    print(f"[evaluate] {nombre}", flush=True)
                    eval_mod.correr(nombre, dir_bm25(args.seleccion, r), dir_denso(e, args.seleccion), rr, cfg,
                                    args.device)
    if "compare" in stages:
        _comparar()


def _comparar():
    res = compare_mod.cargar()
    md = compare_mod.tabla(res) if res else "sin resultados"
    (RESULTS_ROOT / "comparacion.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
