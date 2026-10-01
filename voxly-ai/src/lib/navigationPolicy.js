/**
 * Navigation / link policies for the Voxly SPA.
 *
 * - In-app console ↔ marketing: same tab (hash SPA). Do not spawn duplicates.
 * - True third-party URLs: new tab with noopener/noreferrer (tabnabbing defense).
 * - Downloads / same-origin assets: same tab or download attr — never target=_blank
 *   without rel.
 */

export function isExternalHttpUrl(url) {
  if (!url || typeof url !== 'string') return false;
  try {
    const u = new URL(url, typeof window !== 'undefined' ? window.location.href : 'http://localhost');
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return false;
    if (typeof window === 'undefined') return true;
    return u.origin !== window.location.origin;
  } catch {
    return false;
  }
}

/** Open a third-party URL in a new tab safely. Returns the window handle or null. */
export function openExternalUrl(url, { replace = false } = {}) {
  if (!url) return null;
  if (!isExternalHttpUrl(url)) {
    if (replace) window.location.replace(url);
    else window.location.assign(url);
    return null;
  }
  const win = window.open(url, '_blank', 'noopener,noreferrer');
  // Older browsers ignore features string for noopener — harden explicitly.
  if (win) win.opener = null;
  return win;
}

/** Same-tab SPA navigation back to marketing landing (no duplicate window). */
export function goToMarketingLanding() {
  window.location.hash = '';
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
