import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The React app lives in src/renderer; src/main is reserved for the Electron
// shell. During development the app talks to `stemlab serve` on :8787.
export default defineConfig({
  root: "src/renderer",
  base: "./",
  plugins: [react()],
  build: { outDir: "../../dist", emptyOutDir: true },
  server: { port: 5173, strictPort: true },
  test: { root: ".", include: ["src/renderer/**/*.test.ts"] },
});
