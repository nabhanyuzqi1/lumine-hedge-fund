import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { visualizer } from "rollup-plugin-visualizer";
import { defineConfig } from "vite";

// base "/" — asset absolut; "./" menyebabkan /app/* refresh resolve ke
// /app/assets/* → nginx SPA fallback → MIME text/html → blank screen.
export default defineConfig(() => ({
  base: "/",
  plugins: [
    react(),
    tailwindcss(),
    // Roadmap item 10: bundle analyzer — ANALYZE=1 pnpm build → stats.html
    ...(process.env.ANALYZE === "1"
      ? [
          visualizer({
            filename: "dist/stats.html",
            template: "sunburst",
            gzipSize: true,
            brotliSize: true,
          }),
        ]
      : []),
  ],
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
}));
