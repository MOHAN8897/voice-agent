let gsiLoadPromise = null;
const GOOGLE_IDENTITY_STATE_KEY = Symbol.for('dialtact.googleIdentityState');

/** Load Google Identity Services (One Tap / button) once per page. */
export function loadGoogleIdentityScript() {
  if (typeof window === 'undefined') return Promise.resolve(false);
  if (window.google?.accounts?.id) return Promise.resolve(true);
  if (gsiLoadPromise) return gsiLoadPromise;

  gsiLoadPromise = new Promise((resolve) => {
    const existing = document.querySelector('script[data-dialtact-gsi]');
    if (existing) {
      existing.addEventListener('load', () => resolve(Boolean(window.google?.accounts?.id)));
      existing.addEventListener('error', () => resolve(false));
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    script.dataset.dialtactGsi = '1';
    script.onload = () => resolve(Boolean(window.google?.accounts?.id));
    script.onerror = () => resolve(false);
    (document.head || document.documentElement).appendChild(script);
  });

  return gsiLoadPromise;
}

/** Google Identity Services supports one initialize call per page. Keep the
 * callback current while reusing that single initialization across login tries. */
export function initializeGoogleIdentityOnce(clientId, onCredential) {
  const googleId = typeof window === 'undefined' ? null : window.google?.accounts?.id;
  if (!clientId || typeof googleId?.initialize !== 'function') return false;

  let state = window[GOOGLE_IDENTITY_STATE_KEY];
  if (state) {
    if (state.clientId !== clientId) return false;
    state.onCredential = onCredential;
    return true;
  }

  state = { clientId, onCredential };
  window[GOOGLE_IDENTITY_STATE_KEY] = state;
  try {
    googleId.initialize({
      client_id: clientId,
      callback: (response) => state.onCredential?.(response),
    });
    return true;
  } catch (error) {
    delete window[GOOGLE_IDENTITY_STATE_KEY];
    throw error;
  }
}
