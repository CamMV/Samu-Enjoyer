# Bitácora del corpus — Samu-Enjoyer

Corpus jurídico colombiano construido para el Hackathon IA Week 2026 (Universidad de los Andes):
**31.037 documentos** (normas y sentencias) descargados de fuentes oficiales, convertidos a Markdown con
metadatos, segmentados en **2.211.359 fragmentos** (2.210.629 del corpus base + 730 de las 9 fuentes
agregadas el 3 de octubre) e indexados con BM25 y HNSW.

Archivos que acompañan esta bitácora:

| Archivo | Contenido |
|---|---|
| [`corpus_manifest.json`](corpus_manifest.json) | Un registro por documento indexado: `doc_id`, `titulo`, `fuente`, `url`, `fecha_consulta`, `areas`, `n_articulos`, `n_fragmentos`, `metodo_ingesta` y `sha256` del original. Todo `doc_id` de `submissions.jsonl` está aquí |
| `data/corpus_targets.json` (raíz del repositorio) | Los documentos objetivo con su criterio de inclusión, los excluidos y los no encontrados |

---

## 1. Inventario

El inventario completo, documento por documento, está en `corpus_manifest.json`. Con 31.037 documentos,
una tabla en este archivo no sería legible; aquí va el resumen.

### Totales

| Métrica | Valor |
|---|---:|
| Documentos objetivo | 31.157 |
| Documentos descargados y convertidos (corpus base) | 31.037 (99,6 %) |
| Fallas en el origen oficial | 117 (todas "no encontrado") |
| Duplicados de contenido | 3 |
| Fuentes agregadas el 3/oct | 9 |
| **Documentos en el índice** | **31.037** (31.028 del corpus base + 9 del 3/oct) |
| Artículos indexados | 143.633 |
| Fragmentos en el índice | **2.211.359** (corpus base: 2.210.629) |
| — de normas | 277.184 (corpus base: 276.958) |
| — ventanas de sentencias | 1.909.717 en el corpus base, más las fichas de cada sentencia |
| Originales descargados | 32.348 archivos, 24,86 GB en disco |
| Corpus enriquecido (`chunks.sqlite`, texto y metadatos por fragmento) | 8,6 GB |
| Índice BM25 (completo + solo normas) | 2,4 GB |
| Índice vectorial HNSW (completo + solo normas) | 3,2 GB |
| Fechas de consulta | 29 y 30 de septiembre de 2026; 3 de octubre de 2026 para las 9 fuentes nuevas |

Nueve sentencias de constitucionalidad recientes, de 2021 a 2026, se descargaron y convirtieron pero no
produjeron fragmentos: `c-194_2026`, `c-207_2025`, `c-26_2026`, `c-360_2021`, `c-403_2022`, `c-62_2021`,
`c-67_2026`, `c-73_2024` y `c-93_2021`. Por eso el corpus base indexa 31.028 de los 31.037 documentos
convertidos. Se dejan fuera del manifiesto, porque el agente no puede recuperarlas ni citarlas.

### Por fuente oficial

| Fuente | Documentos | Formato de origen |
|---|---:|---|
| Corte Constitucional — Relatoría (sentencias C, SU y T) | 11.011 | HTML |
| Secretaría del Senado — Base documental | 7.990 | HTML (con cajas de concordancias y notas de vigencia) |
| Corte Suprema de Justicia — Relatoría (casación civil SC, laboral SL y penal SP) | 7.867 | PDF, DOC y DOCX |
| Presidencia de la República (DAPRE) — Normativa | 3.513 | PDF |
| Colpensiones — Normativa | 487 | HTML |
| Consejo de Estado — Relatoría | 104 | DOC |
| DIAN — Normograma (incluye 3 sentencias del Consejo de Estado, Sección Cuarta) | 39 | HTML |
| Cancillería — Normograma | 15 | HTML |
| Función Pública — Gestor Normativo | 8 | PDF |
| Superintendencia de Industria y Comercio — Normatividad | 1 | PDF |
| Ministerio de Ambiente y Desarrollo Sostenible — Normativa | 1 | PDF (con OCR) |
| Comunidad Andina (Decisión 486) | 1 | PDF |
| **Total** | **31.037** | |

### Por tipo de documento

| Tipo | Documentos |
|---|---:|
| Sentencias | 24.027 |
| — Corte Constitucional: T / C / SU | 7.791 / 7.538 / 657 |
| — Corte Suprema: SL / SP / SC (y 67 providencias con prefijo `csj_`) | 3.354 / 3.013 / 1.500 |
| — Consejo de Estado | 107 |
| Decretos | 4.344 |
| Leyes | 2.570 |
| Actos legislativos | 63 |
| Códigos (Civil, Comercio, Penal, CGP, CPACA, CST, Estatuto Tributario, entre otros) | 20 |
| Resoluciones, estatutos, Constitución y Decisión Andina 486 | 13 |

## 2. Criterio de selección

La selección partió de la composición del banco (sección 4.2 del enunciado) y de los `legal_basis` de
las 50 preguntas de muestra, y se amplió por niveles:

| Nivel | Origen | Documentos | Criterio |
|---|---|---:|---|
| 0 | Semilla oficial (`seed_targets.json`) | 173 | Los cuerpos normativos que el enunciado señala como útiles |
| 0 | Enriquecimiento | 405 | Normas que el banco nombra o que completan un área: decretos reglamentarios, estatutos y leyes citadas en los `legal_basis` |
| 0 | Muestra | 4 | Normas de las preguntas de muestra que no estaban en las listas anteriores |
| 0 | Fuentes completas | 22.268 | Relatorías de la Corte Constitucional (C, SU y T) y de la Corte Suprema, y la normativa de Presidencia: las sub-tareas de complejidad media y alta (sentido del fallo, precedente, ponderación) piden jurisprudencia, y el banco cita sentencias que no figuran en la semilla |
| 1 | Enlaces | 8.178 | Normas y sentencias enlazadas desde las páginas del nivel 0 (cajas de concordancias del Senado) y citadas al menos una vez. Solo normas y sentencias, sin doctrina ni actos administrativos. Sus áreas son la unión de las áreas de los documentos que las citan |
| 3/oct | Fuentes citadas por el test | 9 | Ver abajo |

**Excluidos (1.014).** Por un lado, derecho ambiental, minero y de gestión del riesgo, porque el enunciado
aclara que el banco no los cubre. Por otro, la doctrina y los actos administrativos enlazados desde el
nivel 0. **No encontrados (19)** en la fuente oficial, por ejemplo el Decreto 1563 de 2012 y la Sentencia
SL-1972 de 2025; no se buscaron en fuentes no oficiales. Ambas listas, con su motivo, están en
`data/corpus_targets.json`.

**Fuentes agregadas el 3 de octubre (autorizadas por los organizadores).** Se revisaron las 992
preguntas del test buscando normas y providencias citadas que no estuvieran en el corpus. Se agregaron
solo la norma o la providencia oficial; nunca preguntas ni respuestas del test. Son 730 fragmentos, 226
de ellos de normas:

| doc_id | Documento | Fuente | Fragmentos |
|---|---|---|---:|
| `resolucion_368_2014` | Resolución 368 de 2014 (relleno sanitario El Carrasco) | MinAmbiente (OCR del PDF oficial) | 49 |
| `ley_99_1993` | Ley 99 de 1993 (SINA), base del bloque anterior | Secretaría del Senado | 167 |
| `decreto_4302_2008` | Decreto 4302 de 2008 (licencias obligatorias) | SIC | 10 |
| `jurisprudencia_t-426_2003` | Sentencia T-426 de 2003 | Corte Constitucional | 39 |
| `jurisprudencia_t-617_2010` | Sentencia T-617 de 2010 | Corte Constitucional | 245 |
| `jurisprudencia_t-254_2006` | Sentencia T-254 de 2006 | Corte Constitucional | 101 |
| `jurisprudencia_ce-11001-03-27-000-2020-00027-00_2022` | Consejo de Estado, Sección Cuarta, exp. 25406 | DIAN — Normograma | 32 |
| `jurisprudencia_ce-25000-23-37-000-2019-00417-01_2023` | Consejo de Estado, Sección Cuarta, exp. 27113 | DIAN — Normograma | 25 |
| `jurisprudencia_ce-11001-03-27-000-2022-00036-00_2024` | Consejo de Estado, Sección Cuarta, exp. 26644 | DIAN — Normograma | 62 |

La Ley 99 de 1993 y la Resolución 368 de 2014 eran ambientales y por eso estaban excluidas, pero un
bloque del test se basa en ellas. La "SU-279 de 2019" y la "SU-488 de 2011" que cita el test no existen
en la relatoría: son la T-279 de 2019 y la T-488 de 2011, que ya estaban en el corpus. No se consiguieron
en fuente oficial: CSJ exp. 2001-00847 (19/oct/2011), CSJ exp. 2001-00900 (9/feb/2011), CSJ laboral rad.
34223 y CE Sección Tercera del 28/feb/2020 (culpa in contraendo).

### Cobertura frente a la composición del banco

| Área | Ítems en el banco | Documentos | Fragmentos | Fuentes principales |
|---|---:|---:|---:|---|
| Derecho constitucional | 134 | 16.918 | 1.486.245 | Constitución, Decreto 2591 de 1991, Ley 472 de 1998, sentencias C, SU y T |
| Derecho administrativo | 124 | 13.233 | 909.349 | CPACA (Ley 1437 de 2011), Código Contencioso Administrativo, Ley 80 de 1993, decretos únicos reglamentarios |
| Derecho penal | 123 | 10.264 | 758.721 | Código Penal, Código de Procedimiento Penal (Leyes 906 de 2004 y 600 de 2000), casación penal |
| Derecho procesal | 111 | 12.440 | 1.058.376 | Código General del Proceso, Código de Procedimiento Civil, Código Procesal del Trabajo |
| Derecho comercial y sociedades | 104 | 6.639 | 496.047 | Código de Comercio, Estatuto Orgánico del Sistema Financiero, Decreto 2555 de 2010, Ley 222 de 1995 |
| Derecho civil | 102 | 5.830 | 517.302 | Código Civil, casación civil |
| Derecho de familia | 93 | 8.299 | 679.958 | Código Civil (libro primero), Código de la Infancia y la Adolescencia, Ley 294 de 1996 |
| Derecho tributario | 92 | 11.443 | 981.404 | Estatuto Tributario, Decreto 1625 de 2016, normograma DIAN, Consejo de Estado (Sección Cuarta) |
| Derecho laboral | 87 | 14.297 | 957.456 | Código Sustantivo del Trabajo, Leyes 100 de 1993 y 1562 de 2012, normativa de Colpensiones, casación laboral |
| Derecho de los mercados | 72 | 5.784 | 422.803 | Estatuto del Consumidor, Decreto 2153 de 1992, Ley 1581 de 2012, Decisión Andina 486, Decreto 4302 de 2008 |

Un documento puede responder a varias áreas, por eso la suma supera el total. Las diez áreas tienen su
código o ley principal y jurisprudencia.

## 3. Método de ingesta y limpieza

1. **Descarga** (`scraper/descargar.py`). Cuatro carriles en paralelo, uno por servidor de origen, con
   reintentos y con parada y reanudación limpias. Cada documento queda registrado con su URL, fecha de
   consulta y `sha256` de cada archivo descargado. Resultado: 31.037 de 31.157 objetivos (99,6 %).
   Hubo 117 fallas permanentes, todas "no encontrado" en la fuente oficial: 90 de la Corte Suprema (su
   buscador ya no las encuentra), 26 del Consejo de Estado (el servidor devuelve el archivo vacío) y 1
   de la Corte Constitucional (SU-163 de 2023, no publicada). Además, 3 documentos eran duplicados de
   contenido. Una auditoría (`scraper/auditar_descarga.py`) confirmó que no hay archivos truncados ni
   dañados.
2. **Conversión a Markdown** (`src/ingest/convertir.py`).
   - HTML con BeautifulSoup y una plantilla por fuente: quita la navegación y conserva las notas de
     vigencia y concordancias del Senado.
   - PDF con PyMuPDF.
   - DOC con LibreOffice (a DOCX) y DOCX con python-docx.
   - Los documentos de varias páginas se unen en uno. El texto tachado en la fuente (inexequible o
     derogado) se conserva marcado como `~~…~~`.
3. **OCR y limpieza.**
   - Tesseract (español) en las capas de texto ilegibles: 3.780 PDF.
   - Se corrigieron las palabras pegadas de las capas de texto de los PDF: de ~1.580 documentos
     afectados a 0.
   - Se releyeron con OCR 588 documentos de la Corte con capa de texto ilegible.
   - Una auditoría estratificada de 100 documentos dio 91 correctos, 8 por revisar y 1 falla (una ley
     aprobatoria de tratado).
4. **Metadatos** (front-matter de cada `.md`): tipo de norma, número, año, órgano emisor, nombre citable,
   vigencia, áreas, prioridad, fuente, URL y fecha de consulta. Cada fragmento los hereda.
5. **Segmentación** (`src/knowledge/chunking.py`).
   - Normas: un fragmento por artículo, con su ruta jerárquica (libro, título, capítulo) y un encabezado
     citable ("Código General del Proceso (Ley 1564 de 2012) › … › Artículo 25"). Los artículos largos
     se parten y se reúnen al entregarlos. Notas de vigencia, preámbulos y anexos van aparte.
   - Sentencias: una ficha (descriptores, tesis y parte resolutiva) y ventanas de ~1.700 caracteres por
     sección.
   - Cada fragmento guarda su posición (`inicio`, `fin`) en el documento y un ID canónico `<doc_id>/art_<N>`.
6. **Indexación.** BM25 con raíces Snowball (bm25s) e índice vectorial FAISS `IndexHNSWSQ` (8 bits, M=32,
   efConstruction 200, efSearch 256) sobre Qwen3-Embedding-0.6B (dimensión 1024), para el corpus completo
   y para el subconjunto de normas. Las 9 fuentes del 3/oct se agregaron sin recalcular lo existente
   (`src/knowledge/agregar_chunks.py`): sus vectores van al final de los dos HNSW y BM25 se reconstruye
   completo.

**Decisión sobre el encabezado de los fragmentos.** Cada fragmento empieza con el nombre citable de la
norma o sentencia. Así el evaluador puede ligar la cita de la respuesta con el pasaje recuperado, y el
agente cita con el mismo nombre que trae la evidencia.

### Vigencia y normas derogadas

- **En la conversión:** la `vigencia` de cada documento (derogada, transitoria o por revisar) sale de la
  lista maestra y de las notas de vigencia de la fuente. Las notas de vigencia del Senado se quedan con
  su artículo (hasta 800 caracteres), porque responden preguntas de vigencia.
- **En la segmentación:** un artículo con más del 60 % de su texto tachado en la fuente se marca
  `derogado`. El encabezado de cada fragmento lleva la marca `[vigencia: …]`.
- **En la búsqueda:** después del reranker, los fragmentos derogados pierden 0,15 de puntaje. Con eso
  quedan por debajo de los vigentes, pero no se borran: siguen sirviendo para preguntas sobre la historia
  de la norma.
- **En la redacción:** el prompt del escritor prohíbe presentar como vigente una norma marcada como
  derogada o transitoria.

## 4. Evolución del puntaje

Medición sobre las 50 preguntas de muestra con `scripts/evaluate.py`. En todas las versiones se miden los
50 puntos deterministas (cerradas, citación y abstención). RAGAS se midió solo en algunas versiones: juez
`z-ai/glm-5.3-flash`, 35 ítems de texto libre, referencia 0,451. El corpus se mantuvo fijo (31.028
documentos, 2.210.629 fragmentos) desde el 1 de octubre: lo que cambia entre versiones es la recuperación
y el agente.

| Fecha | Versión | Documentos | Fragmentos | Cerradas /20 | Citación /20 | Abstención /10 | Total /50 | RAGAS /30 | Qué cambió |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 2026-10-01 | v2 | 31.028 | 2.210.629 | 14,67 | 12,24 | 7,33 | 34,24 | 12,88 (0,429) | Agente con LangGraph, juez y contexto de 32k sobre el corpus completo |
| 2026-10-01 | v3 | 31.028 | 2.210.629 | 14,67 | 13,88 | 7,44 | 35,99 | — | Sin pasajes casi duplicados en el top-10 |
| 2026-10-01 | v4 | 31.028 | 2.210.629 | 14,67 | 16,56 | 8,37 | 39,60 | — | BM25 solo en cerradas, normas de los pasajes en la respuesta, decreto del salario mínimo |
| 2026-10-01 | v8 | 31.028 | 2.210.629 | 17,33 | 16,73 | 8,84 | 42,90 | 14,56 (0,485)* | Letra elegida a partir del razonamiento, cerradas sin abstención, sin juez LLM |
| 2026-10-02 | v14 | 31.028 | 2.210.629 | 17,33 | 16,73 | 8,84 | 42,90 | 14,11 (0,470) | Salida del LLM reproducible (`cache_prompt: false`) y siglas expandidas en la consulta |
| 2026-10-02 | v16 | 31.028 | 2.210.629 | 17,33 | 18,37 | 9,07 | 44,77 | — | Fuentes de los pasajes (sentencias y leyes mencionadas) al final de la respuesta |
| 2026-10-02 | v22 | 31.028 | 2.210.629 | 17,33 | 17,55 | 9,07 | 43,95 | ~14,07 (0,469) | Abiertas en formato IRAC (requisito de los organizadores) |
| 2026-10-03 | v26 | 31.028 | 2.210.629 | 17,33 | 18,37 | 9,07 | 44,77 | ~14,2 (~0,474) | Anclaje de la letra, poda de oraciones accesorias, fuentes compactas en abiertas); misma cifra en la A40 y en la RTX 4090 |
| 2026-10-03 | **v27 (final)** | 31.037 | 2.211.359 | **17,33** | **18,37** | **9,07** | **44,77** | **13,26 (0,442)** | Índice con las 9 fuentes del test (ninguna de las 50 de muestra las cita), citas del Consejo de Estado por número de expediente y reintento cuando el prompt excede el contexto. Genera `submissions.jsonl`. **Total automático: 58,03 / 80** |

\* Medición con 600 s de límite por llamada al juez. Con el límite oficial de 180 s, la misma versión dio 0,455. El juez varía ~0,02-0,03 entre corridas.

**Lectura de la curva.**
- **Cerradas:** se estancaron en 11/15 hasta que se separó el razonamiento de la elección de la letra: el
  modelo razonaba bien y anunciaba otra opción.
- **Citación:** subió sobre todo por la recuperación (la lista de normas y el filtro de duplicados ponen
  el documento correcto en el top-10: recall_docs@10 pasó de 0,439 a 0,858) y por nombrar en la
  respuesta las normas de los pasajes consultados, siempre respaldadas por la evidencia.
- **Lo que falta:** en citación y abstención son documentos que la búsqueda no trae. En cerradas, la 128
  y la 748 no tienen respaldo alcanzable en el top-10.

## 5. Licencia

El corpus procesado y el índice se publican bajo **CC BY 4.0** (archivo `LICENSE` dentro del
comprimido). La licencia cubre el trabajo del equipo: descarga, conversión, OCR, segmentación,
extracción de metadatos e indexación.

Los textos normativos y jurisprudenciales son de libre distribución en Colombia: la ley de derecho de
autor (Ley 23 de 1982) permite publicar libremente las leyes, decretos, resoluciones y demás actos
oficiales, siempre que se respete el texto de la edición oficial, y las providencias judiciales son
públicas. Por eso cada documento conserva en el manifiesto su URL oficial, su fecha de consulta y el
`sha256` del original.

## 6. Enlace al corpus e índice

| Recurso | Enlace | Tamaño | Licencia | Vigencia |
|---|---|---|---|---|
| `corpus_Samu_Enjoyer.zip` | [Google Drive](https://drive.google.com/file/d/1iKjA3GjzCf_R0Kvj8hmp8XBG_XR8bsR9/view?usp=sharing) | ~4,3 GB (≈15 GB descomprimido) | CC BY 4.0 | 30 días desde el 3 de octubre de 2026 |

El comprimido se descomprime en la raíz del repositorio y deja todo bajo `corpus/`:

```
corpus/
├── LICENSE                     CC BY 4.0
├── LEEME.md                    contenido, uso y hashes
├── SHA256SUMS.txt
├── corpus_manifest.json        manifiesto de descarga (fuente, URL, fecha y sha256 por documento)
├── auditoria_descarga.json
├── chunks/chunks.sqlite        corpus enriquecido: fragmentos con metadatos
└── indices/
    ├── bm25_todo/  bm25_normas/
    └── qwen3-emb-0.6b_todo/  qwen3-emb-0.6b_normas/   (hnsw.faiss + ids.json + info.json)
```

`python -m src.knowledge.verify_indices` comprueba que esté completo y que BM25 y HNSW tengan los mismos
IDs en el mismo orden.

**Reconstrucción desde las URL.** `data/corpus_targets.json` lista los documentos y sus URL.
`python scraper/descargar.py iniciar` los descarga (el `sha256` de cada original está en
`corpus_manifest.json` para comprobarlos), `python -m src.ingest.convertir` los convierte, y
`python -m src.knowledge.chunking`, `src.knowledge.bm25_store` y `src.knowledge.vector_store` arman el
índice (ver `README.md`).
