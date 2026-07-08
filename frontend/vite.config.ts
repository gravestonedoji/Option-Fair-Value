import os from "node:os";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API_TARGET = "http://localhost:8000";

// Every backend route goes through the dev proxy so API calls are same-origin.
// That way the app works no matter how it's reached (localhost, LAN IP, or a
// Tailscale hostname) without CORS or base-URL configuration.
const API_ROUTES = [
  "/api",
  "/expiries",
  "/chain",
  "/fairvalue",
  "/analysis",
  "/alerts",
  "/health",
];

export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // listen on all interfaces (LAN + Tailscale), not just localhost
    port: 5173,
    // Vite rejects unknown Host headers by default; allow this machine's own
    // name (what phones use via Tailscale MagicDNS, e.g. http://<hostname>:5173)
    // and full *.ts.net names so `tailscale serve` works too. Host headers
    // arrive lowercase, so lowercase the hostname for the comparison.
    allowedHosts: [os.hostname().toLowerCase(), ".ts.net"],
    proxy: Object.fromEntries(
      API_ROUTES.map((route) => [route, { target: API_TARGET, changeOrigin: true }])
    ),
  },
});
