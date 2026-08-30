/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import pkg from "./package.json";

const r = (p: string) => fileURLToPath(new URL(p, import.meta.url));

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  resolve: {
    alias: {
      "@": r("./src"),
      "@jingming/shared": r("../../packages/shared/src/index.ts"),
      "@jingming/sdk/mock-server": r("../../packages/sdk/src/mockServer.ts"),
      "@jingming/sdk": r("../../packages/sdk/src/index.ts"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    fs: {
      allow: [r("."), r("../../"), "E:\\jingming-yanhuan\\jingming-yanhuan", "E:\\tb\\jingming-yanhuan"],
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
