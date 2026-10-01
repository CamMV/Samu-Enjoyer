## todo__qwen3-emb-0.6b__bm25__bge-reranker-v2-m3__completo_c200

k=10, n=50, chunks en el índice {'bm25': 2210629, 'denso': 2210629}, cobertura 1.0

| Etapa | recall_citas@k | recall_docs@k | MRR | nDCG@k |
|---|---|---|---|---|
| bm25 | 0.756 | 0.415 | 0.17 | 0.258 |
| denso | 0.862 | 0.423 | 0.176 | 0.256 |
| rrf | 0.882 | 0.545 | 0.268 | 0.375 |
| rerank | 0.837 | 0.447 | 0.246 | 0.326 |
| final | 0.862 | 0.642 | 0.271 | 0.394 |

| Formato (final) | recall_citas@k | recall_docs@k |
|---|---|---|
| multiple_choice | 0.846 | 0.615 |
| open_ended | 0.417 | 0.417 |
| semi_open | 0.944 | 0.694 |

| Tiempo (s) | media | p95 |
|---|---|---|
| citas | 0.001 | 0.002 |
| bm25 | 0.175 | 0.37 |
| denso | 0.104 | 0.053 |
| reranker | 0.248 | 0.272 |
| seleccion | 0.0 | 0.001 |
