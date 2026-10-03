import type { Pasaje } from "../../api/types";
import { FUENTES, type TipoFuente } from "../../config";

/** Tipo de fuente de un documento según el prefijo de su doc_id (ver data/corpus_targets.json). */
export function tipoDeFuente(docId: string): TipoFuente {
  if (docId.startsWith("constitucion")) return "constitucion";
  if (/^(codigo|estatuto)_/.test(docId)) return "codigo";
  if (/^(ley|acto)_/.test(docId)) return "ley";
  if (/^(decreto|resolucion|decision)_/.test(docId)) return "decreto";
  if (/^(jurisprudencia|csj)_/.test(docId)) return "jurisprudencia";
  return "otra";
}

export const colorDe = (p: Pasaje) => FUENTES[tipoDeFuente(p.doc_id)].color;

/** "codigo_general_proceso/art_42#2" -> "art. 42 (parte 2)"; "…/ficha" -> "ficha". */
export function etiquetaArticulo(chunkId?: string): string | undefined {
  const resto = chunkId?.split("/").slice(1).join("/");
  if (!resto) return undefined;
  const art = resto.match(/^art_([^#/]+)(?:#(\d+))?(\/notas)?/);
  if (art) return `art. ${art[1]}${art[2] ? ` (parte ${art[2]})` : ""}${art[3] ? " · notas" : ""}`;
  return resto.replace(/#/g, " ").replace(/_/g, " ");
}

/** Título corto del pasaje para listas: su encabezado, o doc_id + artículo. */
export const tituloPasaje = (p: Pasaje, i: number) =>
  p.titulo ?? ([p.doc_id, etiquetaArticulo(p.chunk_id)].filter(Boolean).join(" · ") || `Pasaje ${i + 1}`);

/** Normas derogadas o transitorias: se marcan para no leerlas como derecho vigente. */
export const noVigente = (vigencia?: string) => !!vigencia && /derog|transitori|inexequib/i.test(vigencia);
