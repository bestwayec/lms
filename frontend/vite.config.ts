import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Use an explicit IPv4 loopback address so the proxy works when Node resolves
// `localhost` to ::1 but Django is listening on 127.0.0.1 only.
const DJANGO = 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('react') || id.includes('react-dom') || id.includes('react-router')) {
              return 'vendor-react';
            }
            if (id.includes('framer-motion')) {
              return 'vendor-motion';
            }
            if (id.includes('recharts') || id.includes('d3-')) {
              return 'vendor-charts';
            }
            if (id.includes('lucide-react')) {
              return 'vendor-icons';
            }
            if (id.includes('ogl')) {
              return 'vendor-webgl';
            }
            if (id.includes('canvas-confetti') || id.includes('qrcode')) {
              return 'vendor-fx';
            }
            return 'vendor-libs';
          }
        },
      },
    },
  },
  server: {
    // 0.0.0.0: reachable via localhost AND 127.0.0.1 (avoids ::1-only
    // binding that made the UI unreachable for some browsers).
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: {
      // Same-origin in dev: React uses relative URLs, Vite forwards to Daphne.
      '/api': { target: DJANGO, changeOrigin: true },
      // React owns the client routes under these prefixes. Proxy only their
      // Django API subpaths; proxying the whole prefix breaks deep links in
      // dev because Django's unbaked SPA fallback redirects back to itself.
      '/essays/api': { target: DJANGO, changeOrigin: true },
      '/arena/api': { target: DJANGO, changeOrigin: true },
      '/subscribe/api': { target: DJANGO, changeOrigin: true },
      '/tma/api': { target: DJANGO, changeOrigin: true },
      '/media': { target: DJANGO, changeOrigin: true },
      '/static': { target: DJANGO, changeOrigin: true },
      // NOTE: /login, /logout and /password-reset* are intentionally NOT
      // proxied — the SPA owns those pages and talks to Django only via the
      // /api/auth/* JSON endpoints (proxied above). The retired Django HTML
      // auth views are unreachable from the UI.
      '/ws': { target: 'ws://localhost:8000', ws: true, changeOrigin: true },
    },
  },
})
