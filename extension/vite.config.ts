// Vite 7.x + Vitest 2.x: verified compatible (see package.json devDependencies).
// No config changes needed for MV3 extension builds with this version combination.
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        // MV3 multi-entry build (content script built separately as IIFE)
        'background/service-worker': resolve(__dirname, 'src/background/service-worker.ts'),
        sidebar: resolve(__dirname, 'src/sidebar/index.html'),
        options: resolve(__dirname, 'src/options/index.html'),
      },
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
    // Service worker must not be code-split
    target: 'esnext',
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
})
