import { useCallback, useEffect, useRef, useState } from "react";
import { preguntar } from "../../api/client";
import type { RespuestaAgente } from "../../api/types";
import { STAGES } from "../../config";
import { uid } from "../../lib/utils";

export type Message =
  | { id: string; role: "user"; content: string }
  | { id: string; role: "assistant"; respuesta: RespuestaAgente };

export type Chat = { id: string; title: string; messages: Message[] };

const KEY = "samu.chats";

const load = (): Chat[] => {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "[]");
  } catch {
    return [];
  }
};

/**
 * Estado de los chats: lista, chat activo, send/stop/newChat/selectChat/deleteChat/deleteAll, la etapa
 * mostrada mientras se espera (`etapa`, null si no hay petición) y el último `error`.
 * Cada pregunta va sola al agente (no hay historial: el agente responde preguntas independientes).
 * Todo se guarda en localStorage.
 */
export function useChats() {
  const [chats, setChats] = useState<Chat[]>(load);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [etapa, setEtapa] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(chats));
    } catch {}
  }, [chats]);

  // Avanza las etapas de la leyenda mientras se espera (la última se queda hasta que llegue la respuesta).
  useEffect(() => {
    if (etapa === null) return;
    const i = STAGES.indexOf(etapa);
    if (i < 0 || i === STAGES.length - 1) return;
    const t = setTimeout(() => setEtapa(STAGES[i + 1]), 1100);
    return () => clearTimeout(t);
  }, [etapa]);

  const active = chats.find((c) => c.id === activeId) ?? null;
  const cancel = () => abortRef.current?.abort();

  const stop = useCallback(cancel, []);

  const newChat = useCallback(() => {
    cancel();
    setActiveId(null);
    setError(null);
  }, []);

  const selectChat = useCallback((id: string) => {
    cancel();
    setActiveId(id);
    setError(null);
  }, []);

  const deleteChat = useCallback((id: string) => {
    setChats((cs) => cs.filter((c) => c.id !== id));
    setActiveId((cur) => (cur === id ? null : cur));
  }, []);

  const deleteAll = useCallback(() => {
    cancel();
    setChats([]);
    setActiveId(null);
  }, []);

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || etapa !== null) return;

      const chatId = activeId ?? uid();
      const userMsg: Message = { id: uid(), role: "user", content };
      setError(null);
      setActiveId(chatId);
      setEtapa(STAGES[0]);
      setChats((cs) =>
        cs.some((c) => c.id === chatId)
          ? cs.map((c) => (c.id === chatId ? { ...c, messages: [...c.messages, userMsg] } : c))
          : [{ id: chatId, title: content.slice(0, 60), messages: [userMsg] }, ...cs]
      );

      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const respuesta = await preguntar(content, controller.signal);
        const reply: Message = { id: uid(), role: "assistant", respuesta };
        setChats((cs) => cs.map((c) => (c.id === chatId ? { ...c, messages: [...c.messages, reply] } : c)));
      } catch (e) {
        if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Error desconocido");
      } finally {
        setEtapa(null);
      }
    },
    [activeId, etapa]
  );

  return { chats, active, activeId, etapa, error, send, stop, newChat, selectChat, deleteChat, deleteAll };
}
