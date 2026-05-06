import dns from "node:dns";
import { fileURLToPath } from "url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Avoid Node reordering localhost → ::1 vs 127.0.0.1 (Vite docs: fewer "wrong host" surprises).
dns.setDefaultResultOrder("verbatim");

const srcDir = fileURLToPath(new URL("./src", import.meta.url));

/** Vite default CORS only allows localhost/127.0.0.1/::1 — LAN URLs (e.g. phone) were blocked. */
const DEV_CORS_ORIGIN =
  /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\]|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3})(?::\d+)?$/;

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": srcDir },
  },
  server: {
    // UI port (5173, or 5174+ if 5173 is already in use). This is NOT the API port.
    port: 5173,
    // If 5173 is already taken, exit with an error instead of silently using 5174+ (wrong URL → "connection failed").
    strictPort: true,
    host: true, // 0.0.0.0 — phone on same Wi‑Fi can open http://<this-pc-ip>:5173
    cors: {
      origin: DEV_CORS_ORIGIN,
      credentials: true,
    },
    // Browser → same host as Vite → these paths are forwarded to the FastAPI process (default :8000).
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
