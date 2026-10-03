import { LogoAvatar } from "../../components/brand/LogoAvatar";
import { APP_NAME, APP_TAGLINE, GREETING_TITLE } from "../../config";

/** Saludo centrado en un chat vacío. */
export function Greeting() {
  return (
    <div className="fade-up flex flex-col items-center px-4">
      <LogoAvatar size={72} />
      <div className="mt-5 text-center font-semibold text-4xl tracking-tight">{APP_NAME}</div>
      <div className="mt-3 max-w-xl text-center text-muted-foreground text-sm leading-relaxed">{APP_TAGLINE}</div>
      <div className="mt-5 text-center font-medium text-base text-foreground/75 tracking-tight">{GREETING_TITLE}</div>
    </div>
  );
}
