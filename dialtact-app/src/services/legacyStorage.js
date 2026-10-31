/**
 * One-time move of pre-rebrand browser keys (voxly_*) to their dialtact_* names.
 *
 * Imported first in main.jsx so it runs before any module reads a session token,
 * backend URL or tour flag. A key that already exists under the new name wins.
 */
const LEGACY_PREFIX = 'voxly_';
const CURRENT_PREFIX = 'dialtact_';

function migrate(store) {
  if (!store) return;
  const legacyKeys = [];
  for (let i = 0; i < store.length; i += 1) {
    const key = store.key(i);
    if (key && key.startsWith(LEGACY_PREFIX)) legacyKeys.push(key);
  }
  for (const key of legacyKeys) {
    const next = CURRENT_PREFIX + key.slice(LEGACY_PREFIX.length);
    if (store.getItem(next) === null) store.setItem(next, store.getItem(key));
    store.removeItem(key);
  }
}

export function migrateLegacyStorage() {
  if (typeof window === 'undefined') return;
  for (const name of ['localStorage', 'sessionStorage']) {
    try {
      migrate(window[name]);
    } catch {
      // Storage can be blocked (private mode, disabled cookies); the app works without it.
    }
  }
}

migrateLegacyStorage();
