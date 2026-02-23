import { defineConfig } from 'vite'
import { resolve } from 'path'

/**
 * Separate Vite build for the content script.
 * MV3 content scripts run as classic scripts (no ES module support),
 * so we must output IIFE format with everything inlined.
 */
export default defineConfig({
  build: {
    outDir: 'dist',
    emptyOutDir: false, // preserve main build output
    lib: {
      entry: resolve(__dirname, 'src/content/index.ts'),
      name: 'ContentScript',
      formats: ['iife'],
      fileName: () => 'content/index.js',
    },
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
      },
    },
    target: 'esnext',
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
})
