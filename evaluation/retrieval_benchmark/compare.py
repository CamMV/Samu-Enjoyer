"""Compara los brazos del banco de pruebas y dice cuál gana.

Reúne los `eval_*.json` de `results/` y los ordena por recall_citas@10 de la etapa
final (lo que puntúa el evaluador oficial), con recall_docs y MRR para desempatar.

Solo se comparan brazos que midieron lo mismo: el mismo subcorpus y el mismo número
de chunks en el índice. Un índice a medias saca mejor puntaje que uno completo por
tener menos con qué confundirse (lección de la tesis: un nDCG sobre 21.000 chunks se
comparó durante semanas contra otro de 625.000). Si los tamaños no coinciden, se
agrupan aparte y se avisa.

  python -m evaluation.retrieval_benchmark.compare
"""
from __future__ import annotations

import argparse
import collections
import json

from evaluation.retrieval_benchmark.config import RESULTS_ROOT


def cargar() -> list[dict]:
    out = []
    for f in sorted(RESULTS_ROOT.glob("eval_*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        r["_archivo"] = f.name
        out.append(r)
    return out


def grupo(r: dict) -> tuple:
    """Brazos comparables: mismo número de chunks en cada índice presente."""
    return tuple(sorted(r.get("n_chunks", {}).values()))


def tabla(resultados: list[dict]) -> str:
    grupos = collections.defaultdict(list)
    for r in resultados:
        grupos[grupo(r)].append(r)
    lin = []
    if len(grupos) > 1:
        lin.append(f"> Aviso: hay {len(grupos)} grupos con índices de distinto tamaño; solo se comparan dentro "
                   "de cada grupo.\n")
    for g, rs in grupos.items():
        rs.sort(key=lambda r: (-(r["por_etapa"]["final"]["recall_citas"] or 0),
                               -(r["por_etapa"]["final"]["recall_docs"] or 0), -(r["por_etapa"]["final"]["rr"] or 0)))
        lin += [f"### Índices de {g} chunks", "",
                "| # | Brazo | recall_citas@10 | recall_docs@10 | MRR | nDCG@10 | rerank s (media/p95) |",
                "|---|---|---|---|---|---|---|"]
        for i, r in enumerate(rs, 1):
            f = r["por_etapa"]["final"]
            t = r["tiempos_s"].get("reranker", {})
            lin.append(f"| {i} | {r['config']['nombre']} | {f['recall_citas']} | {f['recall_docs']} | {f['rr']} | "
                       f"{f['ndcg']} | {t.get('media', '—')}/{t.get('p95', '—')} |")
        lin.append("")
    return "\n".join(lin)


def main():
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    resultados = cargar()
    if not resultados:
        print(f"No hay resultados en {RESULTS_ROOT}")
        return
    md = tabla(resultados)
    (RESULTS_ROOT / "comparacion.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
