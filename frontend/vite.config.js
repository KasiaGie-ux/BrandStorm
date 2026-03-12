import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    hmr: {
      port: 24680,
    },
    proxy: {
      '/ws': { target: 'http://localhost:8080', ws: true },
      '/api': 'http://localhost:8080',
    },
  },
})
