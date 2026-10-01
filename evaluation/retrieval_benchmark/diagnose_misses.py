"""Dónde quedan los documentos del legal_basis que no llegan al top-10 final.

Para cada pregunta con recall_docs < 1 en un eval_*.json, busca el primer chunk de cada
documento faltante en BM25 y en el HNSW (hasta --profundidad) y muestra el top-10 final.
Si el documento ni aparece en los 1000 primeros, el problema es de chunking o de
consulta, no del orden.

    python -m evaluation.retrieval_benchmark.diagnose_misses \\
        --eval evaluation/retrieval_benchmark/results/eval_todo__..._completo_150_seccion.json \\
        --device cuda:0
"""
from __future__ import annotations

import argparse
import json

from evaluation.retrieval_benchmark.config import MUESTRA, dir_bm25, dir_denso
from src.knowledge.citation_lookup import documentos_citados
from src.knowledge.hybrid_search import Recuperador, consulta_de


def primero(lista: list[tuple[str, float]], doc: str) -> tuple[int | None, str | None]:
    for pos, (cid, _) in enumerate(lista, 1):
        if cid.split("/", 1)[0] == doc:
            return pos, cid
    return None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval", required=True)
    ap.add_argument("--embedder", default="qwen3-emb-0.6b")
    ap.add_argument("--seleccion", default="todo")
    ap.add_argument("--profundidad", type=int, default=1000)
    ap.add_argument("--device", default=None)
    args = ap.parse_args()

    res = json.load(open(args.eval, encoding="utf-8"))
    items = {json.loads(l)["id"]: json.loads(l) for l in MUESTRA.read_text(encoding="utf-8").split("\n") if l.strip()}
    rec = Recuperador(dir_bm25(args.seleccion), dir_denso(args.embedder, args.seleccion), None,
                      almacen=None, dispositivo=args.device)
    for f in res["preguntas"]:
        fin = f["etapas"]["final"]
        if fin["recall_docs"] is None or fin["recall_docs"] >= 1:
            continue
        it = items[f["id"]]
        oro = documentos_citados(it.get("legal_basis") or "")
        faltan = sorted(set(oro) - {c.split("/", 1)[0] for c in fin["top"]})
        q = consulta_de(it)
        b = rec.bm25.buscar(q, args.profundidad)
        d = rec.denso.buscar(q, args.profundidad)
        print(f"\n## {f['id']} [{f['formato']}] {it['pregunta'][:110]!r}")
        print(f"   legal_basis: {it.get('legal_basis')!r}")
        for doc in faltan:
            n = len(rec.almacen.por("doc_id", doc))
            pb, cb = primero(b, doc)
            pd, cd = primero(d, doc)
            arts = sorted(a for a in oro[doc] if a)
            print(f"   FALTA {doc} (arts {arts or '-'}; {n} chunks en el corpus)")
            print(f"      bm25: pos {pb} {cb}   |   denso: pos {pd} {cd}")
        print("   top-10 final:", ", ".join(fin["top"]))


if __name__ == "__main__":
    main()
