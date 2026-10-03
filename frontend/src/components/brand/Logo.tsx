import { cn } from "../../lib/utils";

/** El cubo de Samu-Enjoyer (SVG sin fondo). Junto a APP_NAME, usar alt vacío. */
export function Logo({ size = 28, className, alt = "Samu-Enjoyer" }: { size?: number; className?: string; alt?: string }) {
  return (
    <img
      alt={alt}
      className={cn("shrink-0 object-contain", className)}
      draggable={false}
      height={size}
      src="/logo-cubo.svg"
      width={size}
    />
  );
}
