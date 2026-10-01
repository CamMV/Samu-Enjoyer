"""Verificación en vivo: la recuperación de esta máquina contra la de la A40.

Corre las 50 preguntas con la configuración por defecto (el ganador) y compara, pregunta
por pregunta, los 10 pasajes finales con los de un eval_*.json hecho en la A40; además
reporta métricas y tiempos por etapa de esta máquina.

    python -m evaluation.retrieval_benchmark.compare_machines --device cuda
    python -m evaluation.retrieval_benchmark.compare_machines --device cuda --device-denso cpu   # 4 GB de GPU

El resultado queda en results/maquina_<nombre>.json (no pisa los de la A40).
"""
from __future__ import annotations

import argparse
import json
import platform
import time

from evaluation.retrieval_benchmark.config import K, MUESTRA, RESULTS_ROOT, dir_bm25, dir_denso
from evaluation.retrieval_benchmark.evaluate import evaluar
from src.knowledge.hybrid_search import Config, Recuperador

REFERENCIA = RESULTS_ROOT / "eval_todo__qwen3-emb-0.6b__bm25__bge-reranker-v2-m3__ganador_dedup70.json"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", default=None, help="reranker (y embedder si no se da --device-denso)")
    ap.add_argument("--device-denso", default=None, help="embedder de la consulta, p. ej. cpu")
    ap.add_argument("--referencia", default=str(REFERENCIA))
    ap.add_argument("--nombre", default=platform.node() or "local")
    args = ap.parse_args()

    ref = json.load(open(args.referencia, encoding="utf-8"))
    cfg = Config()
    for campo in ("candidatos", "n_rerank", "k", "max_por_doc", "max_sentencias", "normas", "penal_tipo",
                  "bonus_prioridad_alta"):
        if ref["config"].get(campo) != getattr(cfg, campo):
            print(f"AVISO: {campo} = {getattr(cfg, campo)} aquí y {ref['config'].get(campo)} en la referencia")

    t0 = time.perf_counter()
    rec = Recuperador(dir_bm25("todo"), dir_denso("qwen3-emb-0.6b", "todo"), "bge-reranker-v2-m3", cfg,
                      dispositivo=args.device, dispositivo_denso=args.device_denso)
    items = [json.loads(l) for l in MUESTRA.read_text(encoding="utf-8").split("\n") if l.strip()]
    rec.buscar(items[0]["pregunta"])  # calentamiento: carga de modelos fuera de la medición
    carga = time.perf_counter() - t0
    res = evaluar(rec, items, K)

    ref_top = {f["id"]: f["etapas"]["final"]["top"] for f in ref["preguntas"]}
    iguales, distintas = 0, []
    for f in res["preguntas"]:
        top = f["etapas"]["final"]["top"]
        if top == ref_top.get(f["id"]):
            iguales += 1
        else:
            otro = ref_top.get(f["id"]) or []
            distintas.append({"id": f["id"], "mismo_conjunto": set(top) == set(otro),
                              "comunes": len(set(top) & set(otro)), "aqui": top, "a40": otro})

    m, mr = res["por_etapa"]["final"], ref["por_etapa"]["final"]
    print(f"\n== {args.nombre}: carga {carga:.0f} s")
    print("| métrica | esta máquina | A40 |\n|---|---|---|")
    for k in ("recall_citas", "recall_docs", "rr", "ndcg"):
        print(f"| {k} | {m[k]} | {mr[k]} |")
    print("\n| etapa | media s | p95 s |\n|---|---|---|")
    total = 0.0
    for e, v in res["tiempos_s"].items():
        total += v["media"]
        print(f"| {e} | {v['media']} | {v['p95']} |")
    print(f"| **total** | **{total:.2f}** | |")
    print(f"\nPasajes finales idénticos a la A40 (mismo orden): {iguales}/{len(res['preguntas'])}")
    for d in distintas:
        print(f"   pregunta {d['id']}: {d['comunes']}/10 en común, mismo conjunto: {d['mismo_conjunto']}")

    res["comparacion"] = {"maquina": args.nombre, "device": args.device, "device_denso": args.device_denso,
                          "carga_s": round(carga, 1), "identicas": iguales, "distintas": distintas}
    salida = RESULTS_ROOT / f"maquina_{args.nombre}.json"
    salida.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n-> {salida}")


if __name__ == "__main__":
    main()
