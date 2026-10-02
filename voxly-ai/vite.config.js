import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

import { reticle } from '@reticlehq/vite-plugin';
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

const LOCAL_DEV_HOSTS = new Set(['localhost', '127.0.0.1', '::1', '[::1]']);
const allowRemoteDevPortal =
  process.env.DEV_PORTAL_ALLOW_REMOTE === '1' || process.env.DEV_PORTAL_ALLOW_REMOTE === 'true';

function hostnameIsLocal(hostname) {
  const h = String(hostname || '')
    .trim()
    .toLowerCase()
    .split('%')[0];
  const bare = h.startsWith('[') && h.endsWith(']') ? h.slice(1, -1) : h;
  return LOCAL_DEV_HOSTS.has(h) || LOCAL_DEV_HOSTS.has(bare) || bare.endsWith('.localhost');
}

function requestHostsAreLocal(req) {
  if (allowRemoteDevPortal) return true;
  const candidates = [];
  for (const header of ['x-forwarded-host', 'host']) {
    const raw = req.headers[header] || '';
    for (const part of String(raw).split(',')) {
      const host = part.trim().split(':')[0]?.trim();
      if (host) candidates.push(host);
    }
  }
  if (!candidates.length) return false;
  return candidates.every(hostnameIsLocal);
}

/** Refuse /dev and /api/dev on the public tunnel so share links never expose ops. */
function localOnlyDevPortalPlugin() {
  return {
    name: 'local-only-dev-portal',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url || '';
        const path = url.split('?')[0] || '';
        const guarded =
          path === '/dev' ||
          path.startsWith('/dev/') ||
          path.startsWith('/_next') ||
          path === '/api/dev' ||
          path.startsWith('/api/dev/');
        if (!guarded || requestHostsAreLocal(req)) {
          return next();
        }
        res.statusCode = 404;
        res.setHeader('Content-Type', 'text/plain; charset=utf-8');
        res.setHeader('Cache-Control', 'no-store');
        res.end(
          'Dev admin is available on localhost only.\nOpen http://localhost:3000/dev — not the public tunnel link.\n',
        );
      });
    },
  };
}

export default defineConfig({
  // Tunnel hostname (app-dev.hustlelabs.in) is not localhost — Reticle refuses to
  // connect unless allowNonLocalhost is on. Pairing token still comes from the daemon.
  plugins: [
    reticle({
      sourceMapping: false,
      allowNonLocalhost: true,
    }),
    react(),
    localOnlyDevPortalPlugin(),
  ],
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
      // Local-only: public Host is blocked above. Ops opens localhost:3000/dev.
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
