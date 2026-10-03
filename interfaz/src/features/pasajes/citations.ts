import type { Pasaje } from "../../api/types";

/**
 * El escritor cita con IDs canónicos entre corchetes: [codigo_general_proceso/art_42], también con
 * parte (#2), notas (/notas), fichas de sentencias (…/ficha) o varios IDs en un corchete separados por
 * comas o punto y coma. Este módulo cambia cada ID por un número clicable [n](#pasaje-n), donde n es la
 * posición del pasaje en "Pasajes recuperados" (así coincide con la lista bajo la respuesta).
 * Un ID cuyo pasaje no está en la lista se deja como texto (no debería pasar: el validador lo suprime).
 */

const ID = /[a-z0-9][a-z0-9_.\-]*\/[^\s,;\]\[]+/gi;
const BRACKET = /\[([^\[\]]+)\]/g;

/** Índice del pasaje con ese chunk_id; si no, el primero de ese artículo (sin #parte) o de ese doc_id. */
function indiceDe(id: string, pasajes: Pasaje[]): number {
  const exacto = pasajes.findIndex((p) => p.chunk_id === id);
  if (exacto >= 0) return exacto;
  const base = id.replace(/#.*$/, "");
  return pasajes.findIndex((p) => p.chunk_id?.replace(/#.*$/, "") === base);
}

export function conCitasNumeradas(texto: string, pasajes: Pasaje[]): string {
  return texto.replace(BRACKET, (todo, dentro: string) => {
    const ids = dentro.match(ID);
    if (!ids || dentro.replace(ID, "").replace(/[\s,;y]/g, "") !== "") return todo;
    const numeros = [...new Set(ids.map((id) => indiceDe(id, pasajes)).filter((i) => i >= 0))].sort((a, b) => a - b);
    if (!numeros.length) return todo;
    return numeros.map((i) => `[${i + 1}](#pasaje-${i + 1})`).join("");
  });
}

/** Texto para el portapapeles: los enlaces de cita quedan como [1], [2]… */
export const sinEnlacesDeCita = (texto: string) => texto.replace(/\[(\d+)\]\(#pasaje-\d+\)/g, "[$1]");
