import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API_TARGET = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
      "/expiries": { target: API_TARGET, changeOrigin: true },
      "/chain": { target: API_TARGET, changeOrigin: true },
      "/fairvalue": { target: API_TARGET, changeOrigin: true },
    },
  },
});
