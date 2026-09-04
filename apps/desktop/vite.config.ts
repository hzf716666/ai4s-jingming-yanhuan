/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

const r = (p: string) => fileURLToPath(new URL(p, import.meta.url));

export default defineConfig({
  plugins: [react()],
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
    proxy: {
      // 数据面板 API → 本地抽取后端(8787), 前端同源请求, 避免跨源 fetch 被拦
      "/api/records": {
        target: "http://127.0.0.1:8787",
        changeOrigin: true,
      },
    },
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
