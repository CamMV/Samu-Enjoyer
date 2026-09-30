# Entregables — Hackathon IA Week 2026

Lista de control según el enunciado (secciones 6, 7 y 9). Las plantillas oficiales
vienen en la carpeta `entregables/` del material del reto: cuando las tengamos, van
aquí junto a este archivo.

## 1. Viernes 2 de octubre, 17:00 — por correo

| # | Entregable | Formato | Estado |
|---|---|---|---|
| 1 | Reporte de avance de **una página**: puntaje sobre las 50 preguntas de muestra (`scripts/evaluate.py --split sample`), estado del corpus y riesgos | PDF adjunto a rf.manrique@uniandes.edu.co, asunto `[Hackathon 2026] Avance — <nombre del equipo>` | pendiente |

## 2. Sábado 3 de octubre, 15:00 — en el repositorio

| # | Entregable | Dónde | Puntos | Estado |
|---|---|---|---|---|
| 2 | README con dependencias, arquitectura y **comando único de reproducción** (se prueba en contenedor limpio sobre las 50 de muestra) | raíz del repo | 2 | pendiente |
| 3 | `submissions.jsonl`: las 992 respuestas según `schema/submission.schema.json` | repo | 80 (automático) | pendiente |
| 4 | `CORPUS.md` (Inventario, Criterio, Método) y `corpus_manifest.json` en la raíz del corpus | repo | 5 | pendiente |
| 5 | Corpus procesado + **índice vectorial serializado** + `LICENSE`, en un comprimido en la nube (descarga sin permiso, activo 30 días); enlace en la sección **"Corpus e índice"** del README | nube + README | (dentro de los 5) | pendiente |
| 6 | Informe técnico de máximo 3 páginas: arquitectura, encoder y decoder, resultados sobre la muestra, limitaciones | repo | — | pendiente |
| 7 | Video de máximo 5 minutos | repo o enlace | 3 | pendiente |
| 8 | Interfaz gráfica con la identidad visual de Software Colombia: consulta de extremo a extremo, pasajes recuperados y normas citadas | repo | 10 | pendiente |

## 3. Sábado 15:00-17:00 — verificación en vivo

El jurado regenera 2 o 3 preguntas ya entregadas: deben coincidir las normas citadas y los
pasajes recuperados. El índice queda congelado al entregar. Temperatura 0, sistema determinista.

## Reglas que descalifican

- Modelos cerrados en cualquier componente (generación, reformulación, reranking, datos sintéticos).
- Editar respuestas a mano después de la ejecución.
- Indexar el banco de preguntas o material con respuestas (incluida `data/sample_50.jsonl`).
- No reproducir en la verificación en vivo.
