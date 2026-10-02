# Reporte de avance — Hackathon 2026

**Equipo:** Samu Enjoyer  
**Integrantes:** Santiago Gómez, Camilo Murcia, Angie Gutiérrez  
**Fecha de la medición:** 2 de octubre de 2026

---

## 1. Puntaje sobre las preguntas de muestra

Resultado de `python scripts/evaluate.py --submission <archivo> --split sample` (versión v16: configuración de la entrega con fuentes ampliadas).

| Componente | Puntos obtenidos | Puntos posibles |
|---|---:|---:|
| Exactitud en cerradas | 17,33 (13/15 = 0,867) | 20 |
| Calidad de citación | 18,37 | 20 |
| Abstención calibrada | 9,07 | 10 |
| **Total automático sin RAGAS** | **44,77** | **50** |

Observaciones sobre el resultado:

- Con RAGAS (juez oficial, v14) el puntaje es 0,4703 (14,11 pts; la referencia es 0,451), para un total estimado de ~58,9 / 80. El juez varía ~0,02-0,03 entre corridas.
- Las dos cerradas falladas son la 128 (el corpus no respalda "Fintech" en leasing) y la 748 (el art. 137 del CPACA no llega al top-10). En citación y abstención lo que falta son documentos que la búsqueda no trae (60, 247, 679 y la SU-16 de 2020 en la 453).
- Las corridas son reproducibles (`cache_prompt: false`: dos corridas dan respuestas idénticas). Se probaron y descartaron con datos el modo de razonamiento, el largo por complejidad, ejemplos de estilo y el juez LLM.

## 2. Estado del corpus

| Métrica | Valor |
|---|---|
| Documentos incorporados | 31.037 (de 31.157 registros; 117 fallas y 3 duplicados; cobertura 99,6 %) |
| Fragmentos indexados | 2.210.629 (1.909.717 son ventanas de sentencias) |
| Áreas del banco con cobertura | Las 10: constitucional, administrativo, penal, procesal, comercial y sociedades, civil, familia, tributario, laboral y mercados |
| Áreas del banco sin cobertura | Ninguna. Se excluyeron a propósito el derecho ambiental, minero y de gestión del riesgo, que el enunciado dice que el banco no cubre |

Fuentes consultadas: Secretaría del Senado, SUIN-Juriscol, relatorías de la Corte Constitucional, la Corte Suprema y el Consejo de Estado, DAPRE (Presidencia), DIAN, SIC, Función Pública, Cancillería y Colpensiones. Fechas de consulta: 29 y 30 de septiembre de 2026.

## 3. Arquitectura actual

| Componente | Elección |
|---|---|
| Encoder | Qwen3-Embedding-0.6B (dim 1024), índice FAISS HNSW de 8 bits; reranker bge-reranker-v2-m3 |
| Decoder | Qwen3-8B (GGUF Q4_K_M, llama.cpp), temperatura 0, sin modo de razonamiento, contexto de 32k |
| Estrategia de recuperación | Híbrida: BM25 (raíces Snowball) + HNSW, con una lista extra solo de normas → RRF (k=60) → reranker sobre los 150 primeros → 10 pasajes. Cerradas con BM25 + HNSW; semiabiertas y abiertas solo HNSW. Siglas expandidas. Recall@10: citas 0,931, docs 0,858 |
| Segmentación del corpus | Un chunk por artículo con ruta jerárquica y encabezado citable (los largos en partes); notas, preámbulos y anexos aparte; sentencias en ficha (tesis + resuelve) y ventanas de ~1.700 caracteres por sección |
| Mecanismo de abstención | Validación determinista de citas (sin LLM): toda cita debe estar en los 10 pasajes recuperados, si no se suprime. Si el LLM no responde, la pregunta queda en abstención. |

## 4. Riesgos identificados

1. **Verificación en vivo:** las normas citadas dependen del LLM, y CUDA y CPU pueden diferir aun con temperatura 0. Mitigación: la corrida oficial y la verificación van en la misma máquina (RTX 4090), y se repetirán 3 preguntas dos veces para comprobar que salgan idénticas.
2. **Tiempo de la corrida de las 992 preguntas:** estimado de ~1,7-2 h con un proceso, sin razonamiento. Mitigación: correr en `tmux`, con las 50 de la muestra antes para medir tiempos.
3. **Entregables pendientes:** subir el zip del índice (4,59 GB) y poner el enlace en README, `CORPUS.md` y `corpus_manifest.json`; además de la interfaz, el video y el informe técnico. Mitigación: se dividirán las tareas entre los integrantes para completar las entregas.
