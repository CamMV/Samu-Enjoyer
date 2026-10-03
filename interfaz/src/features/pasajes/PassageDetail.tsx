import { AlertTriangle, ArrowLeft, FileText, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { obtenerDocumento } from "../../api/client";
import type { Documento, Pasaje } from "../../api/types";
import { FUENTES } from "../../config";
import { DocumentView } from "./DocumentView";
import { colorDe, etiquetaArticulo, noVigente, tipoDeFuente } from "./passages";

type DocState =
  | { status: "closed" }
  | { status: "loading" }
  | { status: "ready"; doc: Documento }
  | { status: "error"; message: string };

/**
 * Todo lo que se sabe de un pasaje recuperado: su texto y sus metadatos (ID canónico, vigencia, score,
 * posición). "Ver documento completo" carga el documento del corpus (obtenerDocumento) y lo muestra en su
 * lugar con el pasaje resaltado; "Volver al pasaje" regresa.
 */
export function PassageDetail({ pasaje, index }: { pasaje: Pasaje; index: number }) {
  const [doc, setDoc] = useState<DocState>({ status: "closed" });
  const abortRef = useRef<AbortController | null>(null);

  // Otro pasaje (o ventana cerrada): de vuelta a la vista del pasaje, sin peticiones pendientes.
  useEffect(() => {
    setDoc({ status: "closed" });
    return () => abortRef.current?.abort();
  }, [pasaje]);

  const openDocument = () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setDoc({ status: "loading" });
    obtenerDocumento(pasaje.doc_id, controller.signal).then(
      (d) => !controller.signal.aborted && setDoc({ status: "ready", doc: d }),
      (e) =>
        !controller.signal.aborted &&
        setDoc({ status: "error", message: e instanceof Error ? e.message : "Error desconocido" })
    );
  };

  if (doc.status !== "closed") {
    return (
      <div className="flex flex-col gap-4 p-4">
        <button
          className="flex w-fit items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground"
          onClick={() => setDoc({ status: "closed" })}
          type="button"
        >
          <ArrowLeft className="size-4" />
          Volver al pasaje
        </button>
        <div className="font-mono text-[11px] text-muted-foreground">{pasaje.doc_id}</div>
        {doc.status === "loading" && (
          <div className="flex items-center gap-2 text-muted-foreground text-sm">
            <Loader2 className="size-4 animate-spin" />
            Cargando documento…
          </div>
        )}
        {doc.status === "error" && (
          <div className="flex flex-col items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-destructive text-sm">
            {doc.message}
            <button className="underline" onClick={openDocument} type="button">
              Reintentar
            </button>
          </div>
        )}
        {doc.status === "ready" && <DocumentView doc={doc.doc} index={index} pasaje={pasaje} />}
      </div>
    );
  }

  const tipo = tipoDeFuente(pasaje.doc_id);
  const color = colorDe(pasaje);
  const entries: [string, string | undefined][] = [
    ["chunk_id", pasaje.chunk_id],
    ["doc_id", pasaje.doc_id],
    ["artículo", etiquetaArticulo(pasaje.chunk_id)],
    ["tipo de norma", pasaje.tipo_norma],
    ["vigencia", pasaje.vigencia],
    ["score", pasaje.score?.toFixed(3)],
    ["posición", pasaje.inicio !== undefined && pasaje.fin !== undefined ? `caracteres ${pasaje.inicio}–${pasaje.fin}` : undefined],
  ];

  return (
    <div className="flex flex-col gap-5 p-4">
      <span
        className="flex w-fit items-center gap-2 rounded-full border px-3 py-1 font-medium text-[12px]"
        style={{
          color,
          backgroundColor: `color-mix(in oklch, ${color} 14%, transparent)`,
          borderColor: `color-mix(in oklch, ${color} 45%, transparent)`,
        }}
      >
        {FUENTES[tipo].nombre}
      </span>

      {noVigente(pasaje.vigencia) && (
        <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-[12px] text-destructive">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          Norma marcada como «{pasaje.vigencia}»: no debe leerse como derecho vigente.
        </div>
      )}

      <section>
        <h3 className="mb-2 font-medium text-[11px] text-muted-foreground uppercase tracking-wide">
          Texto del pasaje {index + 1}
        </h3>
        <div className="whitespace-pre-wrap break-words rounded-xl border border-border/50 bg-card/40 p-3 text-[13px] leading-relaxed">
          {pasaje.texto}
        </div>
      </section>

      <section>
        <h3 className="mb-2 font-medium text-[11px] text-muted-foreground uppercase tracking-wide">Información</h3>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 rounded-xl border border-border/50 p-3 text-[13px]">
          {entries
            .filter(([, v]) => v !== undefined)
            .map(([k, v]) => (
              <div className="contents" key={k}>
                <dt className="font-mono text-[12px] text-muted-foreground">{k}</dt>
                <dd className="min-w-0 break-words">{v}</dd>
              </div>
            ))}
        </dl>
      </section>

      <button
        className="flex w-fit items-center gap-2 rounded-xl bg-primary px-4 py-2 font-medium text-[13px] text-primary-foreground transition hover:opacity-85 active:scale-95"
        onClick={openDocument}
        type="button"
      >
        <FileText className="size-4" />
        Ver documento completo
      </button>
    </div>
  );
}
