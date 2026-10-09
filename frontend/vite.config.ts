import path from 'node:path'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, './src') } },
  // The backend (eco-value-bakend/README.md). Change the target with API_TARGET=http://host:port
  server: { proxy: { '/api': process.env.API_TARGET ?? 'http://localhost:8000' } },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})
