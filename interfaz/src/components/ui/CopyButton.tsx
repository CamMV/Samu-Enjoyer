import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { cn } from "../../lib/utils";

/** Copies `text` to the clipboard and briefly shows a checkmark. */
export function CopyButton({ text, className }: { text: string; className?: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    if (!text.trim()) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const el = document.createElement("textarea");
      el.value = text;
      el.setAttribute("readonly", "");
      el.style.position = "fixed";
      el.style.left = "-9999px";
      document.body.appendChild(el);
      el.select();
      document.execCommand("copy");
      document.body.removeChild(el);
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <button
      aria-label={copied ? "Copiado" : "Copiar"}
      className={cn(
        "rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
        className
      )}
      onClick={copy}
      title={copied ? "Copiado" : "Copiar"}
      type="button"
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
    </button>
  );
}
