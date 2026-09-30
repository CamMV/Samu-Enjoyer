# Hackathon IA Week 2026 — Sistema RAG de Derecho Colombiano

Sistema de respuesta a preguntas jurídicas colombianas con modelos abiertos pequeños (Qwen3-8B, bge-m3, bge-reranker-v2-m3).
El valor del reto reside en la fidelidad jurídica y en el corpus: **cada respuesta debe citar normas respaldadas en los pasajes recuperados**. Lo que no esté en el corpus no se puede inventar ni citar.

---

## 1. Reglas y Documentación de Referencia

Se encuentra un enlace simbólico a la carpeta de instrucciones llamada `docs_reto/`
- **Enunciado y lineamientos:** `docs_reto/enunciado.pdf` 
- **Arquitectura de referencia:** `docs_reto/arquitecturas_hackathon_local.html` 
- **Esquemas JSON esperados:** carpetas `docs_reto/schema/` y ejemplos en `docs_reto/Ejemplo de entrega/` / `docs_reto/entregables/`.
- **Datos y banco de prueba:** `data/sample_50.jsonl` y `data/corpus_targets.json` (actualizadas en la raíz)
- **Formato de entrega:** Generación estricta de `submissions.jsonl` según el schema oficial.

---

## 2. Frente Agente RAG (Orquestador, Escritor y Juez)

### Restricciones y Reglas de Respuesta
- **Modelo:** Qwen3-8B con `Temperature = 0`. Modelos abiertos en todo el pipeline (incluyendo el Juez).
- **Entrada y Formatos:** Preguntas de `sample_50.jsonl` o UI. Detección de formato:
  - *Cerradas (opción múltiple):* Búsqueda con pregunta + opciones A, B, C, D (determinista, sin LLM).
  - *Abiertas / semiabiertas:* Query rewriter con términos jurídicos y normas candidatas.
- **Top-10 Pasajes:** Toda redacción se hace **exclusivamente con los 10 pasajes** entregados por la recuperación híbrida (BM25 + densa bge-m3 + RRF + Reranker).
- **Validación Determinista de Fuentes (Sin LLM):** 
  - Toda cita en la respuesta debe mapearse a un ID canónico (`<doc_id>/art_<N>`, ej. `ley_1564_2012/art_42`).
  - Si una cita no existe en los 10 pasajes recuperados, se suprime o se activa `abstencion: true`.
- **LLM as Judge:** Evalúa si responde la sub-tarea, si cada afirmación tiene pasaje que la soporte y la coherencia del área jurídica.
- **Control de Ciclos:** Máximo 2 ciclos por pregunta. Si el Juez rechaza en el ciclo 1, el orquestador reintenta ajustando la consulta con el feedback recibido.

---

## 3. Convenciones del Corpus e IDs Canónicos (Para Citas y Búsqueda)

- **ID canónico de documento (`doc_id`):** Definido en `data/corpus_targets.json` (ej. `ley_1564_2012`, `constitucion`, `codigo_civil`, `c-355_2006`).
- **ID canónico de pasaje / chunk:** Formato `<doc_id>/art_<N>` (ej. `ley_1564_2012/art_42`).
- **Metadatos y Vigencia:** Los documentos convertidos en `corpus/md/` contienen front-matter con metadatos (`tipo_norma`, `numero`, `anio`, `vigencia`). **No citar normas marcadas como derogadas o transitorias como si fueran derecho vigente.**
- **Fuentes válidas admitidas:** Senado, SUIN-Juriscol, relatorías de altas cortes (CC, CSJ, CE), DAPRE, DIAN, SIC, Función Pública, Cancillería y Colpensiones.

---

## 4. Estado y Operación del Corpus (`src/ingest/`)

- Conversión a Markdown:
  ```bash
  python -m src.ingest.convertir
  python -m src.ingest.convertir --estado
  pytest tests/