"""Variantes de recuperación para las cerradas: ¿llega el documento de referencia al top-10?"""
import dataclasses
import json
import sys
import time

from evaluation.retrieval_benchmark.config import MUESTRA, dir_bm25, dir_denso
from evaluation.retrieval_benchmark.evaluate import evaluar
from src.knowledge.hybrid_search import Config, Recuperador

solo = sys.argv[1] if len(sys.argv) > 1 else "cerradas"
items = [json.loads(l) for l in MUESTRA.read_text(encoding="utf-8").split("\n") if l.strip()]
if solo == "cerradas":
    items = [it for it in items if it["formato"] == "multiple_choice"]
rec = Recuperador(dir_bm25("todo"), dir_denso("qwen3-emb-0.6b", "todo"), "bge-reranker-v2-m3", Config(),
                  dispositivo="cuda", dispositivo_denso="cpu")
VARIANTES = {
    "base": {},
    "citadas5": {"en_citadas": 5},
    "opciones20": {"solo_opciones": 20},
    "rr_opc": {"rerank_opciones": True},
    "citadas5+opciones20": {"en_citadas": 5, "solo_opciones": 20},
    "todo": {"en_citadas": 5, "solo_opciones": 20, "rerank_opciones": True},
    "smlmv": {"smlmv": True},
    "citadas5+smlmv": {"en_citadas": 5, "smlmv": True},
    "ventana": {"una_ventana": True},
    "fusion10": {"peso_fusion": 0.1},
    "fusion20": {"peso_fusion": 0.2},
    "fusion30": {"peso_fusion": 0.3},
    "lideres1": {"lideres": 1},
}
pedidas = sys.argv[2].split(",") if len(sys.argv) > 2 else list(VARIANTES)
base_cfg = Config()
for nombre in pedidas:
    rec.cfg = dataclasses.replace(base_cfg, **VARIANTES[nombre])
    t0 = time.perf_counter()
    res = evaluar(rec, items)
    dt = (time.perf_counter() - t0) / len(items)
    m = res["por_etapa"]["final"]
    print(f"\n### {nombre}: recall_citas {m['recall_citas']} recall_docs {m['recall_docs']} "
          f"MRR {m['rr']} nDCG {m['ndcg']} ({dt:.1f} s/pregunta)", flush=True)
    for f in res["preguntas"]:
        fin = f["etapas"]["final"]
        if f["formato"] == "multiple_choice":
            fintech = ""
            if f["id"] == 128:
                rr = f["etapas"]["rerank"]["top"] if False else None
            docs = sorted({c.split("/", 1)[0] for c in fin["top"]})
            print(f"  {f['id']:>5} docs {fin['recall_docs']} citas {fin['recall_citas']}  "
                  f"{'fintech:' + str(any(c.startswith('decreto_1068_2025') for c in fin['top'])) if f['id'] == 128 else ''}"
                  f" {[d for d in docs if d.startswith(('codigo', 'constitucion', 'decreto_663', 'estatuto'))]}")
    json.dump(res, open(f"exp_{solo}_{nombre}.json", "w", encoding="utf-8"), ensure_ascii=False)
