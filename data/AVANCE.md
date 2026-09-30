# Avance de la ampliación del corpus (puntos de guardado)

Última actualización: 2026-09-29 (segunda sesión). Los checkpoints de recolección
están completos. Quedan **decisiones abiertas** (abajo) y la descarga real, que
hace el compañero siguiendo `CLAUDE.md`.

## Actualización: ampliación a ~31k (EV en paralelo)

- [x] AM1. Sentencias T de la Corte Constitucional 2011-2026: `data/fuentes/fuente_cc_t.json`
  (2014-2026, 5.372) y `fuente_cc_t_2011_2013.json` (2.389). Agregadas 7.727 nuevas.
- [x] AM2. Tratados de derechos humanos y convenios fundamentales de la OIT:
  `data/fuentes/tratados_ddhh.json` (28 leyes aprobatorias). 21 verificadas por su
  epígrafe y agregadas. Las otras 7 (no están en Senado ni Colpensiones) se encontraron en Cancillería (AM3): Ley 74/1968
  (Pactos ONU), 51/1981 (CEDAW), 22/1981 (discriminación racial), 70/1986 (tortura ONU),
  12/1991 (Convención del Niño), 5/1960 (Ginebra), 22/1967 (Convenio 111 OIT).
- [x] AM3. Los 7 tratados que faltaban sí están en el normograma de Cancillería (misma plantilla
  del Senado): `data/fuentes/tratados_ddhh_cancilleria.json`. Ya están los 28 (CEDAW, CDN,
  Pactos ONU, Ginebra, OIT 111…).
- [x] AM4. Resoluciones DIAN que fijan la UVT (2016, 2019, 2020, 2022-2025), verificadas por su
  epígrafe: `data/fuentes/uvt_dian.json`. Excepción al filtro de actos administrativos (dato
  anual para montos tributarios). Los decretos de salario mínimo 2016-2026 ya venían de Presidencia.
- Supersociedades: solo publica una selección de ~12 autos/sentencias destacados (páginas de
  jurisprudencia de insolvencia y mercantil). Pendiente opcional; no hay índice masivo.
- **Total actual: 31.157 documentos.** Tamaño estimado: +~2-4 GB
  por las sentencias T (≈0,26 MB c/u) → **~13 a ~26 GB**.

## Estado de `data/corpus_targets.json` (lista maestra, antes de AM1-AM2)

**23.411 documentos** (~24.700 archivos):

| Origen | Docs |
|---|---|
| nivel 0 · seed (incluye Decretos 46/2024 y 405/2025, recuperados desde Presidencia) | 173 |
| nivel 0 · enriquecimiento (lista de la otra IA) | 377 |
| nivel 0 · muestra (C-468/24, SU-16/20, SU-277/25, T-256/25) | 4 |
| nivel 0 · fuentes nuevas | 14.654 |
| nivel 1 · enlaces (todos, ≥1 cita; 3.149 normas + 5.054 sentencias) | 8.203 |

Por fuente: Senado 7.998 · Corte Suprema 7.960 · Presidencia 3.513 · Corte
Constitucional 3.282 · Colpensiones 482 · Consejo de Estado 130 · DIAN 29 ·
Función Pública 8 · Cancillería 8 · Comunidad Andina 1 (Decisión 486 del seed).
Formatos: 11.799 HTML, 8.574 PDF, 2.793 .doc, 245 .docx.
No encontrados: 19 (erratas del seed y enlaces rotos del Senado).

La versión anterior (4.696 docs) está en git, en el commit 2c8646e.

## Tamaño estimado (muestreo real por fuente)

| Fuente | Optimista | Pesimista |
|---|---|---|
| Senado (HTML + cajas) | 1,8 GB | 4,1 GB |
| Corte Suprema (~97 % descargable, ~1,5 MB c/u) | 6,6 GB | 11,8 GB |
| Presidencia (PDF, mediana 0,6 MB, media 1,3 MB) | 2,2 GB | 4,7 GB |
| Corte Constitucional | 0,5 GB | 1,5 GB |
| Resto | 0,2 GB | 0,3 GB |
| **Total** | **~11 GB** | **~22 GB** (central ~16 GB) |

## Criterios acordados

- Solo derecho **colombiano**, fuentes **públicas** (.gov.co). Fuera el derecho
  supranacional del nivel 1 (Comunidad Andina); la Decisión 486 se mantiene
  porque el seed la pide.
- Fuera el derecho ambiental del nivel 0 (el banco no lo cubre).
- Todo el nivel 1, pero solo normas y sentencias. Un solo nivel de enlaces,
  deduplicado por `doc_id`: sin ciclos.
- Tribunales superiores fuera (sin URL estables, no son precedente vinculante).
- Presidencia: fuera los decretos no normativos (filtro `DAPRE_EXCLUIR` en
  `scraper/fuentes_nuevas.py`): de 10.576 listados quedan 3.761 normativos.
- Presidencia no necesita OCR: 55 de 55 PDF de muestra traen capa de texto.

## Checkpoints

- [x] CP1. Nivel 1 completo (archivo intermedio ya borrado; se regenera con `construir_targets.py`).
- [x] CP2. Consejo de Estado → `data/fuentes/fuente_ce.json` (131).
- [x] CP3. Corte Constitucional → `data/fuentes/fuente_cc.json` (8.185 C y SU).
- [x] CP4. Corte Suprema → `data/fuentes/fuente_csj.json` (7.958).
- [x] CP5. Presidencia → `data/fuentes/fuente_dapre.json`: los 128 meses
  (2016-2026) en `dapre_listados.jsonl`. Agosto de 2026 se envió en dos partes
  (236 filas no caben en una URL).
- [x] CP6. Unión en la lista maestra (`--agregar --origen fuente_nueva`: no
  reemplaza nada, no descarga para verificar y recupera normas del seed que
  estaban en `no_encontrados`).
- [x] CP7. Auditoría: sin `doc_id` repetidos, IDs consistentes con el scraper,
  áreas válidas, dominios oficiales.
- [x] CP7b. Consejo de Estado: el servicio exige sesión (cookie de WebRelatoria).
  El scraper la abre y reintenta: **101 de 130** descargan; 29 siguen vacíos
  desde el servidor (quedarán como `falla`).
- [x] CP7c. Corte Suprema: rutas desactualizadas en el índice → el scraper
  vuelve a buscar la sentencia (también con ceros a la izquierda, p. ej.
  `SP073-2023`). Muestra de 30: **29 descargan**.
- [x] CP8. `CLAUDE.md` actualizado: total, tamaños, descarga por tandas con
  `--origen` / `--fuente`, nuevas fuentes y conversión de `.doc`.

## Decisiones abiertas (preguntar al usuario antes de tocar)

1. **Leyes aprobatorias de tratados (458 normas, casi todas de nivel 1).**
   Chocan con "no transnacionalidad", pero incluyen tratados de derechos humanos
   del bloque de constitucionalidad (p. ej. Ley 1346/2009, discapacidad; Ley
   319/1996, Protocolo de San Salvador), que el banco sí usa (la pregunta 946
   cita la CEDAW). Además hay falsos positivos ("se aprueba el Acuerdo número
   12" de una entidad colombiana). Opciones: dejarlas; quitar solo las no
   relacionadas con derechos humanos; quitar todas.
2. **Normas ambientales en nivel 1 y Presidencia (27).** Por ejemplo el Código de
   Recursos Naturales (Decreto 2811/1974) y la Ley 1252/2008. Hay falsos
   positivos (Ley 723/2001, celebración de un municipio; Ley 2374/2024,
   esterilización de mascotas). Probablemente conviene quitarlas, revisando la
   lista a mano.
3. Las ~72 **sentencias** con tema ambiental se dejaron: son de consulta previa,
   acción popular o derechos fundamentales.

## Siguiente trabajo (no es recolección)

- Descarga completa (compañero, por tandas; ver `CLAUDE.md`).
- Conversión a Markdown + segmentación por artículo + deduplicación de pasajes
  (texto copiado en leyes de reforma; ver la conversación sobre dedup en el
  conversor).
- Medir recall@10 de las normas de referencia sobre `data/sample_50.jsonl` con
  el índice, comparando nivel 0 contra el corpus completo.

## Evaluación local con Qwen3-8B (checkpoints)

Evaluador oficial en `scripts/` (`evaluate.py`, `citations.py`, `common.py`,
copiados tal cual). Sin llave de OpenRouter, la corrección de texto libre se
EMULA en `scripts/eval_local.py`: 0,75 × F1 factual (juez Qwen3-8B local) +
0,25 × similitud (embeddings de Ollama). Las demás métricas usan el código oficial.

- [x] EV1. Evaluador oficial + mini-corpus: `data/eval/mini_corpus.json` (41 docs
  citados por la muestra + 250 distractores al azar), descargados en `corpus/raw`.
- [x] EV2. Qwen3-8B en Ollama (`ollama pull qwen3:8b`, 5,2 GB).
- [x] EV3. Pasajes: `data/eval/pasajes.jsonl` (31.521, por artículo, con encabezado citable).
- [ ] EV4. Generación: **pausada el 2026-09-29 con 19 de 50 respuestas de la prueba A**
  guardadas y válidas en `data/eval/entrega_A.jsonl`; la prueba B no ha empezado.
  Tiempo medido: ~20-45 s por cerrada y ~90-100 s por abierta con Qwen3-8B en la RTX 3050 Ti
  (A restante ≈ 30-40 min; B ≈ 60-90 min). Comandos:
  `python scripts/eval_local.py generar --prueba A` y `--prueba B`
  → `data/eval/entrega_A.jsonl`, `entrega_B.jsonl` (guarda por pregunta; relanzar retoma).
- [x] EV4 terminado: 50/50 en A y en B.
- [x] EV5. Juez factual (Qwen3-8B): `python scripts/eval_local.py juez --prueba A` y `--prueba B`
  → `juez_A.jsonl`, `juez_B.jsonl` (en curso el 2026-09-29).
- [x] EV5b. Similitud con dos encoders (Qwen3 no genera embeddings en Ollama):
  `python scripts/eval_local.py similitud --prueba A --embed nomic-embed-text` (y B), y lo mismo con
  `--embed granite-embedding:278m` → `juez_{A,B}_{encoder}.jsonl`.
- [x] EV7. Borrados (2026-09-30). Al terminar, borrar los modelos descargados para la prueba (pedido del usuario):
  `ollama rm qwen3:8b nomic-embed-text granite-embedding:278m` (no tocar `gemma3:1b`, que ya estaba).
- [x] EV6. Reporte: `python scripts/eval_local.py reporte` → `data/eval/reporte.json`.
- Requiere `ollama serve` corriendo.

### Cómo retomar la evaluación (después de suspender o reiniciar el PC)

```bash
ollama serve                                   # en otra terminal, si Ollama no está abierto
cd T:/Proyectos/Samu-Enjoyer
python scripts/eval_local.py generar --prueba A   # retoma desde la pregunta 20
python scripts/eval_local.py generar --prueba B
python scripts/eval_local.py juez --prueba A
python scripts/eval_local.py juez --prueba B
python scripts/eval_local.py reporte             # -> data/eval/reporte.json
```

Cada paso salta lo que ya está guardado. No borres `data/eval/entrega_*.jsonl` ni
`juez_*.jsonl`: son los checkpoints. Si una línea queda cortada por un apagón,
bórrala del final del archivo y relanza.

## Correcciones propuestas tras la evaluación parcial (cerradas de la prueba B)

Hallazgos: en 13/15 cerradas la norma de referencia llegó al top-10. Fallas: 308
(art. 11 de la Ley 1150 recuperado pero partido/truncado), 528 (cuantía en SMLMV sin
el valor del salario mínimo), 128 (clave probablemente errada: "Fintech").

Corpus y conversión:
1. Un artículo = un pasaje completo (no partir ni truncar; cajas de vigencia como metadatos).
2. Sentencias: partir por secciones (problema jurídico, consideraciones, resuelve);
   ignorar anclas de notas al pie y de índice (`ref_endnote`, `_Toc`) al segmentar.
3. Encabezado de cada pasaje con el nombre que reconoce `scripts/citations.py`
   (p. ej. "CPACA (Ley 1437 de 2011)", "Código Procesal del Trabajo"): si el extractor
   no reconoce la norma en el pasaje, la cita cuenta como sin respaldo.
4. Datos anuales: decretos de salario mínimo (DAPRE) y resoluciones de UVT (DIAN,
   como excepción al filtro de actos administrativos).
5. Priorizar en la recuperación por `vigencia`, `nivel` y tipo (norma/sentencia);
   marcar CPC y códigos derogados para que no compitan con los vigentes.
6. Los 7 tratados de derechos humanos pendientes y la deduplicación de texto copiado
   en leyes de reforma.

Sistema (lo que la prueba no tiene y la arquitectura sí): recuperación híbrida
(bge-m3 + BM25 + lookup) con RRF, reranker, consulta por opción, rewriter,
validador de citas + subagente de búsqueda, juez con segundo ciclo, razonamiento
activado y pasajes sin truncar.

### Resultados (sample_50, mini-corpus de 291 documentos, Qwen3-8B Q4 en local)

| Componente (pts) | A: sin corpus | B: con corpus |
|---|---|---|
| Cerradas (20) | 9/15 = 0,60 → 12,0 | 12/15 = 0,80 → 16,0 |
| Citas (20) | índice 0 (69 % sin respaldo) → 0 | índice 0,75 (1 % sin respaldo) → 15,0 |
| Abstención (10) | 5,6 | 8,4 |
| Texto libre, RAGAS emulado (30) | 0,49-0,50 → ~14,9 | 0,59 → ~17,7 |
| **Total automático (80)** | **~32,5** | **~57,1** |
| Normas citadas inexistentes en el corpus de 31k | 21/80 (26 %) | 0/91 |
| Correlación pertinencia aparente vs corrección (ρ) | −0,04 a +0,14 | −0,16 a −0,20 |

Juez de texto libre emulado (Qwen3-8B local + nomic/granite), no GLM: cifra aproximada. La
correlación con n = 35 no es significativa (|ρ| < 0,33). Faltan del sistema: recuperación
híbrida, reranker, consulta por opción, validador y juez con segundo ciclo.

## Revisión final de vacíos (2026-09-30)

- Las citas del `legal_basis` de las 50 preguntas de muestra, cruzadas a nivel de norma
  con `citations.py`, están todas en la lista maestra.
- Único hallazgo: el CPACA y el Código Procesal del Trabajo estaban, pero con otro
  `canonico` (`codigo_procedimiento_administrativo`, `codigo_procedimental_laboral`). Se
  cambió al nombre del evaluador (`cpaca`, `codigo_procesal_trabajo`) con
  `CANONICO_EVALUADOR` en `construir_targets.py`; el `doc_id` no cambia.
- **Decisión (usuario, 2026-09-30):** las ~460 leyes aprobatorias de tratados del nivel 1 se
  quedan todas; la recuperación (reranker) debe filtrar las que no aplican.
- Las 7 resoluciones de UVT (DIAN, `fuente_nueva`) no caían en ninguna tanda del `CLAUDE.md`:
  se agregó la tanda 6. Las tandas quedaron disjuntas y por servidor, para correrlas en
  paralelo; `Corpus.guardar` ahora une el manifest con el de disco (con bloqueo y escritura
  atómica). Probado con dos procesos simultáneos sobre la misma carpeta.

- **Limpieza (2026-09-30):** se borraron los archivos de las pruebas (`data/eval/`, mini-corpus,
  pasajes, respuestas y juicios, y `scripts/eval_local.py`). Los resultados quedan en la sección
  "Resultados" de arriba. Se conservan los scripts oficiales del reto en `scripts/`.

- **Descarga completa (2026-09-30):** 31.040 de 31.157 (99,6 %), 24,86 GB, auditada sin dañados ni
  repetidos. 117 fallas permanentes en origen (90 Corte Suprema, 26 Consejo de Estado, 1 Corte
  Constitucional). Detalle en `DESCARGA.md`. Listas del equipo movidas a `data/fuentes/`.
