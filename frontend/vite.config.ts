import { fileURLToPath } from "url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const srcDir = fileURLToPath(new URL("./src", import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": srcDir },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/classify_role": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/match_score": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/rank_candidates_for_job": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  // `vite preview` uses this server too — without it, `/health` would not reach the API when VITE_API_BASE is unset.
  preview: {
    port: 4173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/classify_role": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/match_score": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/rank_candidates_for_job": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
