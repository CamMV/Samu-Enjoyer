import { motion, useReducedMotion } from "motion/react";
import { cn } from "../../lib/utils";
import { Logo } from "./Logo";

/**
 * El cubo con resplandor cian que sigue su forma. `girando`: da vueltas en perspectiva sobre el eje
 * vertical (mientras se genera la respuesta); si no, flota en reposo. Con "reducir movimiento" solo pulsa.
 */
export function LogoCubo({ size = 28, girando = false, className }: { size?: number; girando?: boolean; className?: string }) {
  const reducido = useReducedMotion();
  const glow = (px: number, pct: number) => `drop-shadow(0 0 ${px}px color-mix(in oklch, var(--glow) ${pct}%, transparent))`;
  return (
    <div className={cn("shrink-0", className)} style={{ width: size, height: size, perspective: size * 4 }}>
      <motion.div
        animate={
          girando && !reducido
            ? { rotateY: 360, filter: [glow(size * 0.12, 60), glow(size * 0.22, 95), glow(size * 0.12, 60)] }
            : { rotateY: 0, y: reducido ? 0 : [0, -size * 0.05, 0], filter: [glow(size * 0.08, 30), glow(size * 0.14, 55), glow(size * 0.08, 30)] }
        }
        style={{ width: size, height: size, transformStyle: "preserve-3d" }}
        transition={
          girando && !reducido
            ? { rotateY: { duration: 2.4, repeat: Infinity, ease: "linear" }, filter: { duration: 1.2, repeat: Infinity, ease: "easeInOut" } }
            : { rotateY: { duration: 0.6 }, y: { duration: 4, repeat: Infinity, ease: "easeInOut" }, filter: { duration: 3, repeat: Infinity, ease: "easeInOut" } }
        }
      >
        <Logo alt="" size={size} />
      </motion.div>
    </div>
  );
}
