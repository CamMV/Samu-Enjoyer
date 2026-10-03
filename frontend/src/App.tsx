import { Moon, PanelLeft, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { USE_MOCK } from "./api/client";
import { Logo } from "./components/brand/Logo";
import { APP_CREDIT, APP_NAME } from "./config";
import { Composer } from "./features/chat/Composer";
import { Messages, type PassageTarget } from "./features/chat/Messages";
import { Suggestions } from "./features/chat/Suggestions";
import { useChats } from "./features/chat/useChats";
import { FloatingWindow } from "./features/pasajes/FloatingWindow";
import { PassageDetail } from "./features/pasajes/PassageDetail";
import { colorDe, tituloPasaje } from "./features/pasajes/passages";
import { Sidebar } from "./features/sidebar/Sidebar";
import { useTheme } from "./hooks/useTheme";

const isDesktop = () => window.matchMedia("(min-width: 768px)").matches;

/**
 * Layout: Sidebar | columna del chat (cabecera + Messages + Composer). El pasaje que se abre (desde la
 * lista o desde una cita) se muestra en una ventana flotante que no mueve el chat.
 */
export default function App() {
  const chats = useChats();
  const { dark, toggle } = useTheme();
  const [sidebarOpen, setSidebarOpen] = useState(isDesktop);
  const [abierto, setAbierto] = useState<PassageTarget | null>(null);
  const closeOnMobile = () => !isDesktop() && setSidebarOpen(false);

  const messages = chats.active?.messages ?? [];
  const busy = chats.etapa !== null;

  // Cambiar de chat cierra la ventana del pasaje.
  useEffect(() => setAbierto(null), [chats.activeId]);
  const msg = abierto ? messages.find((m) => m.id === abierto.id) : undefined;
  const pasaje = msg?.role === "assistant" && abierto ? msg.respuesta.pasajes_recuperados[abierto.index] : undefined;

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-sidebar">
      <Sidebar
        activeId={chats.activeId}
        chats={chats.chats}
        onClose={() => setSidebarOpen(false)}
        onDelete={chats.deleteChat}
        onDeleteAll={chats.deleteAll}
        onNew={() => {
          chats.newChat();
          closeOnMobile();
        }}
        onSelect={(id) => {
          chats.selectChat(id);
          closeOnMobile();
        }}
        open={sidebarOpen}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2.5 bg-sidebar px-3">
          {!sidebarOpen && (
            <button
              aria-label="Abrir barra lateral"
              className="rounded-md p-1.5 text-muted-foreground hover:text-foreground"
              onClick={() => setSidebarOpen(true)}
            >
              <PanelLeft className="size-4" />
            </button>
          )}
          <Logo alt="" size={22} />
          <div className="min-w-0 flex-1">
            <span className="block truncate font-medium text-sm">{chats.active?.title || APP_NAME}</span>
            {!chats.active && (
              <span className="hidden truncate text-[11px] text-muted-foreground sm:block">{APP_CREDIT}</span>
            )}
          </div>
          {USE_MOCK && (
            <span
              className="rounded-full border border-glow/40 px-2 py-0.5 text-[11px] text-glow"
              title="Respuestas de ejemplo: VITE_USE_MOCK=0 para usar el back local"
            >
              Modo demo
            </span>
          )}
          <button
            aria-label="Cambiar tema"
            className="rounded-md p-1.5 text-muted-foreground hover:text-foreground"
            onClick={toggle}
          >
            {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
        </header>

        <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden bg-background md:rounded-tl-[12px] md:border-t md:border-l md:border-border/40">
          <Messages abierto={pasaje ? abierto : null} error={chats.error} etapa={chats.etapa} messages={messages} onOpen={setAbierto} />
          <div className="mx-auto flex w-full max-w-4xl flex-col gap-3 bg-background px-2 pb-3 md:px-4 md:pb-4">
            {messages.length === 0 && !busy && <Suggestions onPick={chats.send} />}
            <Composer busy={busy} onSend={chats.send} onStop={chats.stop} />
            <p className="px-1 text-center text-[11px] leading-snug text-muted-foreground/70">
              Respuestas generadas con modelos abiertos locales a partir del corpus; verifica siempre la norma citada.
            </p>
          </div>
        </div>
      </div>

      {pasaje && abierto && (
        <FloatingWindow accent={colorDe(pasaje)} onClose={() => setAbierto(null)} title={tituloPasaje(pasaje, abierto.index)}>
          <PassageDetail index={abierto.index} pasaje={pasaje} />
        </FloatingWindow>
      )}
    </div>
  );
}
