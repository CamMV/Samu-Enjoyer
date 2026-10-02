# Hackathon IA Week 2026 — Sistema RAG de Derecho Colombiano

Sistema de respuesta a preguntas jurídicas colombianas con modelos abiertos pequeños (Qwen3-8B, Qwen3-Embedding-0.6B, bge-reranker-v2-m3).
El valor del reto reside en la fidelidad jurídica y en el corpus: **cada respuesta debe citar normas respaldadas en los pasajes recuperados**. Lo que no esté en el corpus no se puede inventar ni citar.

---

## 0. ESTADO ACTUAL (2/oct/2026, madrugada) — leer primero

- **Fechas:** viernes 2/oct 17:00 reporte de avance; sábado 3/oct corrida de las 992 preguntas en la A40, entrega del repositorio y verificación en vivo (2-3 preguntas en el portátil).
- **Rama de trabajo:** `pruebas-recuperacion`. Código de la entrega: commit `59ef255` (siglas activadas; limpieza de instrucciones medida y apagada).
- **Configuración de la entrega = v14 + fuentes ampliadas:** recuperación `Config()` por defecto (sección 5, con `siglas=True`) + agente sin juez (código de v8sj, `a8a2325`) + respaldo de letra en cerradas + `cache_prompt: false` + lista de fuentes ampliada (`FUENTES_AMPLIADAS`, activada). Comando: `python -m src.agent.batch_runner --salida submissions.jsonl` (sin `--juez`). `LARGO_COMPLEJIDAD` sigue apagado (pendiente de RAGAS).
- **Métricas deterministas en `sample_50` (A40, `scripts/evaluate.py` sin `--ragas`):** v14: cerradas **13/15** (0,867; referencia 0,905; 17,33 pts), citas 16,73, abstención 8,84: 42,90 / 50. **Con fuentes ampliadas (v16): citas 18,37 (45 de 49 cuerpos), abstención 9,07: 44,77 / 50.** RAGAS medido por última vez en v8sj: 0,485 (referencia 0,451, ~14,6 pts) → ~59,3/80. Fallan la 128 (el corpus no respalda "Fintech" en leasing) y la 748 (el art. 137 del CPACA no llega al top-10); llegar a 14/15 sin sobreajustar no se logró (ver sección 7). Lo que queda en citación y abstención (60, 247, 679 y la SU-16 de 2020 en la 453) son documentos que la búsqueda no trae.
- **Reproducibilidad (clave para comparar y para la verificación en vivo):** con `cache_prompt: false` dos corridas dan respuestas idénticas, incluso entre las dos GPU de la A40 (10/10). Antes de eso, el ruido entre corridas era de ~4 puntos sobre 50: **las comparaciones anteriores al 2/oct (v8sj-v12) están dentro del ruido**. Toda comparación nueva debe hacerse con el código actual y en la A40.
- **PC/portátil ≠ A40 en el LLM:** con los mismos pasajes, la 308 salió distinta en el PC (Qwen3-8B con `-ngl 14`, parte en CPU). Antes del sábado, comparar 3-5 preguntas entre el portátil y la A40 (sección 7, "Verificación en vivo"). Los experimentos de prompts en el PC son lentos (3-17 min por cerrada con 16 GB de RAM) y no se trasladan a la A40.
- **Reglas de trabajo acordadas:** el agente no accede a internet y responde solo con nuestro corpus; nada de modelos o APIs cerrados en el sistema. RAGAS (juez externo por OpenRouter, solo para evaluar; llave en `scripts/.env`, no versionada, nunca copiarla en archivos ni mensajes) tiene saldo fijo: preguntar antes de cada evaluación y no re-evaluar versiones viejas. No sobreajustar a las 50 de muestra: solo reglas generales, medidas en las 50 completas. Las métricas deterministas (`scripts/evaluate.py` sin `--ragas`) son gratis.
- **Pendientes:** README con el comando único y la sección "Corpus e índice"; subir el zip (4,59 GB; **no cambia**: las siglas solo cambian el texto de la consulta, no el índice) y poner el enlace en README, `CORPUS.md` y `corpus_manifest.json`; UI (sábado); video; informe técnico (3 páginas); corrida de las 992 con v14; prueba portátil vs A40.

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
- **Modelo:** escritor Qwen3-8B con `Temperature = 0` (el juez Gemma 4 E4B quedó fuera de la entrega, ver "LLM as Judge"). Modelos abiertos en todo el pipeline.
- **Entrada y Formatos:** Preguntas de `sample_50.jsonl` o UI. Detección de formato:
  - *Cerradas (opción múltiple):* Búsqueda con pregunta + opciones A, B, C, D (determinista, sin LLM).
  - *Abiertas / semiabiertas:* Query rewriter con términos jurídicos y normas candidatas.
- **Top-10 Pasajes:** Toda redacción se hace **exclusivamente con los 10 pasajes** entregados por la recuperación híbrida (BM25 + HNSW con Qwen3-Embedding-0.6B + RRF + bge-reranker-v2-m3; ver sección 5).
- **Validación Determinista de Fuentes (Sin LLM):** 
  - Toda cita en la respuesta debe mapearse a un ID canónico (`<doc_id>/art_<N>`, ej. `codigo_general_proceso/art_42`).
  - Si una cita no existe en los 10 pasajes recuperados, se suprime o se activa `abstencion: true`.
  - **Subagente de búsqueda de citas** (`src/agent/tools/citation_search_tool.py`, nodo `buscar_citas`, sin LLM): **por defecto solo suprime** del borrador las citas fuera de los pasajes. Con `CITAS_AGREGAR_PASAJES=1` busca la cita en `chunks.sqlite` y, si existe y está vigente, agrega su pasaje (sustituye al último no citado; nunca más de 10). **Decisión (1/oct): apagado**, porque la afirmación no se redactó con ese texto y los pasajes dejarían de depender solo de la búsqueda determinista que se reproduce en la verificación en vivo. El informe queda en la llave `citas` de `<salida>.juez.jsonl`.
- **LLM as Judge — DESCARTADO para la entrega (1/oct, v8 contra v8sj, mismo código):** sin juez, RAGAS 0,485 contra 0,469 (en pares, el juez gana en 7 preguntas y pierde en 12), cerradas 13/15 contra 12/15 (en la 58 rechazó un borrador correcto y el segundo ciclo lo dañó), total 57,5 contra 55,4 de 80, y 8,9 s contra 15,8 s por pregunta en la A40. Sin juez, además, los pasajes dependen solo de la búsqueda determinista (sin segundo ciclo), lo que simplifica la verificación en vivo. El código sigue disponible con `--juez` (apagado por defecto). Lo que hacía: evaluar si responde la sub-tarea, si cada afirmación tiene pasaje que la soporte y la coherencia del área jurídica.
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

Arquitectura híbrida BM25 + HNSW → RRF → reranker. Configuración ganadora = valores por defecto de `Config()` en `src/knowledge/hybrid_search.py` (perfil `ganador_dedup70` + `bm25_solo_cerradas` + `smlmv` + `lideres` + `siglas`; en el banco de pruebas, perfil `ganador_siglas`); el agente la usa con `Config()` sin parámetros. **El índice está congelado** (no cambia desde el zip); lo agregado el 2/oct (`siglas`) solo transforma el texto de la consulta. `config_de` mide los perfiles viejos con `siglas=False` para que sigan reproduciéndose.

| Pieza | Elección |
|---|---|
| Chunking | Un chunk por artículo con ruta jerárquica y encabezado citable; artículos largos en partes (se reúnen al entregar); notas, preámbulos y anexos aparte; sentencias en ficha (tesis + resuelve) y ventanas de ~1.700 caracteres por sección. 2.210.629 chunks (1.909.717 son ventanas de sentencias) |
| Léxico | BM25 (bm25s) con raíces Snowball, sin quitar stopwords, ids normativos y sentencias normalizados (`src/knowledge/tokenization.py`) |
| Denso | Qwen3-Embedding-0.6B (dim 1024) + FAISS `IndexHNSWSQ` 8 bits (M=32, efConstruction=200, efSearch=256) |
| Lista de normas | BM25 y HNSW extra solo sobre normas (276.958 chunks), 50 candidatos cada uno: evita que las sentencias (~85 % del corpus) entierren códigos y Constitución |
| Buscadores por formato | **Cerradas:** BM25 + HNSW (las opciones traen términos exactos: "Ley 472", "falsa motivación"). **Semiabiertas y abiertas:** solo HNSW (en lenguaje natural BM25 mete pasajes que comparten palabras pero no tema). Determinista: el formato es un dato de la pregunta (`bm25_solo_cerradas`) |
| Fusión | Citas expresas de la pregunta + BM25 (100) + HNSW (100) + normas (50 + 50) → RRF k=60 |
| Reranker | bge-reranker-v2-m3 (fp16) sobre los 150 primeros de la fusión |
| Ajustes | Castigo por tipo (preámbulo 0,2; notas 0,15; ventana de sentencia 0,1; anexo 0,1; derogada 0,15), +0,1 a normas de prioridad alta, máximo 4 sentencias y 3 pasajes por documento, partes de un artículo reunidas |
| Sin casi duplicados | Un pasaje que no es artículo de norma y repite ≥70 % del texto de uno ya elegido (secuencias de 5 palabras) se salta y entra el siguiente distinto. En la muestra, 65 de 500 pasajes repetían a otro (sentencias que copian un párrafo, notas que transcriben la norma). Los artículos de norma nunca se saltan |
| Montos en pesos | Si la pregunta trae un monto en pesos (≥ $1.000.000), entra con lugar asegurado el artículo del decreto más reciente que fija el salario mínimo (hoy `decreto_1572_2024/art_1`, $1.423.500 para 2025): los umbrales legales están en SMLMV (`smlmv`). En la muestra solo cambia la 528; métricas iguales |
| Siglas | Antes de buscar, cada sigla jurídica de la consulta (en mayúsculas, palabra completa) se acompaña de su nombre completo: "SIC" → "SIC (Superintendencia de Industria y Comercio)". Diccionario fijo de ~45 siglas sin ambigüedad en `src/knowledge/siglas.py` (DIAN, ICBF, EPS, CGP, CPACA, CST, SMLMV…); las citas expresas se detectan sobre la consulta original (`siglas`, 2/oct). Métricas idénticas en las 50; solo cambian los pasajes de la 58 (entra el art. 24 del CGP) y la 679 |
| Salida | 10 pasajes; todo orden se desempata por chunk_id (determinista) |

Descartados con datos: bge-m3 y e5-large-instruct (embedders), Qwen3-Reranker-0.6B (peor y 4,5× más lento), BM25 sin raíces, más candidatos sin más reranker, topes más estrictos de sentencias o de pasajes por documento, búsqueda por opción en cerradas (`por_opcion`: recall_docs 0,772, peor) y seguimiento de citas (`seguir_citas`: sin cambio); quedan en el código apagadas. También apagadas (1/oct, medidas sobre las 50): búsqueda dentro de las normas citadas sin artículo (`en_citadas`) y consulta con solo el texto de las opciones (`solo_opciones`): el top-10 no cambia, el reranker decide; reranker por opción (`rerank_opciones`): mete "Fintech" en la 128, pero cerradas recall_docs 0,808 → 0,731 y 5,5× más lento; mezcla del puntaje del reranker con el RRF (`peso_fusion` 0,1): recall_citas 0,931 pero recall_docs 0,797 (cerradas 0,769); cupo para el 1.º de cada buscador (`lideres`): cerradas recall_docs 0,692; una ventana por sección de sentencia (`una_ventana`): métricas iguales. Solo BM25 (0,898 / 0,720) y solo HNSW (0,919 / 0,846) por separado: ninguno gana en todos los formatos. Pasar 20 candidatos al reranker o 20 pasajes al LLM: descartado (menos recall, y el evaluador solo cuenta los 10 primeros pasajes como respaldo).

### Resultados de recuperación (corpus completo, 2,2 M chunks, `data/sample_50.jsonl`)

| Métrica @10 | Sin ajustes (`base`) | **Ganador** |
|---|---|---|
| recall_citas | 0,862 | **0,931** |
| recall_docs | 0,439 | **0,858** |
| MRR | 0,236 | **0,423** |
| nDCG | 0,314 | **0,577** |

- Por etapa (ganador): BM25 0,756 / 0,415 → denso 0,862 / 0,423 → RRF 0,898 / 0,744 → final 0,919 / 0,785 (recall_citas / recall_docs). El RRF con la lista de normas y la selección final (diversidad) son los que más suben recall_docs; el reranker mejora sobre todo el orden.
- Con BM25 en todos los formatos (ganador hasta el 1/oct): 0,919 / 0,809 / MRR 0,419 / nDCG 0,561; las cifras por etapa de arriba son de esa configuración.
- Por formato (final, recall_citas / recall_docs): opción múltiple 0,962 / 0,808 (15 preguntas), semiabierta 0,986 / 0,944 (30; 0,965 / 0,861 con BM25), **abierta 0,5 / 0,5 (5)**. Las abiertas son preguntas de caso que no nombran la norma: le toca al reescritor de consultas del agente.
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
- **Cerradas (1/oct):** el prompt pide la `justificacion` **antes** de `respuesta_correcta`; con la letra primero el modelo elegía antes de razonar (pregunta 671: razonaba la C y respondía B; con el cambio acierta). **Modo de razonamiento de Qwen3 descartado:** no es replicable en el portátil (CPU, ~2 tokens/s: minutos por pregunta) y la verificación en vivo debe reproducir lo que generó la A40. Resultado en la muestra (v3): 11/15 cerradas; falladas 58, 128, 528 y 748. La 58 tiene la clave errónea ("Ley 1564 de 2002": el CGP es de 2012; el prompt ahora pide reconocer la norma por su número si el año no coincide); la 128 queda **sin resolver a propósito**: el único pasaje con "Fintech" (`decreto_1068_2025/art_2.26.3`, 1.º en BM25 de normas, puesto 48 tras el reranker) no trata de leasing, sino de los proveedores de crédito de un programa de Bancóldex (junto a cooperativas y fundaciones); el reranker acierta al bajarlo y forzarlo sería sobreajustar; la 528 necesita el valor del SMLMV (ahora entra el decreto con `smlmv` y el prompt pide convertir el monto); la 748 necesita el art. 137 del CPACA (falsa motivación), que no llega a los 150 candidatos.
- **v4 (1/oct, juez Qwen): 39,60** (v3 35,99): cerradas 11/15, citas 0,828 (16,56), abstención 8,37. Con juez Llama-3.1-8B y voto en cerradas (v4l): 36,63 (forzó 6 abstenciones); descartado. En v4 la 528 tenía el art. 25 del CGP y el decreto del salario mínimo, calculó bien 21,07 smlmv y aun así eligió "mayor cuantía"; la 58 concluyó "Ley 1564 de 2012" y eligió la Ley 906. El problema es que la letra no sale de su propio razonamiento. Dos piezas en `writer_tool.py`, a medir:
  - **Calculadora de montos** (`datos_calculados`, sin LLM): si la pregunta trae pesos y un pasaje fija el salario mínimo, el prompt recibe el monto en salarios mínimos y si EXCEDE o NO EXCEDE cada umbral en salarios mínimos que aparezca en los pasajes.
  - **Elección de la letra en un paso aparte** (`con_letra_de_la_justificacion`, `ELEGIR_LETRA=1` por defecto): un segundo llamado al mismo Qwen lee solo el razonamiento (sin las frases que anuncian una letra) y devuelve la opción que respalda, acotada por gramática a las letras válidas. Si difiere, se corrige la letra y la frase final de la justificación; si el llamado falla, queda el borrador.
  - **Las cerradas nunca se abstienen** (ni por el juez en `graph.finalizar` ni por el escritor si dio una letra válida): la abstención deja `respuesta_correcta: None`, que el esquema rechaza, y vale menos que responder (acierto 1, abstención 0,5, error 0; y 0 en exactitud). En la primera prueba de las 15 cerradas, la 58 pasó a la letra correcta (D → A) y la abstención forzada por el juez la anuló.
- **CONFIGURACIÓN DE LA ENTREGA (2/oct; luego + `cache_prompt: false` + siglas = v14, ver abajo): el código de v8sj (commit `a8a2325`), sin juez, más un respaldo cuando una cerrada queda sin letra** (la opción con más respaldo léxico en los pasajes; no cambia ningún prompt). Todo lo probado después (v9-v11: cupo de sentencia citada, largo por complejidad, sí/no, variantes de razonamiento en cerradas, expansión de consulta) se retiró del código: v11 dio 40,29/50 contra 42,90 de v8sj en las métricas deterministas. Una sola frase agregada al prompt base volteó la 58 con los mismos pasajes: las cerradas en el límite son inestables, y en la máquina final pueden salir distintas de todos modos. Cada experimento queda en el historial de git.
- **Determinismo del LLM (2/oct) — `cache_prompt: false`.** Con el código de v8sj, los mismos pasajes (50/50) y el mismo GGUF y banderas, una segunda corrida (v12) dio **0/50 respuestas idénticas** y 38,96/50 contra 42,90. Causa: llama-server reutiliza por defecto el prefijo común con la petición anterior (caché de prompts) y la salida dependía de qué pregunta se procesó antes (además, v8sj corrió en la GPU 1 y v12 en la GPU 0). Ahora cada llamada lleva `cache_prompt: false` (escritor y juez). Consecuencia para leer las comparaciones: **sin esto, el ruido entre corridas era de ~4 puntos sobre 50**, así que las diferencias de v9-v11 frente a v8sj estaban dentro del ruido. Verificar que dos corridas den lo mismo antes de comparar versiones.
- **v13 y v14 (2/oct), ya reproducibles** (dos corridas de 10 preguntas, una en cada GPU: 10/10 idénticas). **v13** (código de la entrega, sin siglas): cerradas 12/15 (falla 58, 128, 748), citas 16,73, abstención 8,60: **41,33/50**. La 58 concluía "Ley 446 de 1998" (no es opción) y quedaba la C; en v8sj había acertado con un razonamiento errado ("el CPC está contenido en la Ley 1564"): era ruido de la caché. Faltaba el art. 24 del CGP, que no llegaba porque la pregunta dice "SIC" y la norma "Superintendencia de Industria y Comercio". **v14 = v13 + siglas: cerradas 13/15 (17,33), citas 16,73, abstención 8,84: 42,90/50**; la 58 responde A citando el art. 24. **Configuración de la entrega.** Quedan la 128 (el corpus no respalda la D) y la 748 (falta el art. 137 del CPACA).
- **Fuentes ampliadas (2/oct) — INCLUIDO** (`FUENTES_AMPLIADAS`, `src/agent/citas.py`): el evaluador compara citas por cuerpo (norma o sentencia, sin artículo), da media nota a una cita correcta sin respaldo y no castiga las citas de más con respaldo; solo castiga las incorrectas sin respaldo. De los 8 cuerpos de referencia que faltaban en v14, 4 estaban en los pasajes: una sentencia de un pasaje (453; la lista solo traía normas) y leyes o códigos que el texto de un pasaje menciona (1073: CST y Constitución; 748: CPACA). Tras la lista de normas se agregan "Sentencias de los pasajes consultados" y "Leyes y códigos mencionados en los pasajes consultados" (solo leyes, códigos y Constitución: con decretos, resoluciones y sentencias mencionadas la lista se triplicaba sin ganar nada; las sentencias `csj_` se omiten porque su encabezado no es una cita reconocible). v16 (A40): citas 16,73 → 18,37, abstención 8,84 → 9,07, 0 citas sin respaldo; no toca el LLM ni el texto que va a RAGAS. Campo de fundamento: mediana de ~97 a ~149 palabras.
- **Largo de semiabiertas según complejidad (2/oct) — PENDIENTE DE RAGAS** (`LARGO_COMPLEJIDAD=1`, apagado): alta 5 oraciones ≤120 palabras, media 4 ≤80 (medianas de la esperada: 116, 66 y 32 palabras; nuestras respuestas, ~45 en todas). En v16 solo cambian esas 20 semiabiertas (cerradas, bajas y abiertas idénticas a v14: el LLM es reproducible). Indicador léxico gratis (`F1` y cobertura de palabras contra la esperada; correlación con RAGAS por ítem 0,6-0,75): cobertura media 0,282 → 0,368 y alta 0,246 → 0,269, pero F1 igual (0,272 y 0,300 → 0,303): no concluyente. Decidir con RAGAS sobre v14 y v16.
- **BM25 de normas en texto libre (2/oct) — DESCARTADO** (`bm25_normas_libre`, apagado; perfil `ganador_normas_libre`): semiabiertas 0,986 / 0,944 → 0,951 / 0,847; abiertas igual (no trae la Ley 472 a la 247 ni la 1581 a la 679).
- **Sin instrucciones de examen en la consulta (2/oct) — PROBADO, NO INCLUIDO** (`sin_instrucciones`, apagado): la 748 empieza con "Habiendo hecho la lectura previa de… lea con atención cada pregunta y responda la siguiente pregunta. Pregunta jurídica:" y esas palabras traían a BM25 artículos de interrogatorio de parte. Sin ellas, el art. 137 del CPACA pasa del puesto 258 al 35 en BM25 de normas, pero el reranker no lo sube al top-10; métricas de búsqueda idénticas y el agente pasa de D a C (v15: 42,90/50, igual que v14). En la muestra solo la 748 tiene ese formato.
- **v8sj (1/oct):** cerradas 13/15 (17,33), citación 0,837 (16,73), abstención 8,84, RAGAS 0,485 (14,56; 35/35 con veredicto, medición propia con 600 s de límite): **~57,5 / 80** (v2: 47,1). Supera la referencia de RAGAS (0,485 contra 0,451); en cerradas queda en 0,867 contra 0,905 (la 128 y la 748 no tienen respaldo en el corpus).
- **RAGAS (1/oct, juez oficial `z-ai/glm-5.3-flash`, 35 ítems).** `answer_correctness` = 0,75 × F1 de afirmaciones (las que sobran cuentan contra, aunque sean ciertas) + 0,25 × parecido semántico. v2: 0,429; v6: 0,441 oficial, pero con 4-5 ítems sin veredicto por timeout del juez (180 s por llamada; cuentan 0). Con 600 s de límite (medición propia), las semiabiertas de v6 dan 0,523 y las abiertas 0,29. Lo que se cambió:
  - Semiabiertas: `respuesta` de 3 oraciones, la primera responde directo según la `sub_tarea` del catálogo oficial (`guia_primera_oracion` en `writer_tool.py`; verdadero/falso empieza con "La afirmación es…"); las citas salen del texto y pasan a `referencia_legal` (`respuesta_concisa` en `citas.py`). Medido sobre v2 sin regenerar: 0,438 → 0,462.
  - Abiertas: campos en texto corrido con tope de oraciones y palabras (`abierta_concisa`, ~280 palabras); las de ~500 palabras no alcanzaban veredicto. Con 600 s, largas 0,291 y cortas 0,289: el recorte no cuesta puntaje y evita timeouts.
  - Sin meta-texto ("según los pasajes…"): regla en el prompt y limpieza determinista de respaldo (`sin_meta_texto`), y sin encabezados de sección de sentencias (`sin_encabezados`).
- **Expansión de consulta con el LLM (1/oct) — DESCARTADA (retirada del código; commit `3d91b1c`):** Qwen nombraba figuras y normas candidatas para buscar (`src/agent/tools/expansion_tool.py`, apagada con `EXPANDIR_CONSULTA=0` por defecto). Sobre las 35 de texto libre bajó recall_docs 0,881 → 0,798 (0,833 sin BM25) y no mejoró ninguna pregunta: inventa normas que no aplican ("Código Tributario art. 245") y esos pasajes desplazan a los correctos. Además, haría depender los pasajes de la salida del LLM (riesgo en la verificación en vivo).
- **Sentencia citada en la pregunta (1/oct) — PROBADA, NO INCLUIDA:** entran fijas su ficha y sus 2 secciones más pertinentes para la pregunta (`cupo_sentencia`, BM25 y denso dentro de la sentencia). En v8sj, las preguntas sobre una sentencia nombrada con 3 pasajes de ella puntuaban 0,67-0,73 en RAGAS y las que solo tenían la ficha, 0,21 (190: los hechos salieron de la T-256 de 2024 en vez de la de 2025). El prompt pide además responder con la sentencia nombrada, verificando número y año (solo sentencias: con normas, en v9 hizo descartar la opción correcta de la 58, que trae el año errado).
- **Largo según la complejidad (1/oct) — PROBADO, NO INCLUIDO:** semiabiertas de complejidad alta con 5 oraciones (máximo 130 palabras); baja y media, 3. En la muestra, la esperada de complejidad alta tiene una mediana de 116 palabras y 5 oraciones; baja, 32; media, 64.
- **Variantes de razonamiento en cerradas (2/oct) — retiradas; queda el prompt de v8 (13/15).** Sobre las 15 cerradas: solo análisis por opción 11/15 (resolvió 128 y 748, pero perdió 58, 308, 528 y 647); análisis + regla estricta de listas 11/15; solo regla estricta 12/15. Cada cambio pequeño de prompt voltea 3-4 respuestas en ambas direcciones: con 15 ítems no se distingue una mejora real del azar, y la mayoría de votos entre variantes también da 13/15. Elegir la variante que diera 14 sería sobreajustar a estas 15. Se agregó un respaldo: si una cerrada queda sin letra (pasó en una variante), se elige la opción con más respaldo léxico en los pasajes en vez de entregarla vacía.
- **Razonamiento estructurado en cerradas (2/oct) — RETIRADO:** con `analisis_opciones` (para cada letra, qué dicen los pasajes de cada elemento) y la regla "si más de una tiene respaldo, la más completa", las 15 cerradas dieron 12/15: la 128 pasó de B a A (la lista más larga, aunque "asociaciones" no tiene respaldo) y se perdió la 617. La regla de la más completa se quitó (empuja a las opciones largas); el análisis solo queda para medirlo aparte. `analisis_opciones` no va a la entrega (`salida.normalizar` lo descarta) y el verificador de letra lo recibe con el texto de cada opción, no con su letra. Motivo: en la 128 el pasaje con "Fintech" estaba en el top-10 y la justificación libre no lo revisaba.
- **Semiabiertas de sí o no y largo por complejidad (1/oct) — PROBADO, NO INCLUIDO:** si la pregunta tiene forma de sí o no ("¿Puede…?", "¿Procede…?", "¿Existe…?"), la respuesta empieza con "Sí" o "No" (en v8sj y v9, 0,53 cuando coincidía con la esperada contra 0,21 cuando no); complejidad media con 4 oraciones (≤90 palabras): las respuestas con menos del 60 % de las palabras de la esperada promediaban 0,42 y las de largo parecido, 0,55. Análisis hecho sobre los puntajes por pregunta ya medidos, sin nuevas llamadas al juez.
- **Cerradas con opciones que son listas (1/oct) — QUITADA:** una regla de prompt para elegir la lista más completa con todos sus elementos respaldados no cambió la 128 (siguió en B) en v9; sin beneficio, solo agregaba riesgo en el test.
- **v9 (1/oct, cupo de sentencia citada, largo según complejidad, reglas nuevas):** RAGAS oficial 0,4526 (v8sj 0,4551, dentro del ruido del juez), cerradas 12/15 (la regla "verifica número y año" aplicada a normas rompió la 58; corregida a solo sentencias), citación 15,92. No supera a v8sj; se conservan el cupo de sentencia (corrigió la 190 sin cambiar la búsqueda en otras) y el largo para complejidad alta (0,357 → 0,388). Con 35 ítems y un juez externo que varía entre corridas, solo se aceptan cambios con evidencia clara o reglas generales neutras: RAGAS se usa con moderación (cada evaluación cuesta ~$0,07 de un saldo fijo de $20).
- **Cerradas, 1.º de BM25 de normas fijo (1/oct):** entra al top-10 aunque el reranker lo baje (`lideres=1`, `lideres_listas=("bm25_normas",)`, solo cerradas). Búsqueda idéntica al ganador (0,962 / 0,808) y entra el pasaje de "Fintech" en la 128; falta medir con el agente si sube la exactitud. Con el 1.º del HNSW (o de las 4 listas) recall_docs baja a 0,692: descartado.
- **Normas de los pasajes consultados (1/oct):** `to_submission` agrega al final de la `justificacion` (cerradas) y de `referencia_legal` (semiabiertas) la lista de normas (no sentencias) de los 10 pasajes, con el nombre de su encabezado (`src/agent/citas.py`, `con_normas_consultadas`). Son el fundamento consultado, quedan respaldadas y salen de la recuperación determinista (la verificación en vivo las reproduce). Las abiertas no se tocan: todos sus campos van a RAGAS. Recalculado sobre v2: citas 12,24 → 14,69 y abstención 7,33 → 7,79 (+2,9 pts), 0 citas sin respaldo.
- **Citas en la entrega:** el escritor cita con IDs canónicos entre corchetes (los usan el validador y el juez), pero el evaluador oficial no reconoce ese formato. `LegalAgent.to_submission` los reescribe con `src/agent/citas.py`: `[codigo_general_proceso/art_42]` → "(artículo 42 del Código General del Proceso (Ley 1564 de 2012))", con el nombre del encabezado del pasaje, así que toda cita queda respaldada. Probado con los pasajes reales de las 50 preguntas: 401/410 reconocidas y respaldadas (las 9 restantes son sentencias `csj_` sin cita reconocible en su propio texto).
- **Fallas:** si el LLM no responde en `LLM_TIMEOUT` (300 s por defecto) la pregunta queda en **abstención** con aviso en stderr; nunca se entrega una respuesta simulada. Una corrida real sin índices se detiene con error; los pasajes y el escritor simulados solo se usan con `--mock`.
- **Portátil, 4 GB de GPU:** el reranker ocupa ~2,8 GB (el embedder va en CPU con `RAG_DEVICE_DENSO=cpu`, ver sección 8); Qwen3-8B Q4 (~5 GB) no cabe: el LLM va en CPU o con pocas capas en GPU (llama.cpp `-ngl` parcial).
- **Verificación en vivo (2-3 preguntas, ~10 min):** los pasajes ya son idénticos entre máquinas; las **normas citadas dependen del LLM** y CUDA (A40) vs CPU (portátil) pueden diferir aun con temperatura 0. Antes del sábado: correr las mismas 5 preguntas en ambas máquinas con el mismo GGUF y comparar normas citadas; si difieren, regenerar en la A40 con la misma configuración de llama.cpp que el portátil las preguntas que pida el jurado. **Indicio (2/oct):** en el PC de Santiago (Qwen3-8B Q4_K_M, `-ngl 14`, 16 GB de RAM), con los mismos pasajes, la 308 dio C (la A40 acierta la A); el resto de las cerradas comparadas (51, 58, 60, 128, 290, 352) coincidió. El código de esa prueba era el de las variantes (`6fd8afc`), no idéntico al de la entrega, así que falta la prueba limpia.
- **Pendientes:** ver sección 0.
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
4. **LLM local** (escritor: Qwen3-8B GGUF Q4_K_M con llama.cpp; la entrega no usa juez; solo con `--juez` hace falta Gemma 4 E4B en Ollama: `ollama pull gemma4:e4b`):
   ```bash
   llama-server -m Qwen3-8B-Q4_K_M.gguf --host 127.0.0.1 --port 8010 -c 32768 -np 1 --jinja --temp 0 --top-k 1 --seed 42 -ngl 99
   ```
   `-ngl 99` pone todas las capas en GPU (A40); en un portátil, `-ngl 0` (todo en CPU) o unas pocas capas si sobra memoria después del reranker. `--jinja` es necesario para que funcione `enable_thinking: false` (sin bloque `<think>`).
5. **Correr y evaluar:**
   ```bash
   python -m src.agent.batch_runner --mock --limite 3 --salida /tmp/prueba.jsonl     # humo: sin índices ni LLM
   python -m src.agent.batch_runner --limite 3 --salida entregables/prueba.jsonl     # real, 3 preguntas
   python -m src.agent.batch_runner --salida submissions.jsonl                     # las 50 (configuración de la entrega, sin juez)
   python scripts/evaluate.py --submission entregables/submissions.jsonl --split sample
   ```
   Una corrida real sin índices se detiene con error (no usa pasajes simulados); si el LLM no responde, esa pregunta queda en abstención y se avisa en el log.
