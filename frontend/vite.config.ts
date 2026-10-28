import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiPort = process.env.JOBPILOT_PORT ?? "8765";
const uiPort = Number(process.env.JOBPILOT_UI_PORT ?? "5173");

export default defineConfig({
  plugins: [react()],
  build: {
    // The backend serves this folder in the desktop app.
    outDir: "../backend/src/jobpilot/web",
    emptyOutDir: true,
  },
  server: {
    host: "127.0.0.1",
    port: uiPort,
    // Fail instead of silently moving to another port, so the URL stays predictable.
    strictPort: true,
    proxy: { "/api": `http://127.0.0.1:${apiPort}` },
  },
});
