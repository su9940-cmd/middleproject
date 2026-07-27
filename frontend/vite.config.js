import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Lets a Cloudflare quick tunnel (random *.trycloudflare.com host per run)
    // proxy to this dev server without Vite rejecting the Host header.
    // Demo-sharing only - do not widen this for a real deployment.
    allowedHosts: [".trycloudflare.com"],
  },
});
