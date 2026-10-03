/**
 * ─── CONTRATO CON EL BACK LOCAL (implementado en src/api/server.py) ─────────────────────────────
 *
 * GET  /api/salud            200 → { ok, modo: "real" | "mock", llm, chunks_sqlite, ocupado }
 *
 * POST /api/preguntar        body: { "pregunta": "texto libre" }
 *   Opcionales: id, formato, opciones, area, tema, complejidad, sub_tarea (un item del banco tal cual).
 *   Sin `opciones`, el back separa las de una cerrada escrita en el texto ("… A) … B) … C) … D) …").
 *   200 → RespuestaAgente: el registro de LegalAgent.to_submission (schema/submission.schema.json)
 *         con los pasajes enriquecidos (chunk_id, titulo, vigencia, tipo_norma), `opciones` en las
 *         cerradas, `latencia_ms` y `borrador` = los mismos campos antes de reescribir las citas, con
 *         los IDs canónicos [doc_id/art_N]: el front numera las citas y las enlaza a sus pasajes.
 *   422 → body inválido · 500 → el agente falló. Errores: { "detail": "mensaje" }
 *
 * GET /api/documentos/{doc_id}
 *   200 → Documento (front-matter + Markdown de corpus/md/<doc_id>.md; si no está, sus chunks en orden)
 *   404 → doc_id desconocido
 *
 * El front valida con tolerancia: solo `formato` es obligatorio; lo que no llegue no se muestra.
 */

export type Formato = "multiple_choice" | "semi_open" | "open_ended";

/** Un pasaje de `pasajes_recuperados` (los 10 que respaldan la respuesta, en orden). */
export type Pasaje = {
  /** ID canónico: <doc_id>/art_<N>, <doc_id>/art_<N>#<parte>, <doc_id>/ficha… */
  chunk_id?: string;
  doc_id: string;
  texto: string;
  score?: number;
  /** offsets de carácter del pasaje en el documento del corpus */
  inicio?: number;
  fin?: number;
  /** encabezado citable del pasaje ("Artículo 42. Código General del Proceso (Ley 1564 de 2012)") */
  titulo?: string;
  vigencia?: string;
  tipo_norma?: string;
};

/** Campos de respuesta que puede traer el registro según el formato. */
export type CamposRespuesta = {
  // cerradas
  respuesta_correcta?: "A" | "B" | "C" | "D" | null;
  justificacion?: string;
  descarte_opciones?: Record<string, string>;
  // semiabiertas
  respuesta?: string;
  palabras_clave?: string[];
  referencia_legal?: string;
  // abiertas (IRAC)
  marco_normativo?: string;
  analisis?: string;
  jurisprudencia?: string;
  conclusion?: string;
};

export type RespuestaAgente = CamposRespuesta & {
  id?: number;
  formato: Formato;
  abstencion: boolean;
  pasajes_recuperados: Pasaje[];
  /** opciones A-D detectadas en la pregunta (cerradas) */
  opciones?: Record<string, string>;
  latencia_ms?: number;
  borrador?: CamposRespuesta;
};

/** Documento completo del corpus. */
export type Documento = {
  doc_id: string;
  titulo?: string;
  tipo_norma?: string;
  numero?: string;
  anio?: number | string;
  vigencia?: string;
  fuente?: string;
  markdown: string;
};
