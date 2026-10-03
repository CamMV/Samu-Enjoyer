import { motion } from "motion/react";
import type { Pasaje } from "../../api/types";
import { FUENTES } from "../../config";
import { cn } from "../../lib/utils";
import { colorDe, noVigente, tipoDeFuente, tituloPasaje } from "./passages";

/**
 * "Pasajes recuperados": los 10 pasajes que respaldan la respuesta, en el orden de la recuperación,
 * coloreados por tipo de fuente. Cada uno abre su detalle (y desde ahí el documento completo).
 */
export function PassageList({
  pasajes,
  activo,
  onOpen,
}: {
  pasajes: Pasaje[];
  /** índice del pasaje abierto en la ventana flotante, si es de este mensaje */
  activo: number | null;
  onOpen: (index: number) => void;
}) {
  const tipos = [...new Set(pasajes.map((p) => tipoDeFuente(p.doc_id)))];
  return (
    <div className="mt-5 flex flex-col gap-1.5">
      <span className="font-medium text-[11px] text-muted-foreground uppercase tracking-wide">
        Pasajes recuperados ({pasajes.length})
      </span>
      <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1">
        {tipos.map((t) => (
          <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground" key={t}>
            <span className="size-2 rounded-full" style={{ backgroundColor: FUENTES[t].color }} />
            {FUENTES[t].nombre}
          </span>
        ))}
      </div>
      {pasajes.map((p, i) => {
        const color = colorDe(p);
        return (
          <motion.button
            animate={{ opacity: 1, x: 0 }}
            className={cn(
              "flex w-full items-start gap-3 rounded-xl border px-3 py-2 text-left transition-colors hover:bg-muted",
              activo === i ? "border-primary/50 bg-muted" : "border-border/50 bg-card/40"
            )}
            initial={{ opacity: 0, x: -8 }}
            key={p.chunk_id ?? i}
            onClick={() => onOpen(i)}
            style={{ borderLeftColor: color, borderLeftWidth: 4 }}
            transition={{ delay: 0.04 * i, duration: 0.25 }}
            type="button"
          >
            <span className="mt-0.5 font-mono font-semibold text-[11px]" style={{ color }}>
              [{i + 1}]
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium text-[12px]">{tituloPasaje(p, i)}</span>
              <span className="block truncate font-mono text-[10px] text-muted-foreground">
                {p.chunk_id ?? p.doc_id}
                {p.score !== undefined && ` · score ${p.score.toFixed(3)}`}
                {noVigente(p.vigencia) && <span className="text-destructive"> · {p.vigencia}</span>}
              </span>
              <span className="mt-0.5 line-clamp-2 text-[12px] text-muted-foreground">{p.texto}</span>
            </span>
          </motion.button>
        );
      })}
    </div>
  );
}
