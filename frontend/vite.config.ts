import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  // servito dal collector sotto /ui/ (vedi server/agentspy_server/app.py)
  base: '/ui/',
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8082',
        changeOrigin: true,
      },
      '/ingest': {
        target: 'http://127.0.0.1:8082',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8082',
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
