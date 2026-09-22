/** Console lives at #dashboard/*; builder default tab is employees. */
export const DEFAULT_CONSOLE_TAB = 'employees';

export function consoleHash(tab = DEFAULT_CONSOLE_TAB) {
  const safe = tab || DEFAULT_CONSOLE_TAB;
  return `#dashboard/${safe}`;
}

export function parseDashboardTabFromHash(hash = '') {
  if (!hash.startsWith('#dashboard')) return null;
  const part = hash.replace('#dashboard', '').replace(/^\//, '').split('?')[0];
  return part || DEFAULT_CONSOLE_TAB;
}

const POST_AUTH_TAB_KEY = 'voxly_post_auth_tab';

export function rememberPostAuthTab(tab = DEFAULT_CONSOLE_TAB) {
  try {
    sessionStorage.setItem(POST_AUTH_TAB_KEY, tab || DEFAULT_CONSOLE_TAB);
  } catch {
    /* ignore */
  }
}

export function consumePostAuthTab() {
  try {
    const tab = sessionStorage.getItem(POST_AUTH_TAB_KEY) || DEFAULT_CONSOLE_TAB;
    sessionStorage.removeItem(POST_AUTH_TAB_KEY);
    return tab;
  } catch {
    return DEFAULT_CONSOLE_TAB;
  }
}
