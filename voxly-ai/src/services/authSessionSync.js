/**
 * Cross-tab auth coordination (OAuth BCP / SPA industry practice).
 *
 * Refresh cookies are httpOnly + single-use. Two tabs refreshing at once can
 * still race the cookie. We (1) elect a short localStorage lock so only one tab
 * hits /auth/refresh, (2) BroadcastChannel the new access token so siblings
 * adopt it without a second rotation, (3) broadcast logout so every tab signs out.
 */
const CHANNEL_NAME = 'voxly-auth-v1';
const LOCK_KEY = 'voxly_refresh_lock';
const LOCK_TTL_MS = 8000;

const tabId =
  typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `tab-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

let channel = null;
const accessWaiters = new Set();

function getChannel() {
  if (typeof window === 'undefined' || typeof BroadcastChannel === 'undefined') return null;
  if (!channel) {
    channel = new BroadcastChannel(CHANNEL_NAME);
    channel.onmessage = (ev) => {
      const msg = ev?.data;
      if (!msg || msg.tabId === tabId) return;
      if (msg.type === 'access' && msg.accessToken) {
        accessWaiters.forEach((fn) => {
          try {
            fn(msg.accessToken);
          } catch {
            /* ignore */
          }
        });
        window.dispatchEvent(
          new CustomEvent('voxly:auth-sync', { detail: { type: 'access', accessToken: msg.accessToken } })
        );
      } else if (msg.type === 'logout') {
        window.dispatchEvent(new CustomEvent('voxly:auth-sync', { detail: { type: 'logout' } }));
      }
    };
  }
  return channel;
}

export function initAuthSessionSync() {
  getChannel();
}

export function publishAccessToken(accessToken) {
  if (!accessToken) return;
  try {
    getChannel()?.postMessage({ type: 'access', accessToken, tabId, at: Date.now() });
  } catch {
    /* ignore */
  }
}

export function publishLogout() {
  try {
    getChannel()?.postMessage({ type: 'logout', tabId, at: Date.now() });
  } catch {
    /* ignore */
  }
}

function readLock() {
  try {
    const raw = localStorage.getItem(LOCK_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.until || parsed.until < Date.now()) {
      localStorage.removeItem(LOCK_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function takeLock() {
  const existing = readLock();
  if (existing && existing.owner !== tabId) return false;
  try {
    localStorage.setItem(
      LOCK_KEY,
      JSON.stringify({ owner: tabId, until: Date.now() + LOCK_TTL_MS })
    );
    return true;
  } catch {
    return true; // storage blocked → proceed (in-tab coalesce still helps)
  }
}

function releaseLock() {
  try {
    const existing = readLock();
    if (existing?.owner === tabId) localStorage.removeItem(LOCK_KEY);
  } catch {
    /* ignore */
  }
}

function waitForPeerAccess(timeoutMs = 4000) {
  return new Promise((resolve) => {
    let settled = false;
    const done = (token) => {
      if (settled) return;
      settled = true;
      accessWaiters.delete(onAccess);
      clearTimeout(timer);
      resolve(token || null);
    };
    const onAccess = (token) => done(token);
    accessWaiters.add(onAccess);
    const timer = setTimeout(() => done(null), timeoutMs);
  });
}

/**
 * Run refresh under a cross-tab lock. If another tab holds the lock, wait for
 * its BroadcastChannel access token instead of rotating again.
 */
export async function withRefreshLock(doRefresh) {
  if (typeof window === 'undefined') return doRefresh();

  getChannel();
  if (!takeLock()) {
    const peerToken = await waitForPeerAccess();
    if (peerToken) return { ok: true, accessToken: peerToken, fromPeer: true };
    // Lock holder vanished — try ourselves.
    if (!takeLock()) {
      const again = await waitForPeerAccess(2000);
      if (again) return { ok: true, accessToken: again, fromPeer: true };
    }
  }

  try {
    const ok = await doRefresh();
    return { ok: Boolean(ok), fromPeer: false };
  } finally {
    releaseLock();
  }
}

/** True when JWT `exp` is missing or within `skewMs` of now (client clock only). */
export function accessExpiresSoon(token, skewMs = 90_000) {
  if (!token || typeof token !== 'string') return true;
  try {
    const part = token.split('.')[1];
    if (!part) return true;
    const json = JSON.parse(atob(part.replace(/-/g, '+').replace(/_/g, '/')));
    if (!json?.exp) return true;
    return json.exp * 1000 - Date.now() < skewMs;
  } catch {
    return true;
  }
}
