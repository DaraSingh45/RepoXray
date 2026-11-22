import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    open: true,          // opens the browser automatically on `npm run dev`
    proxy: { '/api': { target: process.env.API_URL || 'http://localhost:8000', changeOrigin: true } },
  },
  build: {
    chunkSizeWarningLimit: 3000,
    reportCompressedSize: false,   // skips gzip-size reporting: much less memory on small machines
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: { flow: ['@xyflow/react', '@dagrejs/dagre'], charts: ['recharts'] },
      },
    },
  },
})
