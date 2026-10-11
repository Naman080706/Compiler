/// <reference types="vitest/config" />
// Vite + Vitest configuration for the CEA web UI (plan 013, plans/m2-architecture.md section 4).
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    // The UI talks only to /api/*; the FastAPI backend (plan 012) runs on 127.0.0.1:8000
    // unless CEA_API_URL points elsewhere (e.g. when port 8000 is taken).
    proxy: { "/api": { target: process.env.CEA_API_URL ?? "http://127.0.0.1:8000", changeOrigin: false } },
  },
  build: { chunkSizeWarningLimit: 8000 },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    unstubGlobals: true,
  },
});
