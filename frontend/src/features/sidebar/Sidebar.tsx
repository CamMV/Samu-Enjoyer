import { PanelLeft, PenSquare, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Logo } from "../../components/brand/Logo";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { APP_CREDIT, APP_NAME } from "../../config";
import { cn } from "../../lib/utils";
import type { Chat } from "../chat/useChats";

/**
 * Panel izquierdo con el historial de chats, "Nuevo chat" y "Borrar todo".
 * Cajón fijo con fondo en móvil; columna plegable en escritorio.
 */
export function Sidebar({
  chats,
  activeId,
  open,
  onClose,
  onNew,
  onSelect,
  onDelete,
  onDeleteAll,
}: {
  chats: Chat[];
  activeId: string | null;
  open: boolean;
  onClose: () => void;
  onNew: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onDeleteAll: () => void;
}) {
  const [confirmDeleteAll, setConfirmDeleteAll] = useState(false);

  return (
    <>
      <ConfirmDialog
        confirmLabel="Borrar todo"
        description="Se eliminarán todas tus conversaciones de este navegador. Esta acción no se puede deshacer."
        onCancel={() => setConfirmDeleteAll(false)}
        onConfirm={() => {
          setConfirmDeleteAll(false);
          onDeleteAll();
        }}
        open={confirmDeleteAll}
        title="¿Borrar todos los chats?"
      />
      <div className={cn("fixed inset-0 z-30 bg-black/40 md:hidden", open ? "block" : "hidden")} onClick={onClose} />
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-72 flex-col bg-sidebar text-sidebar-foreground transition-transform duration-300 md:static md:w-64 md:shrink-0 md:border-r md:border-sidebar-border",
          open ? "translate-x-0" : "-translate-x-full md:hidden"
        )}
      >
        <div className="flex items-center justify-between gap-2 px-3 pt-3">
          <div className="flex min-w-0 items-center gap-2.5 px-1">
            <Logo alt="" size={28} />
            <div className="min-w-0">
              <div className="font-medium text-sm text-sidebar-accent-foreground">{APP_NAME}</div>
              <div className="truncate text-[11px] text-sidebar-foreground/50">{APP_CREDIT}</div>
            </div>
          </div>
          <button
            aria-label="Cerrar barra lateral"
            className="rounded-md p-1.5 text-sidebar-foreground/60 hover:text-sidebar-foreground"
            onClick={onClose}
          >
            <PanelLeft className="hidden size-4 md:block" />
            <X className="size-4 md:hidden" />
          </button>
        </div>

        <div className="flex flex-col gap-1 px-2 pt-3">
          <button
            className="flex h-8 items-center gap-2 rounded-lg border border-sidebar-border px-2 text-[13px] text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground"
            onClick={onNew}
          >
            <PenSquare className="size-4" />
            <span className="font-medium">Nuevo chat</span>
          </button>
          {chats.length > 0 && (
            <button
              className="flex h-8 items-center gap-2 rounded-lg px-2 text-[13px] text-sidebar-foreground/40 transition-colors hover:bg-destructive/10 hover:text-destructive"
              onClick={() => setConfirmDeleteAll(true)}
            >
              <Trash2 className="size-4" />
              Borrar todo
            </button>
          )}
        </div>

        <nav className="mt-3 flex-1 overflow-y-auto px-2 pb-3">
          {chats.length === 0 ? (
            <p className="px-2 text-[13px] text-sidebar-foreground/40">Tus conversaciones aparecerán aquí.</p>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {chats.map((c) => (
                <li
                  className={cn(
                    "group flex items-center rounded-lg transition-colors hover:bg-sidebar-accent",
                    c.id === activeId && "bg-sidebar-accent text-sidebar-accent-foreground"
                  )}
                  key={c.id}
                >
                  <button className="min-w-0 flex-1 truncate px-2 py-1.5 text-left text-[13px]" onClick={() => onSelect(c.id)}>
                    {c.title}
                  </button>
                  <button
                    aria-label="Borrar chat"
                    className="mr-1 rounded p-1 text-sidebar-foreground/40 opacity-0 transition hover:text-destructive group-hover:opacity-100"
                    onClick={() => onDelete(c.id)}
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </nav>
      </aside>
    </>
  );
}
