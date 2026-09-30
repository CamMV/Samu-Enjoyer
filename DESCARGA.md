# Descarga del corpus en este PC — cómo parar y retomar

Descarga de los 31.157 documentos de `data/corpus_targets.json` a `corpus/raw/`
(disco T, ~13-26 GB). Corre en 4 carriles paralelos, uno por servidor, desacoplados
de la terminal.

## Órdenes (desde la raíz del repo)

```bash
python scraper/descargar.py estado
```
Avance por carril, fallas, GB en disco y horas restantes (el ritmo sale de comparar con el `estado` anterior).

```bash
python scraper/descargar.py parar
```
**Antes de suspender o mover el PC.** Parada limpia: cada carril termina lo que tiene en curso, guarda y sale (1-2 min).

```bash
python scraper/descargar.py iniciar
```
**Al volver.** Relanza lo que no esté corriendo. Lo ya descargado se salta y las fallas se reintentan.

- Si no hay tiempo para la parada limpia: `python scraper/descargar.py parar --forzar`
  (se pierde como mucho lo de los últimos 2 minutos, que se vuelve a bajar).
- Si el PC se suspendió sin parar: al despertar, correr `estado`. Si algún carril
  aparece detenido o con muchas fallas de red, correr `iniciar`.

## Carriles

| Carril | Qué baja | Docs |
|---|---|---|
| A | Senado/Colpensiones: núcleo (seed, enriquecimiento, muestra) → nivel 1 → UVT DIAN | 8.776 |
| B | Corte Constitucional C, SU y T | 10.794 |
| C | Corte Suprema | 7.946 |
| D | Presidencia → Consejo de Estado | 3.641 |

## Dónde está cada cosa

- `corpus/raw/<doc_id>/…` documentos; `corpus/raw/corpus_manifest.json` registro (estado, url, fecha).
- `corpus/descarga/log_X.txt` log de cada carril; `carril_X.json` paso y procesos.
- `corpus/PARAR` existe mientras hay una parada pedida (`iniciar` lo borra).
- Todo `corpus/raw/` está fuera de git.

## Bitácora de checkpoints

| Fecha y hora | Evento | Total ok | Nota |
|---|---|---|---|
| 2026-09-30 00:34 | Antes de lanzar | 291 / 31.157 | 291 documentos de las pruebas (mini-corpus) se reutilizan |
| 2026-09-30 00:34 | Lanzamiento de los 4 carriles | 291 | |
| 2026-09-30 00:37 | Prueba de `parar` (40 s) | 6.311 | Parada limpia OK, nada perdido |
| 2026-09-30 00:40 | `iniciar` otra vez | 6.311 | Corregida la extensión .doc/.docx de la Corte Suprema |
| 2026-09-30 00:44 | Carriles A, C y D cerrados a mano | 17.877 | Nada perdido |
| 2026-09-30 00:47 | `iniciar` (ahora por WMI, sin ventanas) | 17.877 | Retoma sin repetir |
| 2026-09-30 01:05 | A, B y D murieron al guardar (manifest leído por `estado`); corregido y relanzado | 22.348 | Lo no guardado se vuelve a bajar |
| 2026-09-30 01:23 | Descarga terminada | 31.037 | 117 fallas permanentes; el reintento no recupera ninguna |
| 2026-09-30 02:30 | Auditoría con `--arreglar` | 31.037 | 0 dañados, 0 repetidos, 51 .doc renombrados a .docx |

## Resultado final

**31.040 de 31.157 documentos (99,6 %)**: 31.037 ok + 3 duplicados (mismo contenido que otro
doc_id). 32.348 archivos, 24,86 GB. Detalle en `corpus/descarga/auditoria.json`.

- **117 fallas, todas `NoEncontrado` en la fuente oficial** (no hay que buscarlas en fuentes no
  oficiales): 90 de la Corte Suprema (su buscador ya no las encuentra), 26 del Consejo de Estado (el
  servidor devuelve el archivo vacío) y 1 de la Corte Constitucional (SU-163/23 no publicada).
- **Integridad:** ningún archivo truncado ni dañado. Los PDF de Función Pública no traen `%%EOF`,
  pero abren completos (terminan con su pie de creación).
- **Normas del Senado:** todas con sus cajas de concordancias incrustadas. 5 tienen anclas mal
  escritas en el propio Senado (`ley_734_2002`, `acto_legislativo_1_1999`, `decreto_663_1993`,
  `ley_294_1996`, `ley_701_2001`), pero el texto de esos artículos está: no falta contenido.

Para volver a auditar: `python scraper/auditar_descarga.py` (solo lectura, ~25 min).

---

# Conversión a Markdown en este PC — cómo parar y retomar

Convierte `corpus/raw` (31.037 documentos) a `corpus/md/<doc_id>.md` con el entorno conda
`IA` (Python 3.12, LibreOffice y Tesseract dentro del entorno). Corre en segundo plano,
desacoplada de la terminal, con un proceso por núcleo.

```bash
C:/Users/santi/anaconda3/envs/IA/python.exe -m src.ingest.convertir --estado
```
Avance (.md hechos de 31.037) y últimas líneas del log.

```bash
C:/Users/santi/anaconda3/envs/IA/python.exe -m src.ingest.convertir --parar
```
**Antes de suspender o mover el PC.** Termina los documentos en curso y guarda (1-3 min).

```bash
C:/Users/santi/anaconda3/envs/IA/python.exe -m src.ingest.convertir --fondo --hilos 14
```
**Al volver.** Retoma: los .md cuyo origen no cambió se saltan.

- Log: `corpus/md/_control/log.txt`. Manifest del corpus convertido (se guarda cada 200
  documentos o 2 minutos): `corpus/md/corpus_manifest.json`.
- Si el PC se suspende sin parar, la conversión se pausa y sigue al despertar; si se
  reinició, correr `--fondo` otra vez.
- Auditoría al terminar: `python -m src.ingest.auditar_muestra --estratificar --n 100`.

## Bitácora de la conversión

| Fecha y hora | Evento | .md | Nota |
|---|---|---|---|
| 2026-09-30 03:42 | Lanzamiento (14 procesos) | 0 | Tras pruebas: 48 docs de muestra, auditoría 43 OK / 5 revisar / 0 falla |
| 2026-09-30 06:44 | Parada limpia (el usuario mueve el PC) | 19.846 | Manifest completo; retomar con --fondo --hilos 14 |
| 2026-09-30 11:35 | Reanudación (--fondo --hilos 14) | 19.846 | |
| 2026-09-30 11:58 | Conversión completa: 31.037 .md. Reconversión de los 10.788 PDF (--forzar --lista) | 31.037 | Palabras pegadas en capas OCR (propia y de la Corte) |
| 2026-09-30 15:13 | Reconversión de PDF terminada (palabras pegadas: ~1.580 -> 490 docs). Relectura con OCR de 588 docs con capa de texto ilegible de la Corte | 31.037 | |
| 2026-09-30 17:07 | Relectura con OCR terminada (588 docs). Palabras pegadas: 0 en todos los PDF; 64 docs de la Corte Suprema con restos de otros alfabetos. Auditoría de 100 (estratificada): 91 OK, 8 revisar, 1 falla (ley aprobatoria de tratado) | 31.037 | Conversión cerrada |
