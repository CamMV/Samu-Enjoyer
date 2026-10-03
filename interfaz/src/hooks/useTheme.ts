import { useCallback, useState } from "react";

/** Light/dark switch. Toggles the `dark` class on <html> and remembers the choice in localStorage. */
export function useTheme() {
  const [dark, setDark] = useState(() =>
    document.documentElement.classList.contains("dark")
  );
  const toggle = useCallback(() => {
    const next = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("theme", next ? "dark" : "light");
    } catch {}
    setDark(next);
  }, []);
  return { dark, toggle };
}
