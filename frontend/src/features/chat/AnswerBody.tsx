import { CircleSlash } from "lucide-react";
import { motion } from "motion/react";
import type { ReactNode } from "react";
import type { CamposRespuesta, RespuestaAgente } from "../../api/types";
import { Markdown } from "../../components/ui/Markdown";
import { cn } from "../../lib/utils";
import { conCitasNumeradas } from "../pasajes/citations";
import { colorDe } from "../pasajes/passages";

export const FORMATO_NOMBRE = {
  multiple_choice: "Opción múltiple",
  semi_open: "Semiabierta",
  open_ended: "Abierta · IRAC",
} as const;

/** Un bloque de la respuesta que "se ensambla" al aparecer (entra escalonado, como los cubos del logo). */
function Bloque({ i, titulo, children, className }: { i: number; titulo?: string; children: ReactNode; className?: string }) {
  return (
    <motion.section
      animate={{ opacity: 1, y: 0, scale: 1, rotateX: 0 }}
      className={cn("rounded-xl border border-glow/25 bg-card/50 p-3.5 shadow-[0_0_18px_-10px_var(--glow)]", className)}
      initial={{ opacity: 0, y: 14, scale: 0.96, rotateX: -12 }}
      transition={{ delay: 0.12 * i, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
    >
      {titulo && (
        <h4 className="mb-1.5 flex items-center gap-2 font-medium text-[11px] text-glow uppercase tracking-wide">
          <span className="grid size-4 place-items-center rounded-[4px] bg-glow/15 font-mono text-[10px]">{i + 1}</span>
          {titulo}
        </h4>
      )}
      {children}
    </motion.section>
  );
}

/**
 * Cuerpo de una respuesta del agente según su formato: cerrada (letra + justificación + descarte),
 * semiabierta (respuesta + palabras clave + referencia legal) o abierta (IRAC). Si llega el `borrador`
 * con IDs canónicos, sus citas se vuelven números que abren el pasaje correspondiente.
 */
export function AnswerBody({ r, onCitation }: { r: RespuestaAgente; onCitation: (index: number) => void }) {
  const pasajes = r.pasajes_recuperados;
  // Texto a mostrar de un campo: el del borrador (con citas numeradas) si existe, si no el de la entrega.
  const campo = (k: keyof CamposRespuesta) => {
    const b = r.borrador?.[k];
    if (typeof b === "string" && b.trim()) return conCitasNumeradas(b, pasajes);
    const v = r[k];
    return typeof v === "string" ? v : undefined;
  };
  const md = (texto: string) => (
    <Markdown citationColor={(i) => (pasajes[i] ? colorDe(pasajes[i]) : undefined)} onCitation={onCitation}>
      {texto}
    </Markdown>
  );

  const bloques: { titulo?: string; contenido: ReactNode; className?: string }[] = [];

  if (r.abstencion) {
    bloques.push({
      contenido: (
        <div className="flex items-start gap-2 text-[13px]">
          <CircleSlash className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          El corpus no da fundamento suficiente para responder esta pregunta: el agente se abstiene en vez de
          inventar o citar normas que no recuperó.
        </div>
      ),
    });
  }

  if (r.formato === "multiple_choice" && r.respuesta_correcta) {
    const letra = r.respuesta_correcta;
    bloques.push({
      titulo: "Respuesta",
      contenido: (
        <div className="flex items-center gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-glow/20 font-bold text-glow text-xl shadow-[0_0_16px_-4px_var(--glow)]">
            {letra}
          </span>
          {r.opciones?.[letra] && <span className="text-[13px]">{r.opciones[letra]}</span>}
        </div>
      ),
    });
    const j = campo("justificacion");
    if (j) bloques.push({ titulo: "Justificación", contenido: md(j) });
    const descartes = Object.entries(r.descarte_opciones ?? {}).sort(([a], [b]) => a.localeCompare(b));
    if (descartes.length)
      bloques.push({
        titulo: "Opciones descartadas",
        contenido: (
          <ul className="flex flex-col gap-1.5 text-[13px]">
            {descartes.map(([l, razon]) => (
              <li className="flex gap-2" key={l}>
                <span className="font-mono font-semibold text-muted-foreground">{l}</span>
                <span className="text-muted-foreground">{razon}</span>
              </li>
            ))}
          </ul>
        ),
      });
  }

  if (r.formato === "semi_open") {
    const resp = campo("respuesta");
    if (resp) bloques.push({ titulo: "Respuesta", contenido: md(resp) });
    if (r.palabras_clave?.length)
      bloques.push({
        titulo: "Palabras clave",
        contenido: (
          <div className="flex flex-wrap gap-1.5">
            {r.palabras_clave.map((p) => (
              <span className="rounded-full border border-glow/30 bg-glow/10 px-2.5 py-0.5 text-[12px]" key={p}>
                {p}
              </span>
            ))}
          </div>
        ),
      });
    const ref = campo("referencia_legal");
    if (ref) bloques.push({ titulo: "Referencia legal", contenido: md(ref) });
  }

  if (r.formato === "open_ended") {
    const irac: [keyof CamposRespuesta, string][] = [
      ["marco_normativo", "Problema y regla"],
      ["analisis", "Análisis"],
      ["jurisprudencia", "Jurisprudencia"],
      ["conclusion", "Conclusión"],
    ];
    for (const [k, titulo] of irac) {
      const t = campo(k);
      if (t) bloques.push({ titulo, contenido: md(t) });
    }
  }

  return (
    <div className="flex flex-col gap-2.5" style={{ perspective: 800 }}>
      {bloques.map((b, i) => (
        <Bloque className={b.className} i={i} key={i} titulo={b.titulo}>
          {b.contenido}
        </Bloque>
      ))}
    </div>
  );
}

/** Texto plano de la respuesta para el portapapeles (los campos de la entrega, sin numeración). */
export function textoCopiable(r: RespuestaAgente): string {
  const partes: string[] = [];
  if (r.respuesta_correcta) partes.push(`Respuesta: ${r.respuesta_correcta}${r.opciones?.[r.respuesta_correcta] ? ` — ${r.opciones[r.respuesta_correcta]}` : ""}`);
  for (const k of ["justificacion", "respuesta", "marco_normativo", "analisis", "jurisprudencia", "conclusion", "referencia_legal"] as const) {
    if (r[k]) partes.push(r[k] as string);
  }
  return partes.join("\n\n");
}
