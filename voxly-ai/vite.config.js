import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The public tunnel reaches this dev server with a real hostname (Host header is
// app-dev.hustlelabs.in), which Vite blocks unless the host is allow-listed.
const allowedHosts = (
  process.env.VITE_ALLOWED_HOSTS || '.hustlelabs.in,localhost,127.0.0.1'
)
  .split(',')
  .map((h) => h.trim())
  .filter(Boolean);

const panelTarget = process.env.VITE_PANEL_ORIGIN || 'http://localhost:3000';

// The admin panel is served from the public origin under /dev, but Next.js emits
// absolute asset URLs (/_next/static/...) that do not carry the /dev prefix, so they
// must be routed back to the panel too or the page renders unstyled.
const panelProxy = {
  target: panelTarget,
  changeOrigin: true,
  ws: true,
  configure(proxy) {
    // A dev asset or a proxy 404 must never be cached. Cloudflare caches 404s by
    // default for hours, which pins a stale response at the edge long after the
    // local server has been fixed.
    proxy.on('proxyRes', (proxyRes) => {
      if (!proxyRes.headers) return;
      const status = proxyRes.statusCode;
      if (status === 404 || status >= 500 || status === 304) {
        proxyRes.headers['cache-control'] = 'no-store, must-revalidate';
      }
    });
    // Without this, a stopped admin panel falls through to Voxly's index.html and looks
    // like a broken product page instead of a down service.
    proxy.on('error', (err, _req, res) => {
      if (res.writeHead && !res.headersSent) {
        res.writeHead(502, {
          'Content-Type': 'text/plain; charset=utf-8',
          'Cache-Control': 'no-store',
        });
      }
      if (res.end) {
        res.end(
          `Admin panel is not running on port 3000 (${err.code || err.message}).\n` +
            'Start it with: npm run dev:web',
        );
      }
    });
  },
};

export default defineConfig({
  plugins: [react()],
  assetsInclude: ['**/*.glb', '**/*.gltf'],
  server: {
    port: 5173,
    host: true,
    allowedHosts,
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_ORIGIN || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: process.env.VITE_BACKEND_ORIGIN || 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
      // Voxly routes on the URL hash, so the /dev path space is free to hand over.
      '/dev': panelProxy,
      '/_next': panelProxy,
    },
  },
  preview: {
    port: 4173,
    host: true,
    allowedHosts,
  },
  build: {
    target: 'esnext',
    minify: 'esbuild',
    rollupOptions: {
      output: {
        manualChunks: {
          'three-core': ['three'],
          'three-fiber': ['@react-three/fiber', '@react-three/drei'],
          'ui-vendor': ['lucide-react'],
        },
      },
    },
    chunkSizeWarningLimit: 800,
  },
  esbuild: {
    drop: process.env.NODE_ENV === 'production' ? ['console', 'debugger'] : [],
  },
});
