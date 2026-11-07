import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import path from "node:path"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    host: "127.0.0.1", port: 8443, strictPort: true,
    proxy: { "/api": { target: process.env.MEDIA_API_URL || "http://127.0.0.1:8765", changeOrigin: true } },
  },
  preview: { host: "127.0.0.1", port: 8443 },
})
