/** Reticle is available only to authenticated developers on a local Vite server. */

let isReticleConnected = false;

export function isLocalReticleHost(hostname) {
  const host = String(hostname || '').trim().toLowerCase().replace(/^\[|\]$/g, '');
  return host === 'localhost' || host === '127.0.0.1' || host === '::1' || host.endsWith('.localhost');
}

export function isReticleAllowed({ isDevelopment, hostname, authenticated }) {
  return Boolean(isDevelopment && authenticated && isLocalReticleHost(hostname));
}

export async function syncReticleWithUser(user) {
  // Keep this as a direct build-time guard so Vite can remove the SDK import
  // and its client chunk from production bundles entirely.
  if (!import.meta.env.DEV) return;

  if (
    !isReticleAllowed({
      isDevelopment: true,
      hostname: typeof window === 'undefined' ? '' : window.location.hostname,
      authenticated: Boolean(user),
    })
  ) {
    return;
  }

  if (isReticleConnected) {
    return;
  }

  try {
    const { reticle, install } = await import('@reticlehq/react');
    if (typeof install === 'function') {
      try {
        install();
      } catch (err) {
        // Already installed
      }
    }
    if (reticle && typeof reticle.connect === 'function') {
      // inject:false keeps the auth/localhost gate in charge. The Vite plugin
      // still supplies this compile-time pairing token for manual connects.
      reticle.connect({
        token: typeof __RETICLE_TOKEN__ === 'undefined' ? undefined : __RETICLE_TOKEN__,
      });
      isReticleConnected = true;
      console.info('[Reticle] Connected for local development');
      // Load capabilities
      try {
        await import('../reticle-dev');
      } catch (err) {
        // Capabilities module load optional
      }
    }
  } catch (err) {
    // The local app must remain usable when the developer bridge is unavailable.
    console.debug('[Reticle] Local development bridge unavailable');
  }
}
