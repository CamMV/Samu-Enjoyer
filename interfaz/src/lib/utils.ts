import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind class names, resolving conflicts (later wins). */
export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));

/** Random unique id for chats and messages. */
export const uid = () =>
  crypto.randomUUID?.() ?? Math.random().toString(36).slice(2);
