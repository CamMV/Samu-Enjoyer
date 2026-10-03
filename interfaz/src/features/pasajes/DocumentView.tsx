import { Crosshair } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { Documento, Pasaje } from "../../api/types";
import { Markdown } from "../../components/ui/Markdown";
import { FUENTES } from "../../config";
import { clearHighlight, locateChunk, scrollToRange, setHighlight, supportsHighlight } from "./highlight";
import { colorDe, noVigente, tipoDeFuente } from "./passages";

/** Cabecera del documento completo: tipo de fuente (con color), número, año, vigencia y fuente. */
function DocumentMeta({ doc }: { doc: Documento }) {
  const tipo = tipoDeFuente(doc.doc_id);
  const color = FUENTES[tipo].color;
  const items = [
    doc.tipo_norma,
    doc.numero && `n.º ${doc.numero}`,
    doc.anio && `año ${doc.anio}`,
    doc.fuente,
  ].filter(Boolean);
  return (
    <div className="flex flex-col gap-2">
      {doc.titulo && <h2 className="font-semibold text-base">{doc.titulo}</h2>}
      <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
        <span
          className="rounded-full border px-2.5 py-0.5 font-medium"
          style={{
            color,
            backgroundColor: `color-mix(in oklch, ${color} 14%, transparent)`,
            borderColor: `color-mix(in oklch, ${color} 45%, transparent)`,
          }}
        >
          {FUENTES[tipo].nombre}
        </span>
        {doc.vigencia && (
          <span
            className={
              noVigente(doc.vigencia)
                ? "rounded-md bg-destructive/15 px-2 py-0.5 text-destructive"
                : "rounded-md bg-primary/15 px-2 py-0.5 text-primary"
            }
          >
            {doc.vigencia}
          </span>
        )}
        {items.map((t, i) => (
          <span className="rounded-md bg-muted px-2 py-0.5" key={i}>
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * Markdown del documento con el pasaje abierto ubicado, resaltado y desplazado a la vista.
 * Si el pasaje trae `inicio`, se usa como pista de posición cuando su texto aparece varias veces.
 * Una barra fija arriba lo indica y permite volver a él.
 */
export function DocumentView({ doc, pasaje, index }: { doc: Documento; pasaje: Pasaje; index: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const rangeRef = useRef<Range | null>(null);
  const [status, setStatus] = useState<"found" | "missing" | "unsupported">("missing");
  const [occurrences, setOccurrences] = useState(1);
  const color = colorDe(pasaje);

  useEffect(() => {
    rangeRef.current = null;
    if (!supportsHighlight()) return setStatus("unsupported");
    const hint = pasaje.inicio !== undefined && doc.markdown.length ? Math.min(1, pasaje.inicio / doc.markdown.length) : undefined;
    const located = ref.current ? locateChunk(ref.current, pasaje.texto, hint) : null;
    if (!located) {
      clearHighlight();
      return setStatus("missing");
    }
    const { range } = located;
    setOccurrences(located.occurrences);
    rangeRef.current = range;
    setHighlight(range);
    setStatus("found");
    // deja que el layout se asiente antes de desplazar
    const t = setTimeout(() => scrollToRange(range), 60);
    return () => {
      clearTimeout(t);
      clearHighlight();
    };
  }, [pasaje, doc]);

  const message = {
    found:
      `Pasaje ${index + 1} resaltado en el documento` +
      (occurrences > 1 ? ` · el texto aparece ${occurrences} veces, se marcó el más cercano a su posición` : ""),
    missing: "No se pudo ubicar este pasaje dentro del documento.",
    unsupported: "Este navegador no permite resaltar el pasaje dentro del documento.",
  }[status];

  return (
    <>
      <DocumentMeta doc={doc} />
      <div className="sticky top-0 z-10 -mx-4 flex items-center justify-between gap-3 border-y border-border/40 bg-background/95 px-4 py-2 text-[12px] backdrop-blur">
        <span className="flex items-center gap-2 text-muted-foreground">
          {status === "found" && (
            <span className="size-3 rounded-sm" style={{ backgroundColor: `color-mix(in oklch, ${color} 55%, transparent)` }} />
          )}
          {message}
        </span>
        {status === "found" && (
          <button
            className="flex shrink-0 items-center gap-1.5 rounded-md border border-border px-2 py-1 hover:bg-muted"
            onClick={() => rangeRef.current && scrollToRange(rangeRef.current)}
            type="button"
          >
            <Crosshair className="size-3.5" />
            Ir al pasaje
          </button>
        )}
      </div>
      <div ref={ref} style={{ "--hl-color": color } as React.CSSProperties}>
        <Markdown>{doc.markdown}</Markdown>
      </div>
    </>
  );
}
