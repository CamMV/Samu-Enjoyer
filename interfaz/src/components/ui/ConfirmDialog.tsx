import { useEffect, useRef } from "react";

/**
 * Modal confirmation pop-up built on the native <dialog> element (focus trap, Esc to close and
 * top-layer rendering come for free). Clicking the dark backdrop or "Cancelar" calls `onCancel`.
 * Focus starts on "Cancelar" so an accidental Enter never deletes anything.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirmar",
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      aria-describedby="confirm-desc"
      aria-labelledby="confirm-title"
      className="m-auto w-[min(92vw,26rem)] rounded-2xl border border-border bg-card p-0 text-card-foreground shadow-[var(--shadow-float)] backdrop:bg-black/50"
      onCancel={(e) => {
        e.preventDefault(); // we close it ourselves through `open`
        onCancel();
      }}
      onClick={(e) => e.target === ref.current && onCancel()}
      ref={ref}
      role="alertdialog"
    >
      <div className="flex flex-col gap-2 p-5">
        <h2 className="font-semibold text-base" id="confirm-title">
          {title}
        </h2>
        <p className="text-muted-foreground text-sm leading-relaxed" id="confirm-desc">
          {description}
        </p>
      </div>
      <div className="flex justify-end gap-2 px-5 pb-5">
        <button
          autoFocus
          className="rounded-lg border border-border px-4 py-2 text-sm transition-colors hover:bg-muted"
          onClick={onCancel}
          type="button"
        >
          Cancelar
        </button>
        <button
          className="rounded-lg bg-destructive px-4 py-2 font-medium text-sm text-white transition-opacity hover:opacity-90"
          onClick={onConfirm}
          type="button"
        >
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
