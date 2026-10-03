// ─── Textos de la interfaz ──────────────────────────────────────────────────

export const APP_NAME = "Samu-Enjoyer";

export const APP_TAGLINE =
  "Preguntas de derecho colombiano respondidas solo con normas y sentencias de nuestro corpus. Cada respuesta muestra los 10 pasajes recuperados que la respaldan.";

export const APP_CREDIT = "Hackathon IA Week 2026";

export const GREETING_TITLE = "¿Qué pregunta jurídica quieres resolver?";

export const INPUT_PLACEHOLDER = "Escribe tu pregunta jurídica…";

// Preguntas de ejemplo en la pantalla vacía (tomadas de data/sample_50.jsonl). Lista vacía = ocultas.
export const SUGGESTIONS = [
  "¿Qué normativa regula las actuaciones jurisdiccionales adelantadas ante la SIC? A) Ley 1564 de 2012 B) Ley 270 de 1996 C) Ley 472 de 1998 D) Ley 906 de 2004",
  "¿Cuáles son los elementos esenciales para la validez de un contrato?",
  "¿En qué casos procede la acción de grupo y qué la distingue de la acción popular?",
  "Un trabajador sufre un accidente camino a casa en el transporte de la empresa. ¿Es accidente de trabajo?",
];

// Etapas que se muestran mientras el agente trabaja (el back responde todo de una vez).
export const STAGES = [
  "Detectando el formato de la pregunta…",
  "Buscando en el corpus (BM25 + embeddings)…",
  "Reordenando pasajes con el reranker…",
  "Redactando la respuesta con Qwen3-8B…",
  "Validando que cada cita esté en los pasajes…",
];

// ─── Tipos de fuente: cada pasaje se colorea según su documento ─────────────
// Se deducen del prefijo del doc_id (ver tipoDeFuente en features/pasajes/passages.ts).
// Tonos de la familia cian-violeta del logo; sin rojo/verde/ámbar para que el color no se lea como "bueno/malo".
export type TipoFuente = "constitucion" | "codigo" | "ley" | "decreto" | "jurisprudencia" | "otra";

export const FUENTES: Record<TipoFuente, { nombre: string; color: string }> = {
  constitucion: { nombre: "Constitución", color: "oklch(0.74 0.13 205)" },
  codigo: { nombre: "Códigos y estatutos", color: "oklch(0.66 0.15 240)" },
  ley: { nombre: "Leyes y actos legislativos", color: "oklch(0.64 0.15 275)" },
  decreto: { nombre: "Decretos y resoluciones", color: "oklch(0.64 0.15 310)" },
  jurisprudencia: { nombre: "Jurisprudencia", color: "oklch(0.68 0.14 345)" },
  otra: { nombre: "Otras fuentes", color: "oklch(0.62 0.03 220)" },
};
