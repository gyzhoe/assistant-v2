import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  root: resolve(__dirname, 'src/management'),
  base: '/manage/',
  plugins: [react()],
  build: {
    outDir: resolve(__dirname, '../backend/static/manage'),
    emptyOutDir: true,
  },
  resolve: {
    alias: { '@': resolve(__dirname, 'src') },
  },
})
