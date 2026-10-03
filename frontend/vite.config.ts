import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// Todo corre en local: el front pide /api/... y Vite lo reenvía al back de esta misma máquina.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "VITE_");
  const back = env.VITE_BACK_URL || "http://localhost:8000";
  return {
    server: { port: 3000, strictPort: true, proxy: { "/api": back } },
    preview: { port: 3000, strictPort: true, proxy: { "/api": back } },
    plugins: [react(), tailwindcss()],
  };
});
