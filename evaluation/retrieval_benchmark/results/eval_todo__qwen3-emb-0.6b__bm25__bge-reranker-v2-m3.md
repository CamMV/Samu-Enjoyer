## todo__qwen3-emb-0.6b__bm25__bge-reranker-v2-m3

k=10, n=50, chunks en el índice {'bm25': 2210629, 'denso': 2210629}, cobertura 1.0

| Etapa | recall_citas@k | recall_docs@k | MRR | nDCG@k |
|---|---|---|---|---|
| bm25 | 0.756 | 0.415 | 0.17 | 0.258 |
| denso | 0.862 | 0.423 | 0.176 | 0.256 |
| rrf | 0.882 | 0.545 | 0.263 | 0.372 |
| rerank | 0.862 | 0.439 | 0.236 | 0.313 |
| final | 0.862 | 0.439 | 0.236 | 0.314 |

| Formato (final) | recall_citas@k | recall_docs@k |
|---|---|---|
| multiple_choice | 0.846 | 0.308 |
| open_ended | 0.417 | 0.333 |
| semi_open | 0.944 | 0.528 |

| Tiempo (s) | media | p95 |
|---|---|---|
| citas | 0.001 | 0.002 |
| bm25 | 0.201 | 0.376 |
| denso | 0.124 | 0.076 |
| reranker | 0.253 | 0.274 |
| seleccion | 0.0 | 0.0 |
