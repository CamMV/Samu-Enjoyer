import { SendHorizontal, Square } from "lucide-react";
import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import { INPUT_PLACEHOLDER } from "../../config";

/**
 * Cuadro de pregunta que crece solo. Enter envía, Shift+Enter agrega una línea (útil para escribir las
 * opciones A-D de una cerrada). Mientras `busy`, el botón pasa a "Detener" y llama a `onStop`.
 */
export function Composer({
  busy,
  onSend,
  onStop,
}: {
  busy: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const submit = () => {
    if (!value.trim() || busy) return;
    onSend(value);
    setValue("");
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <form
      className="flex w-full flex-col rounded-2xl border border-border/30 bg-card/70 shadow-[var(--shadow-composer)] transition-shadow duration-300 focus-within:border-glow/40 focus-within:shadow-[0_0_24px_-10px_var(--glow)]"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <textarea
        autoFocus
        className="min-h-20 w-full resize-none bg-transparent px-4 pt-3.5 pb-1.5 text-[13px] leading-relaxed outline-none placeholder:text-muted-foreground/50"
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={INPUT_PLACEHOLDER}
        ref={ref}
        rows={1}
        value={value}
      />
      <div className="flex items-center justify-between gap-3 px-3 pb-3">
        <span className="hidden text-[11px] text-muted-foreground/70 sm:block">
          Para opción múltiple, escribe las opciones A) B) C) D) en la pregunta.
        </span>
        {busy ? (
          <button
            aria-label="Detener respuesta"
            className="ml-auto flex h-9 items-center gap-2 rounded-xl border border-border bg-card px-4 font-medium text-[13px] text-foreground shadow-[var(--shadow-card)] transition hover:bg-muted active:scale-95"
            onClick={onStop}
            type="button"
          >
            <Square fill="currentColor" size={12} />
            Detener
          </button>
        ) : (
          <button
            aria-label="Enviar pregunta"
            className="ml-auto flex h-9 items-center gap-2 rounded-xl bg-primary px-4 font-medium text-[13px] text-primary-foreground shadow-[var(--shadow-card)] transition hover:opacity-85 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
            disabled={!value.trim()}
            type="submit"
          >
            Enviar
            <SendHorizontal size={15} />
          </button>
        )}
      </div>
    </form>
  );
}
