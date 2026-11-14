import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发时把 /api 代理到本机的 ingest/api 服务，生产由 Caddy 反代
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.EDGE_API || 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
  // 冒烟测试用 preview 起静态站，/api 仍按开发时的代理走
  preview: {
    port: 4173,
    proxy: {
      '/api': {
        target: process.env.EDGE_API || 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
