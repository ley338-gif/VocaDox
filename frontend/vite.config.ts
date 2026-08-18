import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Same-origin API access in dev (Phase 1): the app calls relative
// `/api/v1/...` paths (see src/api/client.ts) so the session cookie is a
// same-origin cookie, not a cross-origin one needing CORS credential
// plumbing. Vite's dev server proxies those through to the backend
// container/process. VITE_BACKEND_URL lets docker-compose point this at
// the `backend` service by container name; it defaults to localhost for
// running `npm run dev` directly on the host.
const backendUrl = process.env.VITE_BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: backendUrl, changeOrigin: true },
      "/health": { target: backendUrl, changeOrigin: true },
    },
  },
});
