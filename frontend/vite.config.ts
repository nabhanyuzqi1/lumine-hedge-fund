import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// base './' keeps all asset URLs relative, so the built dist/ folder works
// unchanged on GitHub Pages (project subpath) and on a VPS nginx root.
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    exclude: ["node_modules", "dist"],
    // Loaded machines can push render-heavy suites (dashboard grid, dialogs)
    // past the 5000ms default; verified green at 20s under full-machine load.
    testTimeout: 20000,
  },
});
