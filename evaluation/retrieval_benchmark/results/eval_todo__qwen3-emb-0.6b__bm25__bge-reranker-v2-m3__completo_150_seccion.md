## todo__qwen3-emb-0.6b__bm25__bge-reranker-v2-m3__completo_150_seccion

k=10, n=50, chunks en el índice {'bm25': 2210629, 'denso': 2210629}, cobertura 1.0

| Etapa | recall_citas@k | recall_docs@k | MRR | nDCG@k |
|---|---|---|---|---|
| bm25 | 0.756 | 0.415 | 0.17 | 0.258 |
| denso | 0.862 | 0.423 | 0.176 | 0.256 |
| rrf | 0.882 | 0.545 | 0.263 | 0.372 |
| rerank | 0.85 | 0.533 | 0.35 | 0.44 |
| final | 0.898 | 0.764 | 0.38 | 0.52 |

| Formato (final) | recall_citas@k | recall_docs@k |
|---|---|---|
| multiple_choice | 0.962 | 0.692 |
| open_ended | 0.417 | 0.417 |
| semi_open | 0.944 | 0.861 |

| Tiempo (s) | media | p95 |
|---|---|---|
| citas | 0.001 | 0.002 |
| bm25 | 0.193 | 0.354 |
| denso | 0.115 | 0.067 |
| reranker | 0.675 | 0.749 |
| seleccion | 0.0 | 0.002 |
