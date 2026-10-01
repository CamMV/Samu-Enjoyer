## normas_fichas__qwen3-emb-0.6b__bm25__bge-reranker-v2-m3__completo

k=10, n=50, chunks en el índice {'bm25': 300912, 'denso': 300912}, cobertura 1.0

| Etapa | recall_citas@k | recall_docs@k | MRR | nDCG@k |
|---|---|---|---|---|
| bm25 | 0.772 | 0.541 | 0.225 | 0.337 |
| denso | 0.736 | 0.699 | 0.411 | 0.541 |
| rrf | 0.841 | 0.695 | 0.413 | 0.548 |
| rerank | 0.886 | 0.764 | 0.437 | 0.574 |
| final | 0.935 | 0.837 | 0.448 | 0.601 |

| Formato (final) | recall_citas@k | recall_docs@k |
|---|---|---|
| multiple_choice | 1.0 | 0.923 |
| open_ended | 0.667 | 0.667 |
| semi_open | 0.944 | 0.819 |

| Tiempo (s) | media | p95 |
|---|---|---|
| citas | 0.001 | 0.002 |
| bm25 | 0.042 | 0.067 |
| denso | 0.106 | 0.049 |
| reranker | 0.252 | 0.277 |
| seleccion | 0.001 | 0.007 |
