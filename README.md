# Samu-Enjoyer — Hackathon IA Week 2026

**Integrantes:** Santiago Gómez, Camilo Murcia, Angie Gutiérrez
**Universidad de los Andes**

Sistema de respuesta a preguntas de derecho colombiano con modelos abiertos pequeños (Qwen3-8B,
Qwen3-Embedding-0.6B y bge-reranker-v2-m3) y un corpus jurídico propio de 31.037 documentos oficiales.
Cada respuesta cita solo normas que están en los 10 pasajes que recuperó para esa pregunta. Todo corre
en local y sin red: el agente no llama a ningún servicio externo.

## Corpus e índice

| Recurso | Enlace | Tamaño | Licencia |
|---|---|---|---|
| Corpus procesado e índice (`samu_enjoyer_corpus_indice.zip`) | PENDIENTE | ~4,59 GB (≈15 GB descomprimido) | CC BY 4.0 |

El comprimido se descomprime **en la raíz del repositorio** y deja todo bajo `corpus/`:

- `LICENSE` y `corpus_manifest.json`;
- `chunks/chunks.sqlite`: 2.211.359 fragmentos con su texto y metadatos;
- `indices/`: BM25 y HNSW del corpus completo y del subconjunto de normas;
- `SHA256SUMS.txt`.

El detalle del corpus está en [`CORPUS.md`](CORPUS.md) y el inventario por documento, en
[`corpus_manifest.json`](corpus_manifest.json).

El enlace permanece activo hasta el **2 de noviembre de 2026** (treinta días después del evento).

## Arquitectura

```
pregunta ─→ flags (del ítem, sin LLM) ─→ consulta: cerrada = pregunta + opciones A-D; libre = pregunta original
        ─→ recuperación híbrida: siglas expandidas → citas expresas + BM25 + HNSW + lista de normas
           → RRF (k=60) → bge-reranker-v2-m3 → ajustes de vigencia y tipo → selección diversa → 10 pasajes
        ─→ Qwen3-8B (llama.cpp, T=0) redacta solo con esos 10 pasajes
        ─→ validación determinista de citas contra doc_id/art_N → post-proceso → submissions.jsonl
```

El flujo es un `StateGraph` de **LangGraph** (`src/agent/graph.py`): `entrada` → `consulta_cerrada` o
`reescribir_consulta` → `recuperar` → `escribir` → `validar_fuentes` ⇄ `buscar_citas` → `finalizar`.
Se compila sin checkpointer y sin ramas paralelas, así que cada pregunta se resuelve sola y de forma
reproducible. El diagrama interactivo está en `informe/arquitectura_final.html`.

| Componente | Elección | Motivo |
|---|---|---|
| Encoder | Qwen3-Embedding-0.6B (dim 1024) en FAISS `IndexHNSWSQ` 8 bits (M=32, efSearch 256) | Ganó en el banco de pruebas frente a bge-m3 y e5-large-instruct; SQ8 permite cargar 2,2 M vectores |
| Léxico | BM25 (bm25s) con raíces Snowball e IDs normativos normalizados | Las opciones de las cerradas traen términos exactos ("Ley 472", "falsa motivación"). Se usa solo en cerradas: en lenguaje natural mete pasajes de otro tema |
| Lista de normas | BM25 y HNSW extra solo sobre los fragmentos de normas (50 + 50 candidatos) | Las sentencias son ~85 % del corpus y enterraban códigos y Constitución |
| Fusión | Reciprocal Rank Fusion (k=60) de citas expresas, BM25, HNSW y la lista de normas | Fusiona por posición, sin calibrar escalas de puntaje |
| Reordenamiento | bge-reranker-v2-m3 (fp16) sobre los 150 primeros. Después: castigo a derogadas y a preámbulos y notas, ≤ 4 sentencias y ≤ 3 pasajes por documento, sin casi duplicados (≥ 70 %) | recall_docs@10 de 0,439 a 0,858 y recall_citas@10 de 0,862 a 0,931 frente a la configuración base |
| Decoder | Qwen3-8B Q4_K_M en llama.cpp: temperatura 0, top_k 1, semilla 42, sin modo de razonamiento, `cache_prompt: false` | Local y abierto. Dos corridas dan respuestas idénticas, lo que exige la verificación en vivo |
| Segmentación | Un fragmento por artículo con ruta jerárquica y encabezado citable; sentencias en ficha + ventanas de ~1.700 caracteres | Cada fragmento tiene un ID canónico `<doc_id>/art_<N>` que se puede citar y validar |
| Validación de citas | Determinista, sin LLM: toda cita `[doc_id/art_N]` debe estar entre los 10 pasajes; si no, se suprime | El evaluador solo da por respaldada una cita cuyo documento está en `pasajes_recuperados` |
| Mecanismo de abstención | Texto libre: `abstencion: true` si el LLM no responde en 300 s o no hay pasajes; nunca una respuesta simulada. Cerradas: siempre una letra; si no queda una válida, la opción con más respaldo léxico en los pasajes | Regla de los organizadores: las cerradas no se abstienen. Además, responder rinde más que abstenerse |
| Juez LLM | En el código (`--juez`, Gemma 4 E4B), **apagado** | Sin juez salió mejor en todo: RAGAS 0,485 contra 0,469, cerradas 13/15 contra 12/15 y la mitad del tiempo |

Formatos de salida: las semiabiertas tienen hasta 150 palabras, con la primera oración respondiendo la
sub-tarea; las abiertas tienen hasta 500 palabras, en IRAC (`marco_normativo`, `analisis`,
`jurisprudencia`, `conclusion`). Las citas se reescriben como "artículo N del …" para que el evaluador
oficial las reconozca.

## Despliegue

Guía para levantar el sistema completo (LLM + back + interfaz) en una máquina nueva. Todo corre en
local: después de descargar los modelos y el índice, no hace falta red.

### Requisitos

| Pieza | Versión / recurso |
|---|---|
| Sistema | Linux (probado en Ubuntu 22.04); también funciona en Windows |
| GPU | NVIDIA con CUDA y ≥ 16 GB recomendados (probado en RTX 4090 24 GB y A40). Con ≤ 8 GB, ver `RAG_DEVICE_DENSO` abajo |
| RAM | 32 GB mínimo (64 GB recomendados) |
| Disco | ~25 GB libres: índice descomprimido (~15 GB), GGUF (~5 GB) y modelos de Hugging Face (~3 GB) |
| Python | 3.12 |
| Node.js | 18 o superior (solo para la interfaz) |
| llama.cpp | `llama-server` compilado con CUDA |

### 1. Código y entorno de Python

```bash
git clone https://github.com/CamMV/Samu-Enjoyer.git
cd Samu-Enjoyer
python3.12 -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cu124   # torch con CUDA, antes que el resto
pip install -r requirements.txt
```

### 2. Corpus e índice

Descargar `samu_enjoyer_corpus_indice.zip` desde la sección [Corpus e índice](#corpus-e-índice),
descomprimirlo en la raíz del repositorio (deja todo bajo `corpus/`) y verificarlo:

```bash
unzip samu_enjoyer_corpus_indice.zip -d .
python -m src.knowledge.verify_indices            # debe terminar en TODO CORRECTO
```

### 3. Modelos

- **Decoder:** Qwen3-8B en GGUF Q4_K_M para llama.cpp.

  ```bash
  mkdir -p modelos
  huggingface-cli download Qwen/Qwen3-8B-GGUF Qwen3-8B-Q4_K_M.gguf --local-dir modelos
  ```

- **Encoder y reranker** (`Qwen/Qwen3-Embedding-0.6B` y `BAAI/bge-reranker-v2-m3`): se descargan solos
  de Hugging Face la primera vez que arranca el back o `batch_runner`, y quedan en la caché local
  (`~/.cache/huggingface`). Después de esa primera vez se puede trabajar sin red
  (`export HF_HUB_OFFLINE=1`).

### 4. Configuración

```bash
cp .env.example .env
```

En `.env`, ajustar como mínimo:

| Variable | Valor | Para qué |
|---|---|---|
| `LLM_BASE_URL` | `http://127.0.0.1:8010/v1` | Servidor local del LLM. **No usar el puerto 8000**, que es del back |
| `RAG_DEVICE_DENSO` | vacío, o `cpu` en GPUs de ≤ 8 GB | Pone el embedder de la consulta en CPU; los pasajes salen idénticos |

Lo demás ya viene con la configuración de la entrega. El juez (`JUDGE_*`) no se usa.

### 5. Levantar los servicios

Tres procesos, cada uno en su terminal (o en `tmux`), desde la raíz del repositorio:

```bash
# Terminal 1 — LLM (Qwen3-8B, temperatura 0, determinista). -np 1 es obligatorio.
llama-server -m modelos/Qwen3-8B-Q4_K_M.gguf --host 127.0.0.1 --port 8010 -c 32768 -np 1 \
             --jinja --temp 0 --top-k 1 --seed 42 -ngl 99

# Terminal 2 — Back (FastAPI). Carga índices, reranker y embedder (~1-2 min).
source .venv/bin/activate
python -m src.api.server --host 127.0.0.1 --port 8000

# Terminal 3 — Interfaz (React + Vite)
cd interfaz
cp .env.example .env              # luego poner VITE_USE_MOCK=0 para usar el back real
npm install
npm run dev                       # http://localhost:3000
```

Para servir la versión compilada en lugar del modo desarrollo: `npm run build && npm run preview`
(también en el puerto 3000, con el mismo proxy `/api` hacia el back).

| Servicio | Dirección | Comprobación |
|---|---|---|
| LLM (llama.cpp) | `http://127.0.0.1:8010` | `curl http://127.0.0.1:8010/health` |
| Back (FastAPI) | `http://127.0.0.1:8000` | `curl http://127.0.0.1:8000/api/salud` → `"modo": "real"` |
| Interfaz | `http://localhost:3000` | Abrir en el navegador y hacer una pregunta |

### 6. Pruebas rápidas

```bash
# Sin índices ni LLM (solo comprueba la instalación)
python -m src.agent.batch_runner --mock --limite 3 --salida /tmp/prueba.jsonl
python -m src.api.server --mock                     # back simulado para la interfaz
# Con todo levantado: 3 preguntas reales de la muestra
python -m src.agent.batch_runner --limite 3 --salida /tmp/prueba_real.jsonl
```

En la interfaz, `VITE_USE_MOCK=1` muestra respuestas de ejemplo sin back.

### Problemas comunes

- **El back se detiene con error al arrancar:** falta `corpus/` o no pasó
  `verify_indices` (paso 2).
- **Cada pregunta tarda ~60 s:** la GPU no alcanza para embedder y reranker; poner
  `RAG_DEVICE_DENSO=cpu` en `.env`.
- **Error de contexto en el LLM:** `llama-server` debe arrancar con `-c 32768`.
- **Respuestas que cambian entre corridas:** `llama-server` debe correr con `-np 1`, y no hay que
  cambiar el GGUF ni sus banderas.
- **La interfaz no llega al back:** revisar que `VITE_BACK_URL` en `interfaz/.env` apunte a
  `http://127.0.0.1:8000` y reiniciar `npm run dev`.

## Reproducción

Todo corre en local y sin red, una vez instaladas las dependencias, descargado el GGUF y descomprimido
el índice. Pasos desde la raíz del repositorio (Python 3.12):

```bash
# 1. Dependencias (en GPU, primero torch con CUDA)
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt

# 2. Índice: descomprimir samu_enjoyer_corpus_indice.zip en la raíz y verificarlo
python -m src.knowledge.verify_indices            # debe terminar en TODO CORRECTO

# 3. Servidor local del LLM (Qwen3-8B GGUF Q4_K_M) en localhost:8010; dejarlo corriendo
llama-server -m Qwen3-8B-Q4_K_M.gguf --host 127.0.0.1 --port 8010 -c 32768 -np 1 \
             --jinja --temp 0 --top-k 1 --seed 42 -ngl 99

# 4. Inferencia sobre las 992 preguntas (comando único de la entrega)
LLM_BASE_URL=http://127.0.0.1:8010/v1 \
python -m src.agent.batch_runner --entrada data/test_992.jsonl --salida submissions.jsonl
```

- **Configuración de la LLM:** `LLM_BASE_URL` también puede ir en `.env` (copiar `.env.example`). La
  configuración de la entrega es la que trae el código por defecto: no hace falta ninguna variable más.
- **Paralelismo:** no usar `-np` mayor que 1. Mezcla preguntas en un lote y la salida deja de ser
  reproducible.
- **Validación:** `batch_runner` valida cada registro contra `schema/submission.schema.json`.
- **Prueba de humo sin índices ni LLM:** `python -m src.agent.batch_runner --mock --limite 3 --salida /tmp/prueba.jsonl`.
- **Muestra pública:**
  `python -m src.agent.batch_runner --salida logs/sample.jsonl` y luego
  `python scripts/evaluate.py --submission logs/sample.jsonl --split sample`.

**Requisitos de hardware:** la corrida oficial y la verificación en vivo se hacen en una Dell Precision
3680 con una RTX 4090 de 24 GB, 64 GB de RAM y Ubuntu 22.04. Un proceso ocupa ~13-14 GB de GPU: ~10 GB
el LLM con 32k de contexto, y el resto el reranker y el embedder. En GPUs de ≤ 8 GB se pone
`RAG_DEVICE_DENSO=cpu` (embedder en CPU, reranker en GPU); los pasajes salen idénticos.

**Tiempo estimado:**
- 50 preguntas de muestra: ~8,9 s por pregunta en una A40 (~7 min); ~6-7 s en la RTX 4090.
- 992 preguntas: ~2 h en la RTX 4090.
- Arranque: ~1-2 min (carga de índices, reranker y embedder).

**Reconstruir el índice desde cero** (opcional; horas de GPU):
1. `python scraper/descargar.py iniciar`
2. `python -m src.ingest.convertir`
3. `python -m src.knowledge.chunking`
4. `python -m src.knowledge.bm25_store --seleccion todo` (y `--seleccion normas`)
5. `python -m src.knowledge.vector_store --modelo qwen3-emb-0.6b --seleccion todo`

## Resultados sobre las preguntas de muestra

Configuración de la entrega (v27, la misma que generó `submissions.jsonl`), métricas deterministas de
`scripts/evaluate.py` sobre `sample_50`. Las cifras son iguales en la A40 y en la RTX 4090:

| Componente | Puntos | Posibles |
|---|---:|---:|
| Exactitud en cerradas (13/15) | 17,33 | 20 |
| Calidad de citación | 18,37 | 20 |
| Abstención calibrada | 9,07 | 10 |
| **Subtotal determinista** | **44,77** | **50** |
| Corrección en texto libre (RAGAS, juez oficial) | ~14,2 (~0,474; referencia 0,451) | 30 |

## Interfaz gráfica

La interfaz permite formular una pregunta y ver la respuesta con sus pasajes y normas citadas. Cada
cita abre su pasaje, y cada pasaje abre el documento completo con el fragmento resaltado. Usa el mismo
agente que `batch_runner`: un ítem del banco enviado con su `id`, `formato` y `opciones` da el mismo
registro que en `submissions.jsonl`.

```bash
# 1. LLM en el puerto 8010 (el comando de llama-server de arriba)
# 2. Back (FastAPI) en 127.0.0.1:8000
pip install -r requirements.txt                                   # si no se instaló antes
LLM_BASE_URL=http://127.0.0.1:8010/v1 python -m src.api.server        # --mock: sin índices ni LLM
# 3. Front (React + Vite, Node 18+), con VITE_USE_MOCK=0 en interfaz/.env
cd interfaz && cp .env.example .env && npm install && npm run dev      # http://localhost:3000
```

## Estructura del repositorio

```
Samu-Enjoyer/
├── README.md
├── LICENSE                    # CC BY 4.0 (corpus procesado e índice)
├── requirements.txt           # todas las dependencias de Python
├── submissions.jsonl          # 992 respuestas, esquema oficial (schema/submission.schema.json)
├── CORPUS.md                  # bitácora del corpus
├── corpus_manifest.json       # inventario por documento
├── informe/
│   ├── INFORME_TECNICO.pdf    # informe técnico (máximo 3 páginas)
│   ├── main.tex               # fuente del informe
│   └── arquitectura_final.html
├── interfaz/                  # interfaz gráfica (React + Vite)
├── src/                       # pipeline reproducible: ingest/, knowledge/, agent/, api/
├── data/                      # sample_50.jsonl, test_992.jsonl, corpus_targets.json
├── schema/  scripts/          # material oficial del reto (esquema y evaluador)
├── scraper/                   # descarga del corpus desde las URL oficiales
├── evaluation/                # banco de pruebas de recuperación y sus resultados
└── tests/
```

El corpus procesado y el índice no se versionan: se descargan desde la sección
[Corpus e índice](#corpus-e-índice).

## Limitaciones conocidas

1. **Lo que no está en el corpus no se puede citar.** 117 documentos no están disponibles en la fuente
   oficial (90 de la Corte Suprema) y 9 sentencias C recientes no produjeron fragmentos. En la muestra,
   la citación y la abstención que faltan corresponden a documentos que la búsqueda no trae al top-10.
2. **Cerradas en el límite.** La 128 (el corpus no respalda "Fintech" en leasing) y la 748 (el art. 137
   del CPACA no llega al top-10) no tienen respaldo alcanzable. Algunas preguntas en el borde cambian
   con el hardware aun con temperatura 0.
3. **RAGAS limitado por el contenido.** Con Qwen3-8B sin razonamiento, los errores de texto libre
   vienen de la búsqueda o del razonamiento del modelo, no de la forma. El modo de razonamiento se
   midió y dio peor RAGAS (0,441) con el doble de tiempo.
4. **Abiertas sin norma nombrada.** Las preguntas de caso que no nombran la norma tienen el recall más
   bajo (0,5 en la muestra). La expansión de la consulta con el LLM se probó y se descartó, porque
   inventaba normas.
