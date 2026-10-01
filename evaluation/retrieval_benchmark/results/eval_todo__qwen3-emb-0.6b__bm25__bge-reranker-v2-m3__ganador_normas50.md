## todo__qwen3-emb-0.6b__bm25__bge-reranker-v2-m3__ganador_normas50

k=10, n=50, chunks en el índice {'bm25': 2210629, 'denso': 2210629}, cobertura 1.0

| Etapa | recall_citas@k | recall_docs@k | MRR | nDCG@k |
|---|---|---|---|---|
| bm25 | 0.756 | 0.415 | 0.17 | 0.258 |
| denso | 0.862 | 0.423 | 0.176 | 0.256 |
| rrf | 0.898 | 0.744 | 0.39 | 0.536 |
| rerank | 0.874 | 0.569 | 0.393 | 0.478 |
| final | 0.919 | 0.785 | 0.416 | 0.552 |

| Formato (final) | recall_citas@k | recall_docs@k |
|---|---|---|
| multiple_choice | 0.962 | 0.808 |
| open_ended | 0.5 | 0.5 |
| semi_open | 0.965 | 0.819 |

| Tiempo (s) | media | p95 |
|---|---|---|
| citas | 0.001 | 0.002 |
| bm25 | 0.191 | 0.414 |
| denso | 0.111 | 0.058 |
| normas | 0.043 | 0.076 |
| reranker | 0.659 | 0.733 |
| seleccion | 0.001 | 0.006 |
