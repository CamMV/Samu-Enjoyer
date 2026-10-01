# Bitácora del corpus — Equipo Samu Enjoyer

Corpus jurídico colombiano construido para el Hackathon IA Week 2026: **31.028 documentos** (normas y
sentencias) descargados de fuentes oficiales, convertidos a Markdown con metadatos y segmentados en
**2.210.629 fragmentos** indexados con BM25 y HNSW.

Archivos que acompañan esta bitácora, en la raíz del repositorio:

| Archivo | Contenido |
|---|---|
| [`corpus_manifest.json`](corpus_manifest.json) | Un registro por documento: `doc_id`, `titulo`, `fuente`, `url`, `fecha_consulta`, `areas`, artículos, fragmentos, método de ingesta y `sha256` del original. Todo `doc_id` de `submissions.jsonl` está aquí |
| [`corpus_inventario.csv`](corpus_inventario.csv) | El mismo inventario en tabla (31.028 filas), para filtrar y ordenar |
| [`data/corpus_targets.json`](data/corpus_targets.json) | La lista de documentos objetivo con su criterio de inclusión, los 1.014 excluidos y los 19 no encontrados |

---

## 1. Inventario

El inventario completo, documento por documento (título, fuente, URL, fecha de consulta, número de
artículos y de fragmentos, y áreas del banco), está en `corpus_manifest.json` y `corpus_inventario.csv`.
Con 31.028 documentos, una tabla en este archivo no sería legible; aquí va el resumen.

### Por fuente

| Fuente | Documentos | Formato de origen |
|---|---:|---|
| Corte Constitucional — Relatoría | 11.008 | HTML |
| Secretaría del Senado — Base documental | 7.989 | HTML (con cajas de concordancias y notas de vigencia) |
| Corte Suprema de Justicia — Relatoría | 7.867 | PDF, DOC y DOCX |
| Presidencia de la República — Normativa | 3.513 | PDF |
| Colpensiones — Normativa | 487 | HTML |
| Consejo de Estado — Relatoría | 104 | DOC |
| DIAN — Normograma | 36 | HTML |
| Cancillería — Normograma | 15 | HTML |
| Función Pública — Gestor Normativo | 8 | PDF |
| Comunidad Andina | 1 | PDF |
| **Total** | **31.028** | |

### Por tipo de documento

| Tipo | Documentos |
|---|---:|
| Sentencias (Corte Constitucional, Corte Suprema, Consejo de Estado) | 24.021 |
| Decretos | 4.343 |
| Leyes | 2.569 |
| Actos legislativos | 63 |
| Códigos (Civil, Comercio, Penal, CGP, CPACA, CST, Estatuto Tributario, entre otros) | 20 |
| Resoluciones, estatutos, Constitución y Decisión Andina 486 | 12 |

### Totales

| Métrica | Valor |
|---|---:|
| Documentos incorporados | 31.028 |
| Artículos indexados | 143.495 |
| Fragmentos en el índice | 2.210.629 (1.909.717 son ventanas de sentencias) |
| Originales descargados | 32.348 archivos, 24,9 GB |
| Corpus en Markdown (comprimido) | 0,71 GB |
| Corpus enriquecido (`chunks.sqlite`, texto y metadatos por fragmento) | 8,6 GB |
| Índice BM25 (completo + solo normas) | 2,4 GB |
| Índice vectorial HNSW (completo + solo normas) | 3,2 GB |
| Fechas de consulta | 29 y 30 de septiembre de 2026 |

## 2. Criterio de selección

La selección partió de la composición del banco (sección 4.2 del enunciado) y de los `legal_basis` de
las 50 preguntas de muestra, y se amplió por niveles:

| Nivel | Origen | Documentos | Criterio |
|---|---|---:|---|
| 0 | Semilla oficial (`seed_targets.json`) | 173 | Los cuerpos normativos que el enunciado señala como útiles |
| 0 | Enriquecimiento | 405 | Normas que el banco nombra o que completan un área: decretos reglamentarios, estatutos y leyes citadas en los `legal_basis` |
| 0 | Muestra | 4 | Normas de las preguntas de muestra que no estaban en las listas anteriores |
| 0 | Fuentes completas | 22.268 | Relatorías de la Corte Constitucional (C, SU y T) y de la Corte Suprema, y la normativa de Presidencia: las sub-tareas de complejidad media y alta (sentido del fallo, precedente, ponderación) piden jurisprudencia, y el banco cita sentencias que no figuran en la semilla |
| 1 | Enlaces | 8.178 | Normas y sentencias enlazadas desde las páginas del nivel 0 (cajas de concordancias del Senado) y citadas al menos una vez; solo normas y sentencias, sin doctrina ni actos administrativos. Sus áreas son la unión de las áreas de los documentos que las citan |

**Excluidos (1.014).** Derecho ambiental, minero y de gestión del riesgo, porque el enunciado aclara
que el banco no los cubre (Código de Minas, Ley 99 de 1993, sancionatorio ambiental y similares), y
la doctrina y los actos administrativos enlazados desde el nivel 0. **No encontrados (19)** en la fuente
oficial, por ejemplo el Decreto 1563 de 2012 y la Sentencia SL-1972 de 2025; no se buscaron en fuentes
no oficiales. Ambas listas, con su motivo, están en `data/corpus_targets.json`.

### Cobertura frente a la composición del banco

| Área | Ítems en el banco | Documentos | Fragmentos | Fuentes principales |
|---|---:|---:|---:|---|
| Derecho constitucional | 134 | 16.915 | 1.485.860 | Constitución, Decreto 2591 de 1991, Ley 472 de 1998, sentencias C, SU y T |
| Derecho administrativo | 124 | 13.231 | 909.133 | CPACA (Ley 1437 de 2011), Código Contencioso Administrativo, Ley 80 de 1993, decretos únicos reglamentarios |
| Derecho penal | 123 | 10.264 | 758.721 | Código Penal, Código de Procedimiento Penal (Leyes 906 de 2004 y 600 de 2000), casación penal |
| Derecho procesal | 111 | 12.440 | 1.058.376 | Código General del Proceso, Código de Procedimiento Civil, Código Procesal del Trabajo |
| Derecho comercial y sociedades | 104 | 6.639 | 496.047 | Código de Comercio, Estatuto Orgánico del Sistema Financiero, Decreto 2555 de 2010, Ley 222 de 1995 |
| Derecho civil | 102 | 5.830 | 517.302 | Código Civil, casación civil |
| Derecho de familia | 93 | 8.299 | 679.958 | Código Civil (libro primero), Código de la Infancia y la Adolescencia, Ley 294 de 1996 |
| Derecho tributario | 92 | 11.440 | 981.285 | Estatuto Tributario, Decreto 1625 de 2016, normograma DIAN |
| Derecho laboral | 87 | 14.297 | 957.456 | Código Sustantivo del Trabajo, Leyes 100 de 1993 y 1562 de 2012, normativa de Colpensiones, casación laboral |
| Derecho de los mercados | 72 | 5.783 | 422.793 | Estatuto del Consumidor, Decreto 2153 de 1992, Ley 1581 de 2012, Decisión Andina 486 |

Un documento puede responder a varias áreas, por eso la suma de documentos supera el total. Las 10
áreas tienen cobertura de su código o ley principal y de jurisprudencia.

## 3. Método de ingesta y limpieza

1. **Descarga** (`scraper/descargar.py`). Cuatro carriles en paralelo, uno por servidor de origen,
   con reintentos y parada y reanudación limpias. Cada documento queda registrado con su URL, fecha
   de consulta y `sha256` de cada archivo descargado. Resultado: 31.037 de 31.157 objetivos (99,6 %);
   117 fallas permanentes, todas "no encontrado" en la fuente oficial (90 de la Corte Suprema, 26 del
   Consejo de Estado y 1 de la Corte Constitucional), y 3 duplicados de contenido. Una auditoría
   (`scraper/auditar_descarga.py`) confirmó que no hay archivos truncados ni dañados.
2. **Conversión a Markdown** (`src/ingest/convertir.py`). HTML con BeautifulSoup y una plantilla por
   fuente (quita navegación y conserva las notas de vigencia y concordancias del Senado); PDF con
   PyMuPDF; DOC con LibreOffice (a DOCX) y DOCX con python-docx. Los documentos de varias páginas se
   unen en uno.
3. **OCR y limpieza.** Tesseract (español) en las capas de texto ilegibles: 3.780 PDF. Se corrigieron
   las palabras pegadas de las capas de texto de los PDF (de ~1.580 documentos afectados a 0) y se
   releyeron con OCR 588 documentos de la Corte con capa de texto ilegible. Una auditoría estratificada
   de 100 documentos dio 91 correctos, 8 por revisar y 1 falla (una ley aprobatoria de tratado).
4. **Metadatos** (front-matter de cada `.md`). Tipo de norma, número, año, órgano emisor, nombre
   citable, vigencia (derogada o transitoria según las notas de la fuente), áreas, prioridad, fuente,
   URL y fecha de consulta. Cada fragmento los hereda.
5. **Segmentación** (`src/knowledge/chunking.py`). Normas: un fragmento por artículo, con su ruta
   jerárquica (libro, título, capítulo) y un encabezado citable ("Código General del Proceso (Ley 1564
   de 2012) › … › Artículo 25"); los artículos largos se parten y se reúnen al entregarlos; notas de
   vigencia, preámbulos y anexos van aparte. Sentencias: una ficha (descriptores, tesis y parte
   resolutiva) y ventanas de ~1.700 caracteres por sección. Cada fragmento guarda su posición
   (`inicio`, `fin`) en el documento.
6. **Indexación.** BM25 con raíces Snowball (bm25s) e índice vectorial FAISS `IndexHNSWSQ` (8 bits,
   M=32) sobre Qwen3-Embedding-0.6B, para el corpus completo y para el subconjunto de normas.

**Decisión sobre el encabezado de los fragmentos.** Cada fragmento empieza con el nombre citable de la
norma o sentencia. Así el evaluador puede ligar la cita de la respuesta con el pasaje recuperado, y el
agente cita con el mismo nombre que trae la evidencia.

## 4. Evolución del puntaje

Medición sobre las 50 preguntas de muestra con `scripts/evaluate.py`. Los 50 puntos deterministas
(cerradas, citación y abstención) en todas las versiones; RAGAS (juez `z-ai/glm-5.3-flash`, 35 ítems de
texto libre, referencia 0,451) donde se midió.

| Fecha | Versión | Cerradas /20 | Citación /20 | Abstención /10 | Total /50 | RAGAS /30 | Qué cambió |
|---|---|---:|---:|---:|---:|---:|---|
| 2026-10-01 | v2 | 14,67 | 12,24 | 7,33 | 34,24 | 12,88 (0,429) | Agente con LangGraph, juez y contexto de 32k sobre el corpus completo |
| 2026-10-01 | v3 | 14,67 | 13,88 | 7,44 | 35,99 | — | Sin pasajes casi duplicados en el top-10 |
| 2026-10-01 | v4 | 14,67 | 16,56 | 8,37 | 39,60 | — | BM25 solo en cerradas, normas de los pasajes consultados en la respuesta, decreto del salario mínimo |
| 2026-10-01 | v5 | 17,33 | — | — | — | — | Elección de la letra a partir del razonamiento, calculadora de montos, cerradas sin abstención (13/15 cerradas; corrida completa pendiente) |

**Lectura de la curva.** La exactitud en cerradas se estancó en 11/15 hasta que se separó el
razonamiento de la elección de la letra: el modelo razonaba bien y anunciaba otra opción. La citación
subió sobre todo por la recuperación (documentos correctos en el top-10) y por nombrar en la respuesta
las normas de los pasajes consultados, siempre respaldadas por la evidencia.

## 5. Licencia

El corpus procesado y el índice se publican bajo **CC-BY-4.0**. Los textos normativos y
jurisprudenciales colombianos son de dominio público; la licencia cubre el trabajo de descarga,
conversión, OCR, segmentación y extracción de metadatos del equipo.

## 6. Enlace al corpus e índice

| Recurso | Enlace | Tamaño | Vigencia |
|---|---|---|---|
| `samu_enjoyer_corpus_indice.zip` | PENDIENTE | 4,59 GB | 30 días desde el 3 de octubre de 2026 |

El comprimido se descomprime en la raíz del repositorio y deja todo bajo `corpus/`: `LICENSE`,
`LEEME.md`, `SHA256SUMS.txt`, el manifiesto de descarga, `chunks/chunks.sqlite` (corpus enriquecido) e
`indices/` (BM25 y HNSW). `python -m src.knowledge.verify_indices` comprueba que esté completo.

**Reconstrucción desde las URL.** `data/corpus_targets.json` lista los documentos y sus URL;
`python scraper/descargar.py iniciar` los descarga, `python -m src.ingest.convertir` los convierte y
`python -m src.knowledge.chunking`, `src.knowledge.bm25_store` y `src.knowledge.vector_store` arman el
índice (ver README).
