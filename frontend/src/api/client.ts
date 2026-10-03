import { documentoDemo, preguntarDemo } from "./mock";
import type { CamposRespuesta, Documento, Formato, Pasaje, RespuestaAgente } from "./types";

export type * from "./types";

/** Modo demo salvo VITE_USE_MOCK=0 (ver .env.example). */
export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== "0";
const BACK_URL = import.meta.env.VITE_BACK_URL || "http://127.0.0.1:8000";

const FORMATOS: Formato[] = ["multiple_choice", "semi_open", "open_ended"];
const TEXTOS: (keyof CamposRespuesta)[] = [
  "justificacion",
  "respuesta",
  "referencia_legal",
  "marco_normativo",
  "analisis",
  "jurisprudencia",
  "conclusion",
];

const texto = (v: unknown) => (typeof v === "string" && v.trim() ? v : undefined);
const numero = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : undefined);

function parsePasaje(p: any): Pasaje | null {
  if (!p || typeof p !== "object" || !texto(p.texto)) return null;
  const chunkId = texto(p.chunk_id) ?? texto(p.id);
  const docId = texto(p.doc_id) ?? chunkId?.split("/")[0];
  if (!docId) return null;
  return {
    chunk_id: chunkId,
    doc_id: docId,
    texto: p.texto,
    score: numero(p.score),
    inicio: numero(p.inicio),
    fin: numero(p.fin),
    titulo: texto(p.titulo) ?? texto(p.encabezado),
    vigencia: texto(p.vigencia) ?? texto(p.metadatos?.vigencia),
    tipo_norma: texto(p.tipo_norma) ?? texto(p.metadatos?.tipo_norma),
  };
}

function parseCampos(d: any): CamposRespuesta {
  const out: CamposRespuesta = {};
  for (const k of TEXTOS) (out as any)[k] = texto(d?.[k]);
  if (["A", "B", "C", "D"].includes(d?.respuesta_correcta)) out.respuesta_correcta = d.respuesta_correcta;
  if (d?.descarte_opciones && typeof d.descarte_opciones === "object") out.descarte_opciones = d.descarte_opciones;
  if (Array.isArray(d?.palabras_clave)) out.palabras_clave = d.palabras_clave.filter((x: unknown) => texto(x));
  return out;
}

/** Valida la respuesta del back con tolerancia: solo `formato` es obligatorio. */
export function parseRespuesta(d: any): RespuestaAgente {
  if (!FORMATOS.includes(d?.formato)) throw new Error("Respuesta inesperada del back (falta «formato»).");
  return {
    ...parseCampos(d),
    id: numero(d.id),
    formato: d.formato,
    abstencion: Boolean(d.abstencion),
    pasajes_recuperados: Array.isArray(d.pasajes_recuperados)
      ? d.pasajes_recuperados.map(parsePasaje).filter((p: Pasaje | null): p is Pasaje => p !== null)
      : [],
    opciones: d.opciones && typeof d.opciones === "object" ? d.opciones : undefined,
    latencia_ms: numero(d.latencia_ms),
    borrador: d.borrador && typeof d.borrador === "object" ? parseCampos(d.borrador) : undefined,
  };
}

async function errorHttp(res: Response): Promise<Error> {
  let detalle = "";
  try {
    const body = await res.json();
    detalle = typeof body?.detail === "string" ? body.detail : "";
  } catch {}
  return new Error(`El back respondió HTTP ${res.status}${detalle ? `: ${detalle}` : ""}.`);
}

async function pedir(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (e) {
    if (init.signal?.aborted) throw e;
    throw new Error(`No se pudo conectar con el back local en ${BACK_URL}. ¿Está corriendo?`);
  }
}

/** Envía una pregunta al agente. Cancelable con `signal` (botón Detener). */
export async function preguntar(pregunta: string, signal: AbortSignal): Promise<RespuestaAgente> {
  if (USE_MOCK) return preguntarDemo(pregunta, signal);
  const res = await pedir("/api/preguntar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pregunta }),
    signal,
  });
  if (!res.ok) throw await errorHttp(res);
  return parseRespuesta(await res.json());
}

const cacheDocumentos = new Map<string, Documento>();

/** Documento completo del corpus, en caché por doc_id durante la sesión. */
export async function obtenerDocumento(docId: string, signal: AbortSignal): Promise<Documento> {
  const cached = cacheDocumentos.get(docId);
  if (cached) return cached;
  let doc: Documento;
  if (USE_MOCK) {
    doc = await documentoDemo(docId, signal);
  } else {
    const res = await pedir(`/api/documentos/${encodeURIComponent(docId)}`, {
      headers: { Accept: "application/json" },
      signal,
    });
    if (res.status === 404) throw new Error(`No se encontró el documento «${docId}» en el corpus.`);
    if (!res.ok) throw await errorHttp(res);
    const d = await res.json();
    if (typeof d?.markdown !== "string") throw new Error("Respuesta inesperada del back (falta «markdown»).");
    doc = {
      doc_id: texto(d.doc_id) ?? docId,
      titulo: texto(d.titulo),
      tipo_norma: texto(d.tipo_norma),
      numero: texto(d.numero) ?? (numero(d.numero) !== undefined ? String(d.numero) : undefined),
      anio: texto(d.anio) ?? numero(d.anio),
      vigencia: texto(d.vigencia),
      fuente: texto(d.fuente),
      markdown: d.markdown,
    };
  }
  cacheDocumentos.set(docId, doc);
  return doc;
}
