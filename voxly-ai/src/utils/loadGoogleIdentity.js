let gsiLoadPromise = null;

/** Load Google Identity Services (One Tap / button) once per page. */
export function loadGoogleIdentityScript() {
  if (typeof window === 'undefined') return Promise.resolve(false);
  if (window.google?.accounts?.id) return Promise.resolve(true);
  if (gsiLoadPromise) return gsiLoadPromise;

  gsiLoadPromise = new Promise((resolve) => {
    const existing = document.querySelector('script[data-voxly-gsi]');
    if (existing) {
      existing.addEventListener('load', () => resolve(Boolean(window.google?.accounts?.id)));
      existing.addEventListener('error', () => resolve(false));
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    script.dataset.voxlyGsi = '1';
    script.onload = () => resolve(Boolean(window.google?.accounts?.id));
    script.onerror = () => resolve(false);
    document.head.appendChild(script);
  });

  return gsiLoadPromise;
}
