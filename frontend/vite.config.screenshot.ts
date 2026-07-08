import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  base: '/ui/',
  plugins: [vue()],
  server: {
    port: 5199,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8092', changeOrigin: true },
      '/ingest': { target: 'http://127.0.0.1:8092', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8092', ws: true },
    },
  },
})
