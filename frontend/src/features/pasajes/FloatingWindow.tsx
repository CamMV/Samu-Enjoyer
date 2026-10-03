import { X } from "lucide-react";
import { type PointerEvent, type ReactNode, useEffect, useRef, useState } from "react";

const KEY = "samu.ventana-pasaje";
type Frame = { x: number; y: number; w: number; h: number };

const clampFrame = (f: Frame): Frame => {
  const w = Math.min(f.w, window.innerWidth - 16);
  const h = Math.min(f.h, window.innerHeight - 16);
  // the whole window always stays on screen
  return {
    w,
    h,
    x: Math.min(Math.max(f.x, 0), window.innerWidth - w),
    y: Math.min(Math.max(f.y, 0), window.innerHeight - h),
  };
};

const initialFrame = (): Frame => {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (saved && ["x", "y", "w", "h"].every((k) => typeof saved[k] === "number")) return clampFrame(saved);
  } catch {}
  const w = Math.min(560, Math.round(window.innerWidth * 0.45));
  const h = Math.min(window.innerHeight - 96, 700);
  return clampFrame({ w, h, x: window.innerWidth - w - 16, y: 72 });
};

const isDesktop = () => window.matchMedia("(min-width: 768px)").matches;

/**
 * Movable, resizable window (desktop): drag it by its title bar, resize it from the bottom-right corner.
 * It floats over the page without changing the layout, and remembers its position and size.
 * On mobile it is a full-screen overlay instead.
 */
export function FloatingWindow({
  title,
  accent,
  onClose,
  children,
}: {
  title: ReactNode;
  /** CSS colour for a stripe on top of the window (e.g. the phenomenon colour) */
  accent?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const [frame, setFrame] = useState<Frame>(initialFrame);
  const [desktop, setDesktop] = useState(isDesktop);
  const ref = useRef<HTMLDivElement>(null);
  const drag = useRef<{ dx: number; dy: number } | null>(null);

  useEffect(() => {
    const onResize = () => {
      setDesktop(isDesktop());
      setFrame((f) => clampFrame(f));
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // Remember the frame (position and size), also after a native resize from the corner.
  useEffect(() => {
    if (!desktop) return;
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      setFrame((f) => (f.w === el.offsetWidth && f.h === el.offsetHeight ? f : { ...f, w: el.offsetWidth, h: el.offsetHeight }));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [desktop]);
  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(frame));
    } catch {}
  }, [frame]);

  const onPointerDown = (e: PointerEvent<HTMLElement>) => {
    if (!desktop || (e.target as HTMLElement).closest("button")) return;
    drag.current = { dx: e.clientX - frame.x, dy: e.clientY - frame.y };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: PointerEvent<HTMLElement>) => {
    const d = drag.current;
    if (d) setFrame((f) => clampFrame({ ...f, x: e.clientX - d.dx, y: e.clientY - d.dy }));
  };
  const onPointerUp = () => {
    drag.current = null;
  };

  return (
    <div
      className="fade-up fixed inset-0 z-50 flex flex-col overflow-hidden bg-background md:inset-auto md:min-h-64 md:min-w-80 md:resize md:rounded-xl md:border md:border-border md:shadow-[var(--shadow-float)]"
      ref={ref}
      role="dialog"
      style={
        desktop
          ? { left: frame.x, top: frame.y, width: frame.w, height: frame.h, maxWidth: window.innerWidth - frame.x, maxHeight: window.innerHeight - frame.y }
          : undefined
      }
    >
      {accent && <div className="h-1 shrink-0" style={{ backgroundColor: accent }} />}
      <header
        className="flex h-12 shrink-0 touch-none select-none items-center justify-between gap-2 border-b border-border/40 bg-sidebar px-4 md:cursor-grab md:active:cursor-grabbing"
        onPointerCancel={onPointerUp}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        title={desktop ? "Arrastra para mover la ventana" : undefined}
      >
        <span className="min-w-0 truncate font-medium text-sm">{title}</span>
        <button
          aria-label="Cerrar panel"
          className="rounded-md p-1.5 text-muted-foreground hover:text-foreground"
          onClick={onClose}
          type="button"
        >
          <X className="size-4" />
        </button>
      </header>
      <div className="min-h-0 flex-1 overflow-auto">{children}</div>
    </div>
  );
}
