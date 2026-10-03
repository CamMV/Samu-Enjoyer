import { Clock } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useRef } from "react";
import { LogoAvatar } from "../../components/brand/LogoAvatar";
import { NetworkLoader } from "../../components/brand/NetworkLoader";
import { CopyButton } from "../../components/ui/CopyButton";
import { PassageList } from "../pasajes/PassageList";
import { AnswerBody, FORMATO_NOMBRE, textoCopiable } from "./AnswerBody";
import { Greeting } from "./Greeting";
import type { Message } from "./useChats";

/** Pasaje abierto en la ventana flotante: mensaje + índice del pasaje. */
export type PassageTarget = { id: string; index: number };

/** Un mensaje: burbuja a la derecha para el usuario; avatar + respuesta por bloques + pasajes para el agente. */
function Bubble({
  message,
  abierto,
  onOpen,
}: {
  message: Message;
  abierto: PassageTarget | null;
  onOpen: (target: PassageTarget) => void;
}) {
  if (message.role === "user") {
    return (
      <div className="group fade-up flex items-end justify-end gap-1">
        <CopyButton
          className="mb-0.5 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 max-md:opacity-100"
          text={message.content}
        />
        <div className="w-fit max-w-[min(80%,56ch)] whitespace-pre-wrap break-words rounded-2xl rounded-br-lg border border-border/30 bg-secondary px-3.5 py-2 text-[13px] leading-[1.65] shadow-[var(--shadow-card)]">
          {message.content}
        </div>
      </div>
    );
  }
  const r = message.respuesta;
  const open = (index: number) => onOpen({ id: message.id, index });
  return (
    <div className="flex items-start gap-3">
      <LogoAvatar />
      <div className="min-w-0 flex-1">
        <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <span className="rounded-full border border-glow/30 px-2 py-0.5 text-glow">{FORMATO_NOMBRE[r.formato]}</span>
          {r.latencia_ms !== undefined && (
            <span className="flex items-center gap-1">
              <Clock className="size-3" />
              {(r.latencia_ms / 1000).toFixed(1)} s
            </span>
          )}
        </div>
        <AnswerBody onCitation={open} r={r} />
        <div className="-ml-1.5 mt-1">
          <CopyButton text={textoCopiable(r)} />
        </div>
        {r.pasajes_recuperados.length > 0 && (
          <PassageList
            activo={abierto?.id === message.id ? abierto.index : null}
            onOpen={open}
            pasajes={r.pasajes_recuperados}
          />
        )}
      </div>
    </div>
  );
}

/**
 * Zona de conversación con scroll. Saludo si está vacía, burbujas, el loader de red mientras hay `etapa`
 * y el error. Baja sola al contenido más nuevo.
 */
export function Messages({
  messages,
  etapa,
  error,
  abierto,
  onOpen,
}: {
  messages: Message[];
  etapa: string | null;
  error: string | null;
  abierto: PassageTarget | null;
  onOpen: (target: PassageTarget) => void;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, etapa, error]);

  const empty = messages.length === 0 && etapa === null;

  return (
    <div className="relative flex-1 bg-background">
      {empty && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
          <Greeting />
        </div>
      )}
      <div className="absolute inset-0 overflow-y-auto">
        <div className="mx-auto flex min-h-full min-w-0 max-w-4xl flex-col gap-5 px-2 py-6 md:gap-7 md:px-4">
          {messages.map((m) => (
            <Bubble abierto={abierto} key={m.id} message={m} onOpen={onOpen} />
          ))}
          {etapa !== null && (
            <motion.div animate={{ opacity: 1 }} className="flex justify-center" initial={{ opacity: 0 }}>
              <NetworkLoader etapa={etapa} />
            </motion.div>
          )}
          {error && (
            <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-destructive text-sm">
              {error}
            </div>
          )}
          <div className="min-h-6 shrink-0" ref={endRef} />
        </div>
      </div>
    </div>
  );
}
