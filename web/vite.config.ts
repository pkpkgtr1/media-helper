import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import path from "node:path"


// 开发端口避开正式服务的 8766，API 转发到本地 Python 服务。
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "./src") } },
  server: {
    host: "127.0.0.1",
    port: 8444,
    strictPort: true,
    proxy: { "/api": { target: process.env.MEDIA_API_URL || "http://127.0.0.1:8766", changeOrigin: true } },
  },
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false },
})
