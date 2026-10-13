import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

// 开发期：vite 跑 5198，/api 反代到后端 8788（避免跨域）。
// 注意：用 8788/5198 专用端口，避开其他 AI 工具可能抢占的 8787/5199。
// 生产期：vite build 出 dist，由 FastAPI 直接托管（单端口，无跨域）。
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // 生产构建剔除调试类 console（保留 console.error/warn，便于线上排查）
  esbuild: {
    pure: ["console.log", "console.debug", "console.info"],
  },
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5198,
    host: "0.0.0.0",
    allowedHosts: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8788", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    // echarts 已按依赖族独立分包且懒加载，555kB 属预期；上调阈值消除误报警告
    chunkSizeWarningLimit: 650,
    // 按依赖族分包：echarts / markdown 渲染 / react 各自独立缓存，应用主包保持轻
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes("node_modules/echarts") || id.includes("node_modules/zrender")) return "echarts";
          if (
            id.includes("node_modules/react-markdown") ||
            id.includes("node_modules/remark-gfm") ||
            id.includes("node_modules/remark-parse") ||
            id.includes("node_modules/micromark") ||
            id.includes("node_modules/mdast-util") ||
            id.includes("node_modules/hast-util") ||
            id.includes("node_modules/unified") ||
            id.includes("node_modules/vfile") ||
            id.includes("node_modules/react-syntax-highlighter") ||
            id.includes("node_modules/highlight.js") ||
            id.includes("node_modules/refractor") ||
            id.includes("node_modules/prismjs") ||
            id.includes("node_modules/lowlight")
          )
            return "markdown";
          if (id.includes("node_modules/react") || id.includes("node_modules/scheduler")) return "react";
          return undefined;
        },
      },
    },
  },
});
