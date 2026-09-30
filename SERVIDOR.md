# Pipeline de recuperación en el servidor (A40)

Construye los chunks, los índices (BM25 + HNSW) y corre el banco de pruebas de
recuperación (BM25 + HNSW → RRF → reranker) sobre las 50 preguntas de muestra.
El portátil solo recibe los índices del ganador: la demo y la verificación en vivo
corren allá, así que embedder y reranker son modelos que caben en 4 GB.

## Estructura (igual que la tesis)

| Ruta | Qué hace |
|---|---|
| `src/knowledge/chunking.py` | `corpus/md` → `corpus/chunks/chunks.jsonl` + `chunks.sqlite` (artículo = chunk; sentencias por sección + ficha) |
| `src/knowledge/tokenization.py` | Normalización BM25 (minúsculas, sin tildes, identificadores y sentencias en un token, stemming; sin quitar stopwords) |
| `src/knowledge/bm25_store.py` | Índice BM25 (bm25s) |
| `src/knowledge/embedding_variants.py` | Embedders y rerankers comparados |
| `src/knowledge/vector_store.py` | Embeddings (GPU, por lotes reanudables) + HNSW (FAISS, SQ8) |
| `src/knowledge/hybrid_search.py` | Citas expresas + BM25 + HNSW → RRF → reranker → 10 pasajes (expande artículos partidos) |
| `src/knowledge/reranker.py` | bge-reranker-v2-m3 / Qwen3-Reranker-0.6B |
| `src/knowledge/citation_lookup.py` | Citas de un texto → doc_id/chunks (usa `scripts/citations.py` del evaluador oficial) |
| `evaluation/retrieval_benchmark/` | `config`, `index_variants`, `evaluate`, `metrics`, `compare`, `run_all` |

## 0. Preparar (una vez)

En el portátil, empaquetar el corpus convertido (~2,6 GB → ~0,7 GB comprimido) y copiarlo:

```bash
tar -czf corpus_md.tar.gz -C corpus --exclude=md/_cache_doc --exclude=md/_control --exclude=md/_auditoria md
scp corpus_md.tar.gz usuario@servidor:~/
```

En el servidor:

```bash
git clone https://github.com/CamMV/Samu-Enjoyer.git && cd Samu-Enjoyer
conda create -n IA python=3.12 -y && conda activate IA
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt -r requirements-rag.txt
mkdir -p corpus && tar -xzf ~/corpus_md.tar.gz -C corpus
python -m pytest -q tests                      # 50 pruebas en verde antes de empezar
```

Correr todo dentro de `tmux` (o con `nohup`): si se cae la sesión, se relanza el mismo
comando y cada etapa retoma (chunks, índices y lotes de vectores ya hechos se saltan).

## 1. Prueba de humo (5 minutos)

```bash
python -m src.knowledge.chunking --procesos 32
python -m src.knowledge.bm25_store --seleccion normas_fichas --limite 20000 --salida corpus/indices/humo_bm25
python -m src.knowledge.vector_store --modelo bge-m3 --seleccion normas_fichas --limite 20000 --device cuda:0 --salida corpus/indices/humo_denso
python -m evaluation.retrieval_benchmark.evaluate --bm25 corpus/indices/humo_bm25 --denso corpus/indices/humo_denso --reranker bge-reranker-v2-m3 --device cuda:0 --nombre humo
```

Debe imprimir la tabla por etapa (bm25, denso, rrf, rerank, final). Con solo 20.000
chunks los números no significan nada; es para ver que todo corre. Después:
`rm -r corpus/indices/humo_* evaluation/retrieval_benchmark/results/eval_humo.*`

## 2. Banco de pruebas (subcorpus normas + fichas)

3 embedders × 2 BM25 (con y sin raíces) × 3 rerankers (dos y ninguno) = 18 brazos.

```bash
python -m evaluation.retrieval_benchmark.run_all --seleccion normas_fichas --device cuda:0
```

Resultado: `evaluation/retrieval_benchmark/results/comparacion.md` (ordenado por
`recall_citas@10` de la etapa final, que es lo que puntúa el evaluador) y un
`eval_<brazo>.md` por brazo con el detalle por etapa y los tiempos del reranker.

## 3. El ganador sobre el corpus completo

```bash
python -m evaluation.retrieval_benchmark.run_all --seleccion todo --embedders <ganador> --bm25 <con|sin> --rerankers <reranker_ganador> --device cuda:0
```

## 4. Traer al portátil

Solo lo que usa la búsqueda (sin los `vec_*.npy`):

```
corpus/chunks/chunks.sqlite
corpus/indices/bm25_todo[_sin_raices]/
corpus/indices/<ganador>_todo/{hnsw.faiss,ids.json,info.json}
evaluation/retrieval_benchmark/results/
```

## Tiempos y recursos esperados (A40)

| Etapa | Tiempo aprox. | Recursos |
|---|---|---|
| Chunking (31.037 .md) | 5-10 min con 32 procesos | ~2-3 M de chunks, ~6 GB en disco |
| BM25 normas_fichas / todo | 5-10 min / 40-90 min | todo: 40-60 GB de RAM al construir |
| HNSW por embedder, normas_fichas | 10-25 min | GPU |
| HNSW, todo | 1,5-4 h | GPU; ~3 GB el índice SQ8 |
| Evaluación por brazo | 1-3 min | 50 preguntas |

Los tiempos son estimados: la primera línea de avance de cada etapa da el ritmo real.
