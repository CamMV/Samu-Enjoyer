# Hackathon IA Week 2026 — Sistema RAG de Derecho Colombiano

Sistema de respuesta a preguntas jurídicas colombianas con modelos abiertos pequeños (Qwen3-8B, Qwen3-Embedding-0.6B, bge-reranker-v2-m3).
El valor del reto reside en la fidelidad jurídica y en el corpus: **cada respuesta debe citar normas respaldadas en los pasajes recuperados**. Lo que no esté en el corpus no se puede inventar ni citar.

---

## 1. Reglas y Documentación de Referencia

Se encuentra un enlace simbólico a la carpeta de instrucciones llamada `docs_reto/`
- **Enunciado y lineamientos:** `docs_reto/enunciado.pdf` 
- **Arquitectura de referencia:** `docs_reto/arquitecturas_hackathon_local.html` 
- **Esquemas JSON esperados:** carpetas `docs_reto/schema/` y ejemplos en `docs_reto/Ejemplo de entrega/` / `docs_reto/entregables/`.
- **Datos y banco de prueba:** `data/sample_50.jsonl` y `data/corpus_targets.json` (actualizadas en la raíz)
- **Formato de entrega:** Generación estricta de `submissions.jsonl` según el schema oficial.

# PROHIBICIÓN ESTRICTA (Causal de descalificación)
- Prohibido el uso de APIs o modelos cerrados/propietarios (OpenAI, Anthropic, Google, Cohere) en CUALQUIER componente del sistema (generación, reescritura, reranking o datos sintéticos).
- TODO el pipeline debe correr sobre modelos abiertos: Qwen3-8B local (vía vLLM / Ollama / llama.cpp con API local), bge-m3 y bge-reranker-v2-m3.
- Las llamadas HTTP del agente siempre deben apuntar a hosts locales o de infraestructura propia (`http://localhost:...` o variables `LLM_BASE_URL` internas), nunca a servicios SaaS de terceros.
---

## 2. Frente Agente RAG (Orquestador, Escritor y Juez)

### Restricciones y Reglas de Respuesta
- **Modelo:** escritor Qwen3-8B y juez Gemma 4 E4B, ambos con `Temperature = 0`. Modelos abiertos en todo el pipeline.
- **Entrada y Formatos:** Preguntas de `sample_50.jsonl` o UI. Detección de formato:
  - *Cerradas (opción múltiple):* Búsqueda con pregunta + opciones A, B, C, D (determinista, sin LLM).
  - *Abiertas / semiabiertas:* Query rewriter con términos jurídicos y normas candidatas.
- **Top-10 Pasajes:** Toda redacción se hace **exclusivamente con los 10 pasajes** entregados por la recuperación híbrida (BM25 + HNSW con Qwen3-Embedding-0.6B + RRF + bge-reranker-v2-m3; ver sección 5).
- **Validación Determinista de Fuentes (Sin LLM):** 
  - Toda cita en la respuesta debe mapearse a un ID canónico (`<doc_id>/art_<N>`, ej. `codigo_general_proceso/art_42`).
  - Si una cita no existe en los 10 pasajes recuperados, se suprime o se activa `abstencion: true`.
  - **Subagente de búsqueda de citas** (`src/agent/tools/citation_search_tool.py`, nodo `buscar_citas`, sin LLM): **por defecto solo suprime** del borrador las citas fuera de los pasajes. Con `CITAS_AGREGAR_PASAJES=1` busca la cita en `chunks.sqlite` y, si existe y está vigente, agrega su pasaje (sustituye al último no citado; nunca más de 10). **Decisión (1/oct): apagado**, porque la afirmación no se redactó con ese texto y los pasajes dejarían de depender solo de la búsqueda determinista que se reproduce en la verificación en vivo. El informe queda en la llave `citas` de `<salida>.juez.jsonl`.
- **LLM as Judge:** Evalúa si responde la sub-tarea, si cada afirmación tiene pasaje que la soporte y la coherencia del área jurídica.
- **Voto en cerradas (1/oct, `JUDGE_VOTO_CERRADAS=1`):** en las cerradas el juez (Gemma) no revisa el borrador: responde la pregunta a ciegas con los mismos 10 pasajes (`votar_cerrada` en `judge_tool.py`) y se compara su letra con la del escritor (Qwen). Coinciden → se entrega el borrador de Qwen. Discrepan → ciclo 2 con nueva búsqueda (consulta que sugiere el juez o, si no sugiere, el texto de las dos opciones en disputa) y se vota otra vez. Si persiste, **gana Qwen por ahora** (letra y justificación del mismo modelo, sin regenerar); cuál modelo debe ganar se decide con la corrida comparativa del servidor. Una discrepancia nunca fuerza abstención. Si Gemma no responde, queda la respuesta de Qwen con aviso en stderr. Los votos quedan en `voto` / `voto_escritor` de `<salida>.juez.jsonl`. Sin medir aún en la muestra.
- **Control de Ciclos:** Máximo 2 ciclos por pregunta. Si el Juez rechaza en el ciclo 1, el orquestador reintenta ajustando la consulta con el feedback recibido.
- **Orquestación con LangGraph:** el flujo es un `StateGraph` en `src/agent/graph.py` (`entrada` → `consulta_cerrada` | `reescribir_consulta` → `recuperar` → `escribir` → `validar_fuentes` ⇄ `buscar_citas` → `juzgar` → `finalizar`), compilado sin checkpointer (sin memoria entre preguntas) y sin ramas paralelas. `LegalAgent` (`src/agent/agent.py`) es la fachada; `run_with_judge` activa el nodo del juez. `python -m src.agent.graph` imprime el grafo en Mermaid. El trazado de LangSmith se fuerza apagado (ninguna llamada sale a terceros).

---

## 3. Convenciones del Corpus e IDs Canónicos (Para Citas y Búsqueda)

- **ID canónico de documento (`doc_id`):** Definido en `data/corpus_targets.json` (ej. `codigo_general_proceso` para la Ley 1564 de 2012, `constitucion`, `codigo_civil`, `jurisprudencia_c-355_2006`).
- **ID canónico de pasaje / chunk:** Formato `<doc_id>/art_<N>` (ej. `codigo_general_proceso/art_42`). Otros tipos: `<doc_id>/art_<N>#<parte>`, `<doc_id>/art_<N>/notas`, `<doc_id>/preambulo#<i>`, `<doc_id>/anexo#<i>`, `<doc_id>/ficha` y `<doc_id>/<sección>#<ventana>` en sentencias.
- **Metadatos y Vigencia:** Los documentos convertidos a Markdown contienen front-matter con metadatos (`tipo_norma`, `numero`, `anio`, `vigencia`); cada chunk los hereda en `corpus/chunks/chunks.sqlite`. **No citar normas marcadas como derogadas o transitorias como si fueran derecho vigente.**
- **Fuentes válidas admitidas:** Senado, SUIN-Juriscol, relatorías de altas cortes (CC, CSJ, CE), DAPRE, DIAN, SIC, Función Pública, Cancillería y Colpensiones.

---

## 4. Estado y Operación del Corpus (`src/ingest/`) — TERMINADO

- **Descarga:** 31.157 registros en el manifiesto: 31.037 `ok`, 117 fallas, 3 duplicados (cobertura 99,6 %; bitácora en `DESCARGA.md`).
- **Conversión a Markdown:** 31.037 `.md` (uno por documento `ok`) con front-matter de metadatos; OCR (Tesseract spa) para las capas de texto ilegibles.
  ```bash
  python -m src.ingest.convertir            # convierte corpus/raw -> corpus/md
  python -m src.ingest.convertir --estado
  pytest tests/                             # 72 pruebas
  ```
- **Dónde está cada cosa (PC de Santiago):**
  - `T:\Proyectos\Samu-Enjoyer\corpus_md.tar.gz` — los 31.037 `.md` + su `corpus_manifest.json` de conversión (única copia local; también en el servidor).
  - `T:\Proyectos\Samu-Enjoyer-archivo\raw\` — originales (~25 GB) + `corpus_manifest.json` de **descarga** (fuente, URL y fecha por documento; entregable 4).
  - `T:\Proyectos\Samu-Enjoyer-archivo\descarga\` — `auditoria.json` (evidencia de cobertura para `CORPUS.md`) y logs.
  - No borrar ninguno de los tres antes de que se acepten los entregables.

---

## 5. Recuperación (`src/knowledge/`) — CONGELADA

Arquitectura obligatoria BM25 + HNSW → RRF → reranker. Configuración ganadora = valores por defecto de `Config()` en `src/knowledge/hybrid_search.py` (perfil `ganador_dedup70`); el agente la usa con `Config()` sin parámetros.

| Pieza | Elección |
|---|---|
| Chunking | Un chunk por artículo con ruta jerárquica y encabezado citable; artículos largos en partes (se reúnen al entregar); notas, preámbulos y anexos aparte; sentencias en ficha (tesis + resuelve) y ventanas de ~1.700 caracteres por sección. 2.210.629 chunks (1.909.717 son ventanas de sentencias) |
| Léxico | BM25 (bm25s) con raíces Snowball, sin quitar stopwords, ids normativos y sentencias normalizados (`src/knowledge/tokenization.py`) |
| Denso | Qwen3-Embedding-0.6B (dim 1024) + FAISS `IndexHNSWSQ` 8 bits (M=32, efConstruction=200, efSearch=256) |
| Lista de normas | BM25 y HNSW extra solo sobre normas (276.958 chunks), 50 candidatos cada uno: evita que las sentencias (~85 % del corpus) entierren códigos y Constitución |
| Fusión | Citas expresas de la pregunta + BM25 (100) + HNSW (100) + normas (50 + 50) → RRF k=60 |
| Reranker | bge-reranker-v2-m3 (fp16) sobre los 150 primeros de la fusión |
| Ajustes | Castigo por tipo (preámbulo 0,2; notas 0,15; ventana de sentencia 0,1; anexo 0,1; derogada 0,15), +0,1 a normas de prioridad alta, máximo 4 sentencias y 3 pasajes por documento, partes de un artículo reunidas |
| Sin casi duplicados | Un pasaje que no es artículo de norma y repite ≥70 % del texto de uno ya elegido (secuencias de 5 palabras) se salta y entra el siguiente distinto. En la muestra, 65 de 500 pasajes repetían a otro (sentencias que copian un párrafo, notas que transcriben la norma). Los artículos de norma nunca se saltan |
| Salida | 10 pasajes; todo orden se desempata por chunk_id (determinista) |

Descartados con datos: bge-m3 y e5-large-instruct (embedders), Qwen3-Reranker-0.6B (peor y 4,5× más lento), BM25 sin raíces, más candidatos sin más reranker, topes más estrictos de sentencias o de pasajes por documento, búsqueda por opción en cerradas (`por_opcion`: recall_docs 0,772, peor) y seguimiento de citas (`seguir_citas`: sin cambio); quedan en el código apagadas. Pasar 20 candidatos al reranker o 20 pasajes al LLM: descartado (menos recall, y el evaluador solo cuenta los 10 primeros pasajes como respaldo).

### Resultados de recuperación (corpus completo, 2,2 M chunks, `data/sample_50.jsonl`)

| Métrica @10 | Sin ajustes (`base`) | **Ganador** |
|---|---|---|
| recall_citas | 0,862 | **0,919** |
| recall_docs | 0,439 | **0,809** |
| MRR | 0,236 | **0,419** |
| nDCG | 0,314 | **0,561** |

- Por etapa (ganador): BM25 0,756 / 0,415 → denso 0,862 / 0,423 → RRF 0,898 / 0,744 → final 0,919 / 0,785 (recall_citas / recall_docs). El RRF con la lista de normas y la selección final (diversidad) son los que más suben recall_docs; el reranker mejora sobre todo el orden.
- Por formato (final, recall_citas / recall_docs): opción múltiple 0,962 / 0,808 (15 preguntas), semiabierta 0,965 / 0,819 (30), **abierta 0,5 / 0,5 (5)**. Las abiertas son preguntas de caso que no nombran la norma: le toca al reescritor de consultas del agente.
- **recall_docs es el techo de citas del agente**: el validador solo acepta citas cuyo documento esté entre los 10 pasajes.
- Tiempo por pregunta en la A40: ~1 s (reranker 0,66 s, BM25 0,19 s, denso 0,11 s, normas 0,04 s).
- **Portátil (RTX 3050 Ti, 4 GB): determinismo verificado, 50/50 preguntas con los mismos 10 pasajes en el mismo orden que la A40** y métricas idénticas. Configuración obligatoria: **embedder de la consulta en CPU, reranker en GPU** (`Recuperador(..., dispositivo="cuda", dispositivo_denso="cpu")`): **6,4 s por pregunta** (reranker 3,6 s, denso 1,9 s, BM25 0,6 s; carga inicial ~100 s). Con los dos modelos en la GPU, Windows desborda la memoria a la RAM y el reranker sube a 59 s. Se repite con `python -m evaluation.retrieval_benchmark.compare_machines --device cuda --device-denso cpu --nombre portatil_denso_cpu` (`results/maquina_portatil_denso_cpu.json`).

### Dónde están las comparaciones (para el informe)

En `evaluation/retrieval_benchmark/results/` (traídas del servidor, versionadas):
- `comparacion_banco_normas_fichas.md` — selección de modelos sobre el subcorpus normas + fichas (300.912 chunks): 3 embedders × BM25 con/sin raíces × 2 rerankers y sin reranker, más perfiles de ajuste.
- `comparacion.md` — todas las pruebas sobre el corpus completo, de `base` al ganador.
- `eval_todo__qwen3-emb-0.6b__bm25__bge-reranker-v2-m3__ganador_normas50.md` — el ganador por etapa, por formato y tiempos.
- `logs/diagnostico_fallos.log` (no versionado) — posición de los documentos que no llegaban al top-10; motivó la lista de normas. Se regenera con `python -m evaluation.retrieval_benchmark.diagnose_misses --eval <eval_*.json>`.

### Operación

```bash
python -m src.knowledge.chunking                                                  # corpus/md -> corpus/chunks
python -m src.knowledge.bm25_store --seleccion todo                               # y --seleccion normas
python -m src.knowledge.vector_store --modelo qwen3-emb-0.6b --seleccion todo --parte i --partes 4 --device cuda:i
python -m src.knowledge.vector_store --modelo qwen3-emb-0.6b --seleccion normas --subindice-de todo   # sin GPU
python -m evaluation.retrieval_benchmark.run_all --seleccion todo --stages evaluate,compare --embedders qwen3-emb-0.6b --bm25 con --rerankers bge-reranker-v2-m3 --perfiles ganador_normas50 --device cuda:0
python -m src.knowledge.verify_indices                                            # completitud y concordancia de los índices
```

La construcción pesada corre en el servidor (`ml-server03`, 4 A40, venv `~/envs/IA`; ver `SERVIDOR.md`), nunca en el PC. Los `vec_*.npy` (vectores por lote, 4,5 GB) solo están en el servidor y sirven para rearmar el HNSW.

---

## 6. Índice congelado y entregable 5 (zip)

`python -m src.knowledge.package_index` arma `T:\Proyectos\samu_enjoyer_corpus_indice.zip` (se sube a la nube con enlace de descarga libre por 30 días y va en la sección "Corpus e índice" del README). **Se descomprime en la raíz del repositorio**; todo queda bajo `corpus/`, donde el código lo busca:

```
Samu-Enjoyer/                                  <- descomprimir aquí
└── corpus/
    ├── LICENSE                                CC BY 4.0
    ├── LEEME.md                               contenido, uso, configuración y hashes
    ├── SHA256SUMS.txt
    ├── corpus_manifest.json                   manifiesto de descarga
    ├── auditoria_descarga.json
    ├── chunks/
    │   ├── chunks.sqlite                      corpus enriquecido: 2.210.629 pasajes con metadatos
    │   └── resumen.json
    └── indices/
        ├── bm25_todo/                         BM25 completo
        ├── bm25_normas/                       BM25 de normas
        ├── qwen3-emb-0.6b_todo/               hnsw.faiss + ids.json + info.json
        └── qwen3-emb-0.6b_normas/             hnsw.faiss + ids.json + info.json
```

Después: `python -m src.knowledge.verify_indices` debe terminar en `TODO CORRECTO`. El índice queda congelado al entregar: la verificación en vivo exige los mismos pasajes que en `submissions.jsonl`.

---

## 7. Agente — decisiones y pendientes

- **LLM recomendado:** Qwen3-8B GGUF Q4_K_M con llama.cpp (servidor local con API compatible), temperatura 0, top_k=1, semilla fija, sin modo de razonamiento, peticiones secuenciales. Mismo motor en la A40 (992 preguntas) y en el portátil (verificación en vivo). **Contexto de 32k** (`-c 32768`, el máximo nativo de Qwen3-8B) y presupuesto de 85.000 caracteres para los 10 pasajes en el prompt (`MAX_CHARS_PASAJES`), repartido de forma justa: los que caben van completos y solo se recortan los gigantes. En la muestra, 45/50 preguntas entran sin recortar nada y el prompt más grande (escritor o juez) es de 25.318 tokens; las 5 restantes traen anexos de 59k-310k tokens en un solo artículo. Con 16k y recorte fijo de 3.000 caracteres por pasaje, 8 preguntas fallaban por contexto. En el portátil el contexto de 32k ocupa ~4,7 GB más de RAM y leer prompts largos en CPU toma más tiempo. El juez es un modelo distinto del escritor, en su propio servidor: Gemma 4 E4B en Ollama (`JUDGE_MODEL=gemma4:e4b`, `JUDGE_BASE_URL=http://localhost:11434/v1`); llama.cpp ignora el campo `model`, así que con la URL del escritor juzgaría el mismo Qwen.
- **Cerradas (1/oct):** el prompt pide la `justificacion` **antes** de `respuesta_correcta`; con la letra primero el modelo elegía antes de razonar (pregunta 671: razonaba la C y respondía B; con el cambio acierta). **Modo de razonamiento de Qwen3 descartado:** no es replicable en el portátil (CPU, ~2 tokens/s: minutos por pregunta) y la verificación en vivo debe reproducir lo que generó la A40. Resultado en la muestra: 11/15 cerradas; de las 4 falladas, la 58 tiene la clave errónea ("Ley 1564 de 2002" no existe), la 128 pide un dato ("Fintech") que no está en ningún pasaje, la 528 necesita el valor del SMLMV (no está en los pasajes) y la 748 es de búsqueda (no trae el CPACA).
- **Citas en la entrega:** el escritor cita con IDs canónicos entre corchetes (los usan el validador y el juez), pero el evaluador oficial no reconoce ese formato. `LegalAgent.to_submission` los reescribe con `src/agent/citas.py`: `[codigo_general_proceso/art_42]` → "(artículo 42 del Código General del Proceso (Ley 1564 de 2012))", con el nombre del encabezado del pasaje, así que toda cita queda respaldada. Probado con los pasajes reales de las 50 preguntas: 401/410 reconocidas y respaldadas (las 9 restantes son sentencias `csj_` sin cita reconocible en su propio texto).
- **Fallas:** si el LLM no responde en `LLM_TIMEOUT` (300 s por defecto) la pregunta queda en **abstención** con aviso en stderr; nunca se entrega una respuesta simulada. Una corrida real sin índices se detiene con error; los pasajes y el escritor simulados solo se usan con `--mock`.
- **Portátil, 4 GB de GPU:** el reranker ocupa ~2,8 GB (el embedder va en CPU con `RAG_DEVICE_DENSO=cpu`, ver sección 8); Qwen3-8B Q4 (~5 GB) no cabe: el LLM va en CPU o con pocas capas en GPU (llama.cpp `-ngl` parcial).
- **Verificación en vivo (2-3 preguntas, ~10 min):** los pasajes ya son idénticos entre máquinas; las **normas citadas dependen del LLM** y CUDA (A40) vs CPU (portátil) pueden diferir aun con temperatura 0. Antes del sábado: correr las mismas 5 preguntas en ambas máquinas con el mismo GGUF y comparar normas citadas; si difieren, regenerar en la A40 con la misma configuración de llama.cpp que el portátil las preguntas que pida el jurado.
- **Pendientes:** conectar el agente al recuperador y correr `scripts/evaluate.py --split sample` para el reporte del viernes 2/oct 17:00; reescritor de consultas para abiertas; `CORPUS.md`; README con comando único y sección "Corpus e índice"; subir el zip; informe técnico (3 páginas).
- **Anomalías de datos conocidas (sin corregir):** `doc_id` `ley_09060_204a` (metadato mal leído en la conversión); sentencias de la CSJ con prefijo `csj_` se tratan como normas.
---

## 8. Cómo probar el agente (cualquier máquina del equipo)

1. **Dependencias** (Python 3.12; en GPU, primero torch con CUDA):
   ```bash
   pip install torch --index-url https://download.pytorch.org/whl/cu124
   pip install -r requirements.txt -r requirements-rag.txt -r requirements-agent.txt
   ```
2. **Índice:** descargar el zip del entregable 5 (sección 6), descomprimirlo en la raíz del repo y comprobar con `python -m src.knowledge.verify_indices` (debe terminar en `TODO CORRECTO`). Pesa ~15 GB descomprimido.
3. **Configuración por máquina:** copiar `.env.example` como `.env` (no se versiona) y ajustar:
   - `LLM_BASE_URL` del servidor local del LLM (por defecto `http://localhost:8000/v1`).
   - **`RAG_DEVICE_DENSO=cpu` en GPUs de ≤ 8 GB** (portátiles): el embedder de la consulta va en CPU y el reranker en GPU. Sin esto, en 4 GB cada búsqueda tarda ~60 s en vez de ~6 s. Los pasajes salen idénticos. En la A40 se deja vacío.
4. **LLM local** (escritor: Qwen3-8B GGUF Q4_K_M con llama.cpp; el juez, Gemma 4 E4B, va aparte en Ollama: `ollama pull gemma4:e4b`):
   ```bash
   llama-server -m Qwen3-8B-Q4_K_M.gguf --host 127.0.0.1 --port 8010 -c 32768 -np 1 --jinja --temp 0 --top-k 1 --seed 42 -ngl 99
   ```
   `-ngl 99` pone todas las capas en GPU (A40); en un portátil, `-ngl 0` (todo en CPU) o unas pocas capas si sobra memoria después del reranker. `--jinja` es necesario para que funcione `enable_thinking: false` (sin bloque `<think>`).
5. **Correr y evaluar:**
   ```bash
   python -m src.agent.batch_runner --mock --limite 3 --salida /tmp/prueba.jsonl     # humo: sin índices ni LLM
   python -m src.agent.batch_runner --limite 3 --salida entregables/prueba.jsonl     # real, 3 preguntas
   python -m src.agent.batch_runner --juez --salida entregables/submissions.jsonl    # las 50 con juez (máx. 2 ciclos)
   python scripts/evaluate.py --submission entregables/submissions.jsonl --split sample
   ```
   Una corrida real sin índices se detiene con error (no usa pasajes simulados); si el LLM no responde, esa pregunta queda en abstención y se avisa en el log.
