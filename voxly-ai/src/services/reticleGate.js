/**
 * Reticle DevTools Gatekeeper.
 *
 * Restricts Reticle connection exclusively to the designated test account:
 * mohansaiteja.99@gmail.com
 *
 * For all other public users and tenants, Reticle is completely dormant:
 * no websocket connections to localhost:4400, no dev tooling in the console,
 * and zero DOM/network side-effects.
 */

const TEST_ACCOUNT_EMAILS = new Set([
  'mohansaiteja.99@gmail.com',
  'mohanssaiteja.99@gmail.com',
]);

let isReticleConnected = false;

export function isReticleTestUser(user) {
  if (!user || !user.email) return false;
  const email = String(user.email).trim().toLowerCase();
  return TEST_ACCOUNT_EMAILS.has(email);
}

export async function syncReticleWithUser(user) {
  const allowed = isReticleTestUser(user);

  if (!allowed) {
    // If not the authorized test account, do not connect Reticle
    return;
  }

  if (isReticleConnected) {
    return;
  }

  try {
    // Dynamically connect Reticle only for the authorized test account
    const { reticle, install } = await import('@reticlehq/react');
    if (typeof install === 'function') {
      try {
        install();
      } catch (err) {
        // Already installed
      }
    }
    if (reticle && typeof reticle.connect === 'function') {
      reticle.connect({ allowNonLocalhost: true });
      isReticleConnected = true;
      console.info('[Reticle] Connected for test account:', user?.email);
      // Load capabilities
      try {
        await import('../reticle-dev');
      } catch (err) {
        // Capabilities module load optional
      }
    }
  } catch (err) {
    // In production builds or offline, fail gracefully without throwing
    console.debug('[Reticle] Dev kit load bypassed:', err?.message || err);
  }
}
