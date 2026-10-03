import { SUGGESTIONS } from "../../config";

/** Preguntas de ejemplo clicables (SUGGESTIONS en config.ts). No muestra nada si la lista está vacía. */
export function Suggestions({ onPick }: { onPick: (text: string) => void }) {
  if (SUGGESTIONS.length === 0) return null;
  return (
    <div className="flex w-full gap-2.5 overflow-x-auto pb-1 sm:grid sm:grid-cols-2 sm:overflow-visible">
      {SUGGESTIONS.map((s, i) => (
        <button
          className="fade-up h-auto min-w-[220px] shrink-0 rounded-xl border border-border/50 bg-card/30 px-4 py-3 text-left text-[12px] text-muted-foreground leading-relaxed transition-all duration-200 hover:-translate-y-0.5 hover:border-glow/40 hover:bg-card/60 hover:text-foreground hover:shadow-[0_0_18px_-8px_var(--glow)] sm:min-w-0 sm:shrink sm:p-4 sm:text-[13px]"
          key={s}
          onClick={() => onPick(s)}
          style={{ animationDelay: `${60 * i}ms` }}
          type="button"
        >
          <span className="line-clamp-3">{s}</span>
        </button>
      ))}
    </div>
  );
}
