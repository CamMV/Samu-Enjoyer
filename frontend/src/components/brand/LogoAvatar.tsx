import { LogoCubo } from "./LogoCubo";

/** Avatar del asistente: el cubo flotando con resplandor; `activo` lo hace girar. */
export function LogoAvatar({ size = 28, activo = false, className }: { size?: number; activo?: boolean; className?: string }) {
  return <LogoCubo className={className} girando={activo} size={size} />;
}
