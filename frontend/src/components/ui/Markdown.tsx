import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "../../lib/utils";

/** Markdown (GFM: tablas, listas) con la tipografía de la app. Se usa en respuestas y documentos completos. */
export function Markdown({
  children,
  className,
  onCitation,
  citationColor,
}: {
  children: string;
  className?: string;
  /** recibe el índice (desde 0) del pasaje cuando se hace clic en un número de cita */
  onCitation?: (index: number) => void;
  /** color CSS del número de cita (el del tipo de fuente del pasaje) */
  citationColor?: (index: number) => string | undefined;
}) {
  return (
    <div
      className={cn(
        "prose prose-sm dark:prose-invert min-w-0 max-w-none text-[13px] leading-[1.65] prose-pre:bg-muted prose-pre:text-foreground prose-table:text-[12px]",
        className
      )}
    >
      <ReactMarkdown
        components={{
          a: ({ href, children }) => {
            const cite = href?.match(/^#pasaje-(\d+)$/);
            if (cite && onCitation) {
              const n = Number(cite[1]);
              const color = citationColor?.(n - 1);
              return (
                <button
                  className="mx-0.5 inline-flex min-w-5 items-center justify-center rounded-md border border-transparent bg-muted px-1 align-baseline font-semibold text-[11px] text-foreground no-underline transition-opacity hover:opacity-70"
                  onClick={() => onCitation(n - 1)}
                  style={
                    color
                      ? {
                          color,
                          backgroundColor: `color-mix(in oklch, ${color} 16%, transparent)`,
                          borderColor: `color-mix(in oklch, ${color} 45%, transparent)`,
                        }
                      : undefined
                  }
                  title={`Ver pasaje ${n}`}
                  type="button"
                >
                  {n}
                </button>
              );
            }
            return (
              <a href={href} rel="noopener noreferrer" target="_blank">
                {children}
              </a>
            );
          },
        }}
        remarkPlugins={[remarkGfm]}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
