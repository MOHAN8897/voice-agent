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

function devNoCachePlugin() {
  return {
    name: 'dev-no-cache',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        // Prevent Cloudflare tunnel and browser edge from caching dynamic dev assets
        res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
        res.setHeader('Pragma', 'no-cache');
        res.setHeader('Expires', '0');
        next();
      });
    },
  };
}

const enableReticle =
  process.env.ENABLE_RETICLE !== '0' &&
  process.env.ENABLE_RETICLE !== 'false';

export default defineConfig({
  plugins: [
    devNoCachePlugin(),
    ...(enableReticle
      ? [
          reticle({
            sourceMapping: false,
            allowNonLocalhost: true,
          }),
        ]
      : []),
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
    // Keep the native <link rel=modulepreload> hints for the entry's static imports
    // but drop Vite's JS polyfill: the helper now lives in its own `vite-helpers`
    // chunk (see manualChunks), so it can no longer drag a lazily-imported chunk into
    // the entry graph.
    modulePreload: { polyfill: false },
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Vite's dynamic-import preload helper is shared between the entry and the
          // lazy 3D chunk. Rollup folds a shared module into the biggest chunk that
          // needs it, which put the helper in `three` — so the entry imported the 3D
          // chunk *for the helper* and the browser fetched three.js before it was
          // wanted. Giving the helper its own tiny chunk keeps the 3D payload lazy.
          if (id.includes('vite/preload-helper') || id.includes('modulepreload-polyfill')) {
            return 'vite-helpers';
          }
          if (!id.includes('node_modules')) return undefined;
          const p = id.replace(/\\/g, '/');
          // React has to live in its own chunk, not inside the 3D one. `@react-three/*`
          // pulls in react-dom through `its-fine`, so without a named chunk for it the
          // whole react-dom payload ended up inside the lazy chunk — which made the
          // entry import that chunk statically and put ~1 MB back on the critical path,
          // silently undoing the dynamic import.
          if (/node_modules\/(react|react-dom|scheduler|react-reconciler)\//.test(p)) {
            return 'react-vendor';
          }
          // These are only ever reached through the WebGL packages, so they can ride
          // along in the chunk the lazy 3D scene loads.
          if (/node_modules\/(its-fine|zustand)\//.test(p)) return 'three';
          // Everything else in the WebGL stack belongs to the chunk only the lazy 3D
          // scene reaches.
          if (
            p.includes('/three/') ||
            p.includes('three-stdlib') ||
            p.includes('/maath/') ||
            p.includes('@react-three')
          ) {
            return 'three';
          }
          if (p.includes('lucide-react')) return 'ui-vendor';
          return undefined;
        },
      },
    },
    chunkSizeWarningLimit: 800,
  },
  esbuild: {
    drop: process.env.NODE_ENV === 'production' ? ['console', 'debugger'] : [],
  },
});
