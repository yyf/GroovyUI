import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    // Browser is opened once by scripts/dev.sh — never by Vite.
    open: false,
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
