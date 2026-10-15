import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: Number(process.env.HEADCOUNT_DEV_PORT ?? 5173),
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.HEADCOUNT_API_TARGET ?? 'http://127.0.0.1:8000',
        // Preserve the browser origin/Host pair for the backend's local-origin check.
        changeOrigin: false,
      },
    },
  },
  test: { include: ['src/**/*.test.ts'] },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          ui: ['element-plus', '@element-plus/icons-vue'],
          canvas: ['konva', 'vue-konva'],
        },
      },
    },
  },
})
