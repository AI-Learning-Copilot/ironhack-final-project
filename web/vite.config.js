import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API is a separate process on 8000. Proxying in dev keeps the frontend calling
// same-origin paths, so the fetch code does not need to change when this is deployed
// behind one domain.
export default defineConfig({
  plugins: [react()],
  // Sourcemaps in the production build too: this bundle gets debugged on other
  // people's machines, and a minified stack trace costs more than the extra file.
  build: { sourcemap: true },
  // host:true binds 0.0.0.0 rather than the IPv6 loopback vite picks by default —
  // without it, a browser that resolves localhost to 127.0.0.1 never connects.
  server: { host: true, port: 5173, strictPort: true, proxy: { "/api": { target: "http://localhost:8000", rewrite: (p) => p.replace(/^\/api/, "") } } },
});
