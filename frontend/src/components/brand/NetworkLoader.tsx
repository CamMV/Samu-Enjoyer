import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef } from "react";
import { LogoCubo } from "./LogoCubo";

type Nodo = { x: number; y: number; vx: number; vy: number };

const N = 26;
const ENLACE = 70; // distancia máxima (px) para dibujar una línea entre dos nodos

/**
 * Espera de la respuesta: el cubo girando al centro y, alrededor, una red de nodos que se mueven y se conectan
 * y desconectan según su distancia ("procesamiento de conexiones"). Debajo, la etapa actual.
 */
export function NetworkLoader({ etapa, size = 180 }: { etapa: string; size?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);
    const color = getComputedStyle(canvas).getPropertyValue("--glow").trim() || "#2bb3c9";
    const c = size / 2;
    const nodos: Nodo[] = Array.from({ length: N }, () => {
      const a = Math.random() * Math.PI * 2;
      const r = size * (0.22 + Math.random() * 0.26);
      return { x: c + Math.cos(a) * r, y: c + Math.sin(a) * r, vx: (Math.random() - 0.5) * 0.5, vy: (Math.random() - 0.5) * 0.5 };
    });
    const reducido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    const frame = () => {
      ctx.clearRect(0, 0, size, size);
      for (const n of nodos) {
        if (!reducido) {
          n.x += n.vx;
          n.y += n.vy;
        }
        // anillo alrededor del logo: rebotan contra el borde interior y el exterior
        const dx = n.x - c;
        const dy = n.y - c;
        const d = Math.hypot(dx, dy) || 1;
        if (d < size * 0.2 || d > size * 0.48) {
          n.vx -= (dx / d) * 0.08 * (d < size * 0.2 ? -1 : 1);
          n.vy -= (dy / d) * 0.08 * (d < size * 0.2 ? -1 : 1);
        }
        n.vx = Math.max(-0.6, Math.min(0.6, n.vx));
        n.vy = Math.max(-0.6, Math.min(0.6, n.vy));
      }
      ctx.strokeStyle = color;
      for (let i = 0; i < N; i++) {
        for (let j = i + 1; j < N; j++) {
          const d = Math.hypot(nodos[i].x - nodos[j].x, nodos[i].y - nodos[j].y);
          if (d < ENLACE) {
            ctx.globalAlpha = (1 - d / ENLACE) * 0.7;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(nodos[i].x, nodos[i].y);
            ctx.lineTo(nodos[j].x, nodos[j].y);
            ctx.stroke();
          }
        }
      }
      ctx.globalAlpha = 1;
      ctx.fillStyle = color;
      for (const n of nodos) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, 2, 0, Math.PI * 2);
        ctx.fill();
      }
      raf = requestAnimationFrame(frame);
    };
    frame();
    return () => cancelAnimationFrame(raf);
  }, [size]);

  return (
    <div className="flex flex-col items-center gap-3 py-2" role="status">
      <div className="relative" style={{ width: size, height: size }}>
        <canvas className="absolute inset-0" ref={ref} style={{ width: size, height: size }} />
        <LogoCubo className="absolute inset-0 m-auto" girando size={size * 0.34} />
      </div>
      <AnimatePresence mode="wait">
        <motion.span
          animate={{ opacity: 1, y: 0 }}
          className="text-[13px] text-muted-foreground"
          exit={{ opacity: 0, y: -4 }}
          initial={{ opacity: 0, y: 4 }}
          key={etapa}
          transition={{ duration: 0.25 }}
        >
          {etapa}
        </motion.span>
      </AnimatePresence>
    </div>
  );
}
