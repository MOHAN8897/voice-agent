/**
 * Voxly AI — API client (voice agent backend, JWT + refresh)
 */
import { mockBackend } from './mockBackend';
import {
  normalizeAgent,
  normalizeCatalogItem,
  normalizeLead,
  normalizeCall,
  normalizeCampaign,
  leadStageToApi,
} from './apiNormalize';
import {
  accessExpiresSoon,
  initAuthSessionSync,
  publishAccessToken,
  publishLogout,
  withRefreshLock,
} from './authSessionSync';

const AUTH_TOKEN_KEY = 'voxly_auth_token';

/**
 * Window in which a just-finished token refresh is reused instead of starting
 * another. Covers a burst of parallel 401s landing slightly apart, so one burst
 * rotates the single-use refresh cookie once. Kept well under the server's
 * REFRESH_REUSE_GRACE_SECONDS so a genuine later refresh is never suppressed.
 */
const REFRESH_COALESCE_MS = 5000;

function tokenStorage() {
  return typeof window !== 'undefined' ? window.sessionStorage : null;
}

/**
 * Server-authoritative session bounds, learned from every auth response.
 *
 * The idle timer's limits used to be a constant in the frontend that nobody could
 * change without a redeploy — so a security policy change on the server and the
 * behaviour in the browser could silently disagree. The server sends the policy on
 * each auth response and the client adopts it.
 */
let sessionPolicy = null;
const sessionPolicyListeners = new Set();

function applySessionPolicy(policy) {
  if (!policy || typeof policy !== 'object') return;
  const next = {
    idleTimeoutMinutes: Number(policy.idleTimeoutMinutes) || 0,
    absoluteMaxHours: Number(policy.absoluteMaxHours) || 0,
    accessTokenMinutes: Number(policy.accessTokenMinutes) || 0,
    rememberIdleTimeoutMinutes: Number(policy.rememberIdleTimeoutMinutes) || 0,
    rememberAbsoluteMaxHours: Number(policy.rememberAbsoluteMaxHours) || 0,
  };
  if (
    sessionPolicy &&
    sessionPolicy.idleTimeoutMinutes === next.idleTimeoutMinutes &&
    sessionPolicy.absoluteMaxHours === next.absoluteMaxHours &&
    sessionPolicy.rememberIdleTimeoutMinutes === next.rememberIdleTimeoutMinutes &&
    sessionPolicy.rememberAbsoluteMaxHours === next.rememberAbsoluteMaxHours
  ) {
    return;
  }
  sessionPolicy = next;
  sessionPolicyListeners.forEach((fn) => {
    try {
      fn(next);
    } catch {
      /* ignore */
    }
  });
}

export function getSessionPolicy() {
  return sessionPolicy;
}

export function subscribeSessionPolicy(fn) {
  sessionPolicyListeners.add(fn);
  if (sessionPolicy) {
    try {
      fn(sessionPolicy);
    } catch {
      /* ignore */
    }
  }
  return () => sessionPolicyListeners.delete(fn);
}

function applyAuthResponse(data) {
  const access = data?.accessToken || data?.token;
  if (access) api.setToken(access);
  applySessionPolicy(data?.sessionPolicy);
}

const fetchOpts = { credentials: 'include' };

/**
 * One client-wide degraded flag.
 *
 * The banner used to be driven by the last *auth refresh* outcome, so an old
 * refresh fault was attributed to later unrelated 4xx responses, and nothing
 * except another refresh could clear it. Track the current state here: any 5xx
 * raises it, any successful API response clears it.
 */
let serviceDegraded = false;

function markServiceDegraded(detail) {
  if (typeof window === 'undefined') return;
  const first = !serviceDegraded;
  serviceDegraded = true;
  if (first) {
    window.dispatchEvent(new CustomEvent('voxly:service-degraded', { detail }));
  }
}

function markServiceRestored() {
  if (typeof window === 'undefined' || !serviceDegraded) return;
  serviceDegraded = false;
  window.dispatchEvent(new CustomEvent('voxly:service-restored'));
}

/**
 * Drop the machine-readable `--- ENTITY TAGS ---` block from a calling script.
 * The tags are an internal compiler/runtime contract (PSTN pins the opening line
 * and identity from them); they live in the stored script and the compiled brain
 * but are never part of the script a person reads or edits.
 */
export function stripEntityTags(script) {
  if (!script) return '';
  return script
    .replace(/(?:^|\n)--- ENTITY TAGS ---\s*\n[\s\S]*?(?=\n--- [^\n-][^\n]*---|\s*$)/i, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export function parseApiError(data, status) {
  const detail = data?.detail;
  const err =
    data?.error ||
    (detail && typeof detail === 'object' && (detail.error || detail)) ||
    null;
  const code = typeof err === 'object' ? err?.code : undefined;
  const message =
    (typeof err === 'object' && (err?.message || err?.code)) ||
    (typeof err === 'string' ? err : null) ||
    (typeof detail === 'string' ? detail : null) ||
    data?.message ||
    (status === 402
      ? 'Insufficient wallet credits. Add funds to continue.'
      : status === 429
        ? 'Too many requests. Wait a moment and try again.'
        : `HTTP ${status}`);
  const retryAfter = typeof err === 'object' ? err?.retry_after : undefined;
  const retryHint =
    status === 429 && retryAfter ? ` Retry in ${retryAfter}s.` : '';
  const issues = Array.isArray(err?.issues) ? err.issues : [];
  const issueText = issues.map((issue) => issue?.message).filter(Boolean).join(' ');
  return {
    code,
    message: `${message}${retryHint}${issueText ? ` ${issueText}` : ''}`,
    issues,
    retryAfter,
    retryable: typeof err?.retryable === 'boolean' ? err.retryable : undefined,
    correlationId: typeof err === 'object' ? err?.correlationId : undefined,
    stage: typeof err === 'object' ? err?.stage : undefined,
    status,
  };
}

function parseError(data, status) {
  return parseApiError(data, status).message;
}

/** Dev-only structured API diagnostics (browser console + optional beacon). */
function logApiEvent(level, event, detail = {}) {
  if (typeof window === 'undefined' || !import.meta.env.DEV) return;
  const line = `[voxly:api] ${event}`;
  const payload = { ...detail, at: new Date().toISOString() };
  if (level === 'error') console.error(line, payload);
  else if (level === 'warn') console.warn(line, payload);
  else console.debug(line, payload);
  try {
    const buf = (window.__voxlyApiLog = window.__voxlyApiLog || []);
    buf.push({ level, event, ...payload });
    if (buf.length > 100) buf.shift();
  } catch {
    /* ignore */
  }
}

function normalizeApiBase(url) {
  const u = String(url || '').trim().replace(/\/$/, '');
  if (!u) return u;
  // Stored/env values are often the API origin without /api (e.g. http://127.0.0.1:8000).
  // request() strips a leading /api from paths, so the base MUST end with /api or every
  // call lands on /agents → FastAPI 404 "Not found".
  if (/\/api$/i.test(u)) return u;
  return `${u}/api`;
}

/**
 * Prefer same-origin `/api` so the httpOnly refresh cookie is set on the page host
 * (Vite/Cloudflare proxy → API). Cross-origin API Set-Cookie never sticks for the SPA.
 */
function preferSameOriginApi() {
  if (typeof window === 'undefined') return false;
  const host = window.location.hostname;
  return (
    host === 'localhost' ||
    host === '127.0.0.1' ||
    host === 'app-dev.dialtact.com' ||
    host === 'dialtact.com' ||
    host === 'www.dialtact.com' ||
    host === 'app.dialtact.com' ||
    host === 'app-dev.hustlelabs.in'
  );
}

export const api = {
  getBackendUrl() {
    // On local Vite, ignore stale localStorage pointing at :8000 without /api (or with CORS
    // mismatches between localhost vs 127.0.0.1). The Vite proxy is the source of truth.
    if (preferSameOriginApi()) {
      const stored = localStorage.getItem('voxly_backend_url');
      if (stored) {
        try {
          const origin = new URL(normalizeApiBase(stored).replace(/\/api$/i, '')).origin;
          const pageOrigin = window.location.origin;
          // Only honor an explicit local override when it is same-host API (normalized).
          if (origin === pageOrigin || /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(origin)) {
            // Drop cross-port :8000 overrides — they cause Not found / CORS; use the proxy.
            if (/:(8000|8001)$/i.test(origin) && origin !== pageOrigin) {
              localStorage.removeItem('voxly_backend_url');
            } else {
              return normalizeApiBase(stored);
            }
          } else {
            localStorage.removeItem('voxly_backend_url');
          }
        } catch {
          localStorage.removeItem('voxly_backend_url');
        }
      }
      return `${window.location.origin}/api`;
    }
    if (import.meta.env.VITE_API_URL) {
      return normalizeApiBase(import.meta.env.VITE_API_URL);
    }
    const stored = localStorage.getItem('voxly_backend_url');
    if (stored) {
      const normalized = normalizeApiBase(stored);
      if (normalized !== stored.replace(/\/$/, '')) {
        localStorage.setItem('voxly_backend_url', normalized);
      }
      return normalized;
    }
    if (typeof window !== 'undefined') return `${window.location.origin}/api`;
    return 'http://localhost:8000/api';
  },

  getWsOrigin() {
    const apiBase = this.getBackendUrl().replace(/\/$/, '');
    const http = apiBase.replace(/\/api$/i, '');
    return http.replace(/^http/, 'ws');
  },

  setBackendUrl(url) {
    if (!url) {
      localStorage.removeItem('voxly_backend_url');
      return;
    }
    const normalized = normalizeApiBase(url);
    const origin = normalized.replace(/\/api$/i, '');
    const allowed =
      typeof window !== 'undefined' &&
      (origin === window.location.origin ||
        normalized === `${window.location.origin}/api` ||
        /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(origin) ||
        /^https?:\/\/[\w.-]+\.(dialtact\.com|hustlelabs\.in)$/i.test(origin));
    if (!allowed) {
      throw new Error('Backend URL must be this site origin, localhost, or the dialtact.com API host.');
    }
    localStorage.setItem('voxly_backend_url', normalized);
  },

  getToken() {
    const store = tokenStorage();
    return store?.getItem(AUTH_TOKEN_KEY) || null;
  },

  setToken(token) {
    const store = tokenStorage();
    if (!store) return;
    if (token) {
      store.setItem(AUTH_TOKEN_KEY, token);
      if (!api._suppressAuthBroadcast) publishAccessToken(token);
    } else {
      store.removeItem(AUTH_TOKEN_KEY);
    }
  },

  /** Adopt a peer tab's access token without re-broadcasting (avoids echo loops). */
  adoptPeerAccessToken(token) {
    if (!token) return;
    api._suppressAuthBroadcast = true;
    try {
      this.setToken(token);
      api._refreshSettled = { at: Date.now(), ok: true };
    } finally {
      api._suppressAuthBroadcast = false;
    }
  },

  clearToken() {
    const store = tokenStorage();
    store?.removeItem(AUTH_TOKEN_KEY);
  },

  /**
   * Resilient session policy: Default false.
   * Arbitrary 401s from sub-services or network hiccups must NEVER wipe the user's workspace session.
   * Only explicit user sign-out or confirmed auth token revocation (401 from /auth/refresh) may evict.
   */
  _logoutOn401: false,
  _logoutTimer: null,
  _lastRefreshOutcome: null,

  _scheduleSessionLogout(force = false) {
    if (!force && this._logoutOn401 === false) return;
    // Guard against kicking the tenant out during server 5xx or network drops
    if (force && !this._lastRefreshOutcome?.isAuthDead) {
      return;
    }
    if (this._logoutTimer) return;
    this._logoutTimer = setTimeout(() => {
      this._logoutTimer = null;
      this.clearToken();
      publishLogout();
      window.dispatchEvent(new Event('voxly:logout'));
    }, 50);
  },

  /**
   * Run `fn` under a temporary auth policy (e.g. suppress logout during workspace sync).
   */
  async withAuthPolicy(opts, fn) {
    const prev = this._logoutOn401;
    if (opts && Object.prototype.hasOwnProperty.call(opts, 'logoutOn401')) {
      this._logoutOn401 = opts.logoutOn401;
    }
    try {
      return await fn();
    } finally {
      this._logoutOn401 = prev;
    }
  },

  /**
   * Exchange the httpOnly refresh cookie for a new access token.
   *
   * Differentiates between authentic auth expiration (HTTP 401/403) and server/network degradation (5xx, fetch error).
   * A server 5xx or network glitch preserves the session and informs the UI gracefully without logging the tenant out.
   */
  async refreshAccessToken() {
    initAuthSessionSync();
    const settled = api._refreshSettled;
    if (settled && Date.now() - settled.at < REFRESH_COALESCE_MS) {
      return settled.ok;
    }
    if (api._refreshInFlight) return api._refreshInFlight;

    const backendUrl = this.getBackendUrl().replace(/\/$/, '');
    const attempt = (async () => {
      const locked = await withRefreshLock(async () => {
        try {
          const res = await fetch(`${backendUrl}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            ...fetchOpts,
            body: JSON.stringify({}),
          });
          if (!res.ok) {
            const isAuthDead = res.status === 401 || res.status === 403;
            const isServerFault = res.status >= 500;
            api._lastRefreshOutcome = {
              attemptedAt: Date.now(),
              ok: false,
              status: res.status,
              isAuthDead,
              isServerFault,
            };
            logApiEvent(isAuthDead ? 'debug' : 'warn', 'refresh_failed', {
              status: res.status,
              hint:
                isAuthDead
                  ? 'No valid refresh cookie (signed out or cookie on wrong host)'
                  : 'Refresh endpoint error (server degraded; session preserved)',
            });
            if (isServerFault) {
              markServiceDegraded({
                status: res.status,
                message: 'Authentication service is momentarily busy. Workspace session preserved.',
              });
            }
            return false;
          }
          const data = await res.json();
          applyAuthResponse(data);
          api._lastRefreshOutcome = {
            attemptedAt: Date.now(),
            ok: true,
            status: 200,
            isAuthDead: false,
            isServerFault: false,
          };
          logApiEvent('debug', 'refresh_ok', {});
          markServiceRestored();
          return true;
        } catch (err) {
          api._lastRefreshOutcome = {
            attemptedAt: Date.now(),
            ok: false,
            status: 0,
            isAuthDead: false,
            isServerFault: true,
            isNetworkError: true,
          };
          logApiEvent('warn', 'refresh_network_error', { message: String(err?.message || err) });
          markServiceDegraded({
            message: 'Network connection error. Workspace session preserved.',
          });
          return false;
        }
      });

      if (locked.fromPeer && locked.accessToken) {
        this.adoptPeerAccessToken(locked.accessToken);
        api._lastRefreshOutcome = {
          attemptedAt: Date.now(),
          ok: true,
          status: 200,
          isAuthDead: false,
          isServerFault: false,
        };
        return true;
      }
      return Boolean(locked.ok);
    })();

    api._refreshInFlight = attempt;
    try {
      const ok = await attempt;
      api._refreshSettled = { at: Date.now(), ok };
      return ok;
    } finally {
      if (api._refreshInFlight === attempt) api._refreshInFlight = null;
    }
  },

  /** Proactive refresh when the tab is focused and access JWT is near expiry. */
  async ensureFreshAccessToken() {
    const token = this.getToken();
    if (!token) return false;
    if (!accessExpiresSoon(token)) return true;
    return this.refreshAccessToken();
  },

  /**
   * POST and return binary (audio) rather than JSON.
   *
   * Separate from `request` because that one unconditionally parses JSON, and a
   * WAV body would throw it away. Shares the auth header and backend-URL fixups
   * so binary and JSON calls cannot drift apart on auth.
   */
  async requestBinary(method, endpoint, body = null, customHeaders = {}, { allowMp3 = false } = {}) {
    const backendUrl = this.getBackendUrl().replace(/\/$/, '');
    const token = this.getToken();
    const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const fullUrl = `${backendUrl}${path.replace(/^\/api/, '')}`;
    const response = await fetch(fullUrl, {
      method,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'audio/wav, application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...customHeaders,
      },
      body: body != null ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(30000),
    });
    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try {
        const data = await response.json();
        message = parseApiError(data, response.status).message || message;
      } catch {
        /* keep the status text */
      }
      const e = new Error(message);
      e.status = response.status;
      throw e;
    }
    markServiceRestored();
    const blob = await response.blob();
    const header = new Uint8Array(await blob.slice(0, 12).arrayBuffer());
    const isWav =
      header.length >= 12 &&
      String.fromCharCode(...header.slice(0, 4)) === 'RIFF' &&
      String.fromCharCode(...header.slice(8, 12)) === 'WAVE';
    const isMp3 = header.length >= 3 && (String.fromCharCode(...header.slice(0, 3)) === 'ID3' || (header[0] === 0xff && (header[1] & 0xe0) === 0xe0));
    if (blob.size < 44 || (!isWav && !(allowMp3 && isMp3))) {
      throw new Error('The voice service returned audio that could not be played.');
    }
    return {
      blob,
      headers: {
        voice: response.headers.get('X-Voice-Name'),
        label: response.headers.get('X-Voice-Label'),
        model: response.headers.get('X-Voice-Model'),
        stackModel: response.headers.get('X-Voice-Stack-Model'),
        cache: response.headers.get('X-Voice-Cache'),
      },
    };
  },

  /**
   * Authenticated download of a file (invoice PDF, CSV).
   *
   * `request` always parses JSON, which would destroy a PDF body. This shares
   * its auth/refresh behaviour and surfaces the server's error message.
   */
  async requestBlob(method, endpoint) {
    const backendUrl = this.getBackendUrl().replace(/\/$/, '');
    const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const fullUrl = `${backendUrl}${path.replace(/^\/api/, '')}`;
    const buildHeaders = () => {
      const token = this.getToken();
      return { Accept: 'application/pdf, text/csv, application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
    };
    const doFetch = () => fetch(fullUrl, { method, headers: buildHeaders(), ...fetchOpts });
    let response = await doFetch();
    if (response.status === 401 && this.getToken()) {
      const refreshed = await this.refreshAccessToken();
      if (refreshed) response = await doFetch();
    }
    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try {
        const data = await response.json();
        message = parseApiError(data, response.status).message || message;
      } catch {
        /* keep the status */
      }
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    markServiceRestored();
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = /filename="?([^";]+)"?/i.exec(disposition);
    return { blob: await response.blob(), filename: match?.[1] || null };
  },

  async request(method, endpoint, body = null, customHeaders = {}, { allowMock = false, timeoutMs = 60_000 } = {}) {
    const backendUrl = this.getBackendUrl().replace(/\/$/, '');
    const token = this.getToken();
    const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const fullUrl = `${backendUrl}${path.replace(/^\/api/, '')}`;

    const isForm = typeof FormData !== 'undefined' && body instanceof FormData;
    const headers = {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      Accept: 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...customHeaders,
    };
    const bodyInit = body == null ? undefined : isForm ? body : JSON.stringify(body);

    const doFetch = async () =>
      fetch(fullUrl, {
        method,
        headers,
        ...fetchOpts,
        signal: AbortSignal.timeout(timeoutMs),
        ...(bodyInit !== undefined ? { body: bodyInit } : {}),
      });

    let response;
    try {
      response = await doFetch();
    } catch (err) {
      logApiEvent('warn', 'request_network_error', { method, path, message: String(err?.message || err) });
      markServiceDegraded({
        status: 0,
        path,
        message: 'A backend service is momentarily busy. Workspace session is active.',
      });
      const netErr = new Error('Network connection error. Workspace session preserved.');
      netErr.isServerDegraded = true;
      netErr.status = 0;
      throw netErr;
    }

    let refreshOk = false;
    let triedRefresh = false;
    if (response.status === 401 && token) {
      triedRefresh = true;
      refreshOk = await this.refreshAccessToken();
      if (refreshOk) {
        headers.Authorization = `Bearer ${this.getToken()}`;
        try {
          response = await doFetch();
        } catch (err) {
          logApiEvent('warn', 'request_network_error_after_refresh', { method, path, message: String(err?.message || err) });
          markServiceDegraded({
            status: 0,
            path,
            message: 'A backend service is momentarily busy. Workspace session is active.',
          });
          const netErr = new Error('Network connection error. Workspace session preserved.');
          netErr.isServerDegraded = true;
          netErr.status = 0;
          throw netErr;
        }
      }
    }
    // Stale voxly_backend_url without /api → FastAPI {"detail":"Not found"} on /agents etc.
    if (response.status === 404 && preferSameOriginApi()) {
      localStorage.removeItem('voxly_backend_url');
      const fixedBase = this.getBackendUrl().replace(/\/$/, '');
      if (fixedBase !== backendUrl) {
        const retryUrl = `${fixedBase}${path.replace(/^\/api/, '')}`;
        response = await fetch(retryUrl, {
          method,
          headers,
          ...fetchOpts,
          signal: AbortSignal.timeout(timeoutMs),
          ...(bodyInit !== undefined ? { body: bodyInit } : {}),
        });
      }
    }

    let data = null;
    try {
      data = await response.json();
    } catch {
      data = {};
    }

    if (!response.ok) {
      const isAuthRoute = path.includes('/auth/');
      const parsed = parseApiError(data, response.status);

      if (
        data?.error === 'tenant_quarantined' ||
        data?.detail?.error === 'tenant_quarantined' ||
        parsed?.code === 'tenant_quarantined'
      ) {
        if (
          typeof window !== 'undefined' &&
          !path.includes('/tenant/delete/cancel') &&
          !path.includes('/tenant/export')
        ) {
          sessionStorage.removeItem(AUTH_TOKEN_KEY);
          window.location.href = '/login?notice=workspace_quarantined';
        }
      }
      const fail = () => {
        // Only trigger session termination if token refresh was actually attempted against
        // /auth/refresh AND /auth/refresh explicitly rejected the session with 401/403.
        // Server faults (5xx) or individual endpoint 401s must NEVER wipe the session.
        const isConfirmedAuthDead =
          Boolean(api._lastRefreshOutcome?.isAuthDead) && triedRefresh && !refreshOk;
        // Only this request's own failure marks the service degraded. A refresh
        // fault counts solely when this request actually triggered the refresh;
        // otherwise a stale outcome mislabels ordinary 4xx responses.
        const refreshFaulted =
          triedRefresh && !refreshOk && Boolean(api._lastRefreshOutcome?.isServerFault);
        const isServerDegraded = response.status >= 500 || refreshFaulted;

        const e = new Error(
          isConfirmedAuthDead
            ? 'Your session expired. Sign in again to continue.'
            : parsed.message || (isServerDegraded ? 'Service temporarily degraded. Please try again.' : `HTTP ${response.status}`)
        );
        e.code = parsed.code || (isConfirmedAuthDead ? 'session_expired' : isServerDegraded ? 'service_degraded' : undefined);
        e.issues = parsed.issues || [];
        e.status = response.status;
        e.isServerDegraded = isServerDegraded;
        e.retryAfter = Number(response.headers.get('Retry-After') || parsed.retryAfter || 0);
        e.retryable = parsed.retryable;
        e.correlationId = parsed.correlationId;
        e.stage = parsed.stage;
        logApiEvent(isConfirmedAuthDead ? 'warn' : 'error', 'request_failed', {
          method,
          path,
          status: response.status,
          code: e.code,
          message: e.message,
          triedRefresh,
          refreshOk,
          isConfirmedAuthDead,
          isServerDegraded,
        });

        if (isServerDegraded) {
          markServiceDegraded({
            status: response.status,
            path,
            message: 'A backend service is momentarily busy. Workspace session is active.',
          });
        }

        if (isConfirmedAuthDead) {
          this._scheduleSessionLogout(true);
        }
        throw e;
      };
      if (backendUrl && !allowMock && !isAuthRoute) fail();
      if (!backendUrl || allowMock) {
        const mockResult = await mockBackend.handleRequest(method, endpoint, body, headers);
        if (mockResult.status >= 400) throw new Error(mockResult.data?.error || 'Request failed');
        return mockResult.data;
      }
      fail();
    }

    markServiceRestored();
    return data;
  },

  auth: {
    async login(email, password, { rememberMe = false } = {}) {
      const data = await api.request('POST', '/api/auth/login', {
        email,
        password,
        rememberMe: Boolean(rememberMe),
      });
      applyAuthResponse(data);
      return data;
    },

    async signup(name, email, password) {
      const data = await api.request('POST', '/api/auth/signup', {
        email,
        password,
        fullName: name,
        orgName: `${name}'s Workspace`,
      });
      if (!data?.requiresEmailVerification) {
        applyAuthResponse(data);
      }
      return data;
    },

    async forgotPassword(email) {
      return await api.request('POST', '/api/auth/forgot-password', { email });
    },

    /**
     * Redeem a single-use reset token. The server answers with a fresh session (the
     * token proved mailbox ownership), so this applies the access token exactly like
     * sign-in does and the console opens without a second password prompt.
     */
    async resetPassword(token, newPassword) {
      const data = await api.request('POST', '/api/auth/reset-password', { token, newPassword });
      applyAuthResponse(data);
      return data;
    },

    /**
     * Change the signed-in user's password. Also returns a session: every other
     * session for the account is revoked, and this browser gets a fresh one so the
     * person who changed it is not signed out of the tab they did it in.
     */
    async changePassword(currentPassword, newPassword) {
      const data = await api.request('POST', '/api/auth/change-password', {
        currentPassword,
        newPassword,
      });
      applyAuthResponse(data);
      return data;
    },

    /** Server-authoritative idle / absolute session bounds the client timer mirrors. */
    async sessionPolicy() {
      return await api.request('GET', '/api/auth/session-policy');
    },

    async verifyEmail(token) {
      return await api.request('POST', '/api/auth/verify-email', { token });
    },

    async verifyEmailOtp(email, otp) {
      const data = await api.request('POST', '/api/auth/verify-email-otp', { email, otp });
      applyAuthResponse(data);
      return data;
    },

    async resendVerification(email) {
      return await api.request('POST', '/api/auth/resend-verification', { email });
    },

    async googleLogin(idToken) {
      const data = await api.request('POST', '/api/auth/google', { idToken });
      applyAuthResponse(data);
      return data;
    },

    async googleConfig() {
      return await api.request('GET', '/api/auth/google/config');
    },

    googleRedirectLogin() {
      const base = api.getBackendUrl().replace(/\/api\/?$/, '');
      const returnTo = encodeURIComponent(window.location.origin);
      window.location.href = `${base}/api/auth/google/start?return_to=${returnTo}`;
    },

    /** Exchange a one-time OAuth handoff id for access + same-origin refresh cookie. */
    async consumeHandoff(handoff) {
      const data = await api.request('POST', '/api/auth/handoff', { handoff });
      applyAuthResponse(data);
      return data;
    },

    async githubLogin() {
      throw new Error('GitHub sign-in is not enabled on this deployment.');
    },

    async getSession() {
      return await api.request('GET', '/api/auth/session');
    },

    async getMe() {
      return await api.request('GET', '/api/auth/me');
    },

    async magicLink(email) {
      return await api.request('POST', '/api/auth/magic-link', { email });
    },

    async ssoLogin(domain) {
      return await api.request('POST', '/api/auth/sso', { domain });
    },

    async submitOnboardingSurvey(data) {
      return await api.request('POST', '/api/auth/onboarding-survey', data);
    },

    async getOnboardingSurvey() {
      return await api.request('GET', '/api/auth/onboarding-survey');
    },

    async logout() {
      const backendUrl = api.getBackendUrl().replace(/\/$/, '');
      const path = '/auth/logout';
      try {
        await fetch(`${backendUrl}${path}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          credentials: 'include',
          body: JSON.stringify({}),
        });
      } catch {
        /* still clear local session */
      } finally {
        api.clearToken();
        publishLogout();
      }
      return { ok: true };
    },
  },

  agents: {
    async list() {
      const data = await api.request('GET', '/api/agents');
      const rows = data.agents || data;
      return Array.isArray(rows) ? rows.map(normalizeAgent) : [];
    },
    /**
     * Operational phone settings for one agent: greeting, business hours,
     * after-hours action, and the inbound/outbound toggles. Kept server-side and
     * separate from the Business Brain, which holds the AI's behaviour.
     */
    async getTelephonyProfile(agentId) {
      const data = await api.request('GET', `/api/agents/${agentId}/telephony-profile`);
      return {
        profile: data.profile || {},
        afterHoursActions: data.afterHoursActions || [],
      };
    },
    async saveTelephonyProfile(agentId, profile) {
      const data = await api.request('PUT', `/api/agents/${agentId}/telephony-profile`, profile);
      return data.profile || {};
    },
    /** What the live inbound path would decide right now, and why. */
    async getEffectiveTelephony(agentId) {
      return await api.request('GET', `/api/agents/${agentId}/telephony-profile/effective`);
    },
    async getAgentProfile(agentId) {
      return await api.telephony.getAgentProfile(agentId);
    },
    async get(id) {
      const data = await api.request('GET', `/api/agents/${id}`);
      return normalizeAgent(data.agent || data);
    },
    async create(agentData) {
      const langs = agentData.languages || (agentData.language ? [agentData.language] : ['en-IN']);
      const body = {
        name: agentData.name,
        languages: langs,
      };
      if (agentData.recordingDisclosureEnabled !== undefined) {
        body.recordingDisclosureEnabled = Boolean(agentData.recordingDisclosureEnabled);
      }
      if (agentData.recordingDisclosureText !== undefined) {
        body.recordingDisclosureText = agentData.recordingDisclosureText;
      }
      const data = await api.request('POST', '/api/agents', body);
      return normalizeAgent(data.agent || data);
    },
    async update(id, updates) {
      const body = {
        name: updates.name,
        status: updates.status,
        languages: updates.languages,
      };
      if (updates.recordingDisclosureEnabled !== undefined) {
        body.recordingDisclosureEnabled = Boolean(updates.recordingDisclosureEnabled);
      }
      if (updates.recordingDisclosureText !== undefined) {
        body.recordingDisclosureText = updates.recordingDisclosureText;
      }
      const data = await api.request('PATCH', `/api/agents/${id}`, body);
      return normalizeAgent(data.agent || data);
    },
    async toggleStatus(id, status) {
      return api.agents.update(id, { status });
    },
    async duplicate(id) {
      const src = await api.agents.get(id);
      const copy = await api.agents.create({ name: `${src.name} (Copy)`, languages: src.languages });
      return copy;
    },
    async delete(id) {
      return await api.request('DELETE', `/api/agents/${id}`);
    },
    /**
     * Save an edited calling script back to the agent's published brain.
     * Only the script text changes; the compiler is not re-run, so the user's
     * wording is what the agent will say.
     */
    async saveCallingScript(agentId, script) {
      const data = await api.request('PUT', `/api/agents/${agentId}/business-brain/calling-script`, {
        script,
      });
      return data;
    },

    /**
     * Persist voice selection. Stored in the brain's voice config section, which
     * is what the live voice pipeline reads.
     */
    async saveVoice(agentId, { voiceId, speed, language }) {
      return await api.request('PUT', `/api/agents/${agentId}/business-brain/voice`, {
        voiceId,
        speed,
        language,
      });
    },

    /** The agent's stored brain: script, variables and voice config. */
    async getBusinessBrain(agentId) {
      const data = await api.request('GET', `/api/agents/${agentId}/business-brain`);
      const sections = data?.draft?.sections || [];
      const byTitle = (title) => sections.find((s) => s.title === title);
      const scriptSection =
        sections.find((s) => s.type === 'facts') || byTitle('Calling script') || null;
      const variablesSection = byTitle('saas_script_variables');
      const voiceSection = byTitle('saas_voice_config');
      let variables = [];
      let voice = {};
      try {
        if (variablesSection?.raw_text) {
          variables = JSON.parse(variablesSection.raw_text)?.variables || [];
        }
      } catch {
        variables = [];
      }
      try {
        if (voiceSection?.raw_text) voice = JSON.parse(voiceSection.raw_text) || {};
      } catch {
        voice = {};
      }
      return {
        callingScript: stripEntityTags(scriptSection?.raw_text || ''),
        variables,
        voice,
        published: data?.published || null,
      };
    },

    async composeOnboarding(payload) {
      const data = await api.request('POST', '/api/app/agents/compose-onboarding', {
        name: payload.name,
        role: payload.role,
        language: payload.language,
        businessSummary: payload.businessSummary,
        goals: payload.goals,
        notes: payload.notes || '',
        brief: payload.brief || '',
        mode: payload.mode || 'instant_lead',
        industry: payload.industry || '',
        naturalSpokenStyle: Boolean(payload.naturalSpokenStyle),
      });
      return data;
    },
    async analyzeEmployee(payload) {
      return api.request('POST', '/api/app/agents/analyze-brief', {
        ...payload,
        agentRole: payload.agentRole || payload.role || '',
        callDirection: payload.callDirection || payload.direction || '',
      });
    },
    async buildEmployee(payload) {
      const data = await api.request('POST', '/api/app/agents/build-employee', {
        brief: payload.brief,
        language: payload.language,
        mode: payload.mode || 'instant_lead',
        industry: payload.industry || '',
        naturalSpokenStyle: Boolean(payload.naturalSpokenStyle),
        employeeName: payload.employeeName || '',
        agentRole: payload.agentRole || payload.role || '',
        callDirection: payload.callDirection || payload.direction || '',
        requestId: payload.requestId,
        retryFailed: Boolean(payload.retryFailed),
        clarificationAnswers: payload.clarificationAnswers || [],
      });
      const agent = data.agent || {};
      return {
        ...data,
        id: data.agentId || agent.agent_id || agent.id,
      };
    },

    /** Languages the platform currently offers at creation (admin-configurable). */
    async languages() {
      const data = await api.request('GET', '/api/app/agents/languages');
      return data.languages || [];
    },
  },

  telephony: {
    async getProvider() {
      return await api.request('GET', '/api/telephony/provider');
    },
    async getNumbers() {
      const data = await api.request('GET', '/api/telephony/numbers');
      const rows = data.numbers || data;
      return Array.isArray(rows) ? rows : [];
    },
    async buyNumber(catalogItem, assignAgentId = null) {
      const e164 = catalogItem?.e164 || catalogItem?.phone_number || catalogItem;
      const body = {
        e164: typeof e164 === 'string' ? e164 : catalogItem?.e164,
        country: catalogItem?.country || catalogItem?.countryCode || 'IN',
        payMethod: catalogItem?.payMethod || 'wallet',
      };
      if (assignAgentId) body.assignAgentId = assignAgentId;
      return await api.request('POST', '/api/telephony/buy', body);
    },
    async assignNumber(numberId, agentId) {
      return await api.request('POST', `/api/telephony/numbers/${numberId}/assign`, {
        agentId: agentId || null,
      });
    },
    async unassignNumber(numberId) {
      return await api.request('POST', `/api/telephony/numbers/${numberId}/assign`, { agentId: null });
    },
    async releaseNumber(numberId) {
      return await api.request('POST', `/api/telephony/numbers/${numberId}/release`);
    },
    async getPurchase(purchaseId) {
      return await api.request('GET', `/api/telephony/purchases/${purchaseId}`);
    },
    async updateRouting(numberId, routingConfig) {
      const body = {};
      if (routingConfig.agentId !== undefined) body.agentId = routingConfig.agentId;
      if (routingConfig.assignedAgentId !== undefined) body.agentId = routingConfig.assignedAgentId;
      if (routingConfig.inboundEnabled !== undefined) body.inboundEnabled = routingConfig.inboundEnabled;
      if (routingConfig.outboundEnabled !== undefined) body.outboundEnabled = routingConfig.outboundEnabled;
      if (routingConfig.inboundRouting?.action === 'ai_agent' && routingConfig.assignedAgentId) {
        body.agentId = routingConfig.assignedAgentId;
      }
      return await api.request('PUT', `/api/telephony/numbers/${numberId}/routing`, body);
    },
    async getVoiceOptions() {
      return await api.request('GET', '/api/telephony/voice-options');
    },

    /**
     * Speak a line in the agent's real production voice (the live model, not the
     * browser's speech engine) and return the WAV plus which voice spoke it.
     */
    async previewVoice({ text, voiceId, language, speed, tier } = {}) {
      const { blob, headers } = await api.requestBinary('POST', '/api/telephony/voice-preview', {
        text,
        voiceId: voiceId || null,
        language: language || null,
        speed: speed != null ? Number(speed) : null,
        tier: tier || null,
      });
      return {
        blob,
        url: URL.createObjectURL(blob),
        voice: headers.voice,
        label: headers.label,
        model: headers.model,
        stackModel: headers.stackModel,
      };
    },

    /** Stored server-side sample addressed by a URL the catalog returned. */
    async fetchVoicePreview(previewUrl) {
      const path = String(previewUrl || '');
      if (!/^\/api\/telephony\/voice-preview\/(catalog|live)\?/.test(path)) {
        throw new Error('A stored voice sample is not available.');
      }
      const { blob } = await api.requestBinary('GET', path);
      return blob;
    },

    /** Per-country compliance obligations for an agent. */
    async getAgentCompliance(agentId) {
      return await api.request('GET', `/api/agents/${encodeURIComponent(agentId)}/compliance`);
    },
    async saveAgentCompliance(agentId, body) {
      return await api.request('PUT', `/api/agents/${encodeURIComponent(agentId)}/compliance`, body);
    },
    /** Operational phone profile + live inbound decision for an agent. */
    async getAgentProfile(agentId) {
      const [profData, effData] = await Promise.all([
        api.agents.getTelephonyProfile(agentId).catch(() => ({ profile: {} })),
        api.agents.getEffectiveTelephony(agentId).catch(() => null),
      ]);
      return {
        profile: profData?.profile || {},
        decision: effData?.decision || null,
        afterHoursActions: profData?.afterHoursActions || [],
      };
    },
    async saveAgentProfile(agentId, profile) {
      return await api.agents.saveTelephonyProfile(agentId, profile);
    },
    async getCatalog(country = 'US') {
      const data = await api.request('GET', `/api/telephony/numbers/search?country=${encodeURIComponent(country)}`);
      const rows = data.numbers || [];
      return rows.map((item) =>
        normalizeCatalogItem({
          ...item,
          country: item.country || item.country_code || country,
        })
      );
    },
    async getCountries() {
      const data = await api.request('GET', '/api/telephony/countries');
      return {
        countries: data.countries || [],
        default: data.default || 'US',
      };
    },
  },

  kyc: {
    async getStatus() {
      return await api.request('GET', '/api/kyc/status');
    },
    async createSession(email = null) {
      return await api.request('POST', '/api/kyc/session', email ? { email } : {});
    },
    async getVoiceStatus({ refresh = false } = {}) {
      return await api.request('GET', `/api/kyc/voice/status${refresh ? '?refresh=true' : ''}`);
    },
    async startVoiceSession(details) {
      return await api.request('POST', '/api/kyc/voice/session', details);
    },
  },

  calls: {
    /**
     * Call history. `status` uses the server's canonical vocabulary
     * (answered | missed | outbound | declined | failed | voicemail | in_progress)
     * and includes calls that never connected, so the Missed tab is real.
     */
    async list({ agentId, status, statuses, direction, tags, tagMatch = 'any', limit = 100, offset = 0, agentMap = null } = {}) {
      const qs = new URLSearchParams({ limit: String(limit) });
      if (offset) qs.set('offset', String(offset));
      if (agentId) qs.set('agentId', agentId);
      if (status) qs.set('status', status);
      if (statuses?.length) qs.set('status', statuses.join(','));
      if (direction) qs.set('direction', direction);
      if (tags?.length) {
        qs.set('tags', tags.join(','));
        qs.set('tag_match', tagMatch);
      }
      const data = await api.request('GET', `/api/calls?${qs}`);
      const rows = data.calls || data;
      if (!Array.isArray(rows)) return [];
      let map = agentMap;
      if (!map) {
        const agents = await api.agents.list().catch(() => []);
        map = {};
        agents.forEach((a) => {
          map[a.id] = a;
        });
      }
      return rows.map((r) => normalizeCall(r, map));
    },
    /** Tags present in history, with counts, for the filter menu. */
    async tags({ agentId } = {}) {
      const qs = new URLSearchParams();
      if (agentId) qs.set('agentId', agentId);
      const suffix = qs.toString() ? `?${qs}` : '';
      const data = await api.request('GET', `/api/calls/tags${suffix}`);
      return data.tags || [];
    },
    /** Counts and totals for the history header. */
    async stats({ agentId, since, until } = {}) {
      const qs = new URLSearchParams();
      if (agentId) qs.set('agentId', agentId);
      if (since) qs.set('since', since);
      if (until) qs.set('until', until);
      const suffix = qs.toString() ? `?${qs}` : '';
      return await api.request('GET', `/api/calls/stats${suffix}`);
    },
    async get(id) {
      return await api.request('GET', `/api/calls/${id}`);
    },
    async transcript(id) {
      return await api.request('GET', `/api/call/${id}/transcript`);
    },
    async recording(id) {
      return api.requestBinary('GET', `/api/call/${encodeURIComponent(id)}/audio/mix`, null,
        { Accept: 'audio/wav, audio/mpeg' }, { allowMp3: true });
    },
    /** Structured post-call outcome: disposition, summary, extracted fields. */
    async outcome(id) {
      return await api.request('GET', `/api/call/${id}/outcome`);
    },
    async triggerOutbound({ agentId, toE164, fromE164 = null, dialRequestId = null }) {
      const body = { agentId, toE164 };
      if (fromE164) body.fromE164 = fromE164;
      if (dialRequestId) body.dialRequestId = dialRequestId;
      const result = await api.request('POST', '/api/calls/outbound', body);
      if (result?.ok === false) {
        const error = new Error(result.error?.message || result.error || 'The call could not be placed. Please try again.');
        error.code = result.code;
        error.status = result.status;
        throw error;
      }
      return result;
    },
    /**
     * Call a missed caller back. Goes through the same outbound path as a manual
     * call, so every server-side guard still applies. Works for both a connected
     * call id and a ringing-attempt id.
     */
    async callback(callId, { toE164, agentId, fromE164, mode = 'manual' } = {}) {
      const body = { mode };
      if (toE164) body.toE164 = toE164;
      if (agentId) body.agentId = agentId;
      if (fromE164) body.fromE164 = fromE164;
      return await api.request('POST', `/api/calls/${callId}/callback`, body);
    },
    async listCallbacks(callId) {
      const data = await api.request('GET', `/api/calls/${callId}/callbacks`);
      return data.callbacks || [];
    },
  },

  leads: {
    async listPage({ agentId, stage, search, hasPhone, updatedSince, sort, limit = 25, offset = 0 } = {}) {
      const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
      for (const [key, value] of Object.entries({ agentId, stage: stage ? leadStageToApi(stage) : '', search, hasPhone, updatedSince, sort })) {
        if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
      }
      const data = await api.request('GET', `/api/leads?${params}`);
      const rows = data.leads || [];
      return { ...data, leads: rows.map(normalizeLead), total: data.total ?? rows.length };
    },
    async update(leadId, changes) {
      const body = { ...changes, ...(changes.stage ? { stage: leadStageToApi(changes.stage) } : {}) };
      const data = await api.request('PATCH', `/api/leads/${leadId}`, body);
      return data.lead ? normalizeLead(data.lead) : null;
    },
    /**
     * `agentId` is sent to the server, which filters on it. Filtering client-side
     * would still ship every agent's leads to every agent's browser.
     */
    async list({ agentId, limit, offset } = {}) {
      const params = new URLSearchParams();
      if (agentId) params.set('agentId', agentId);
      if (limit != null) params.set('limit', String(limit));
      if (offset != null) params.set('offset', String(offset));
      const qs = params.toString() ? `?${params.toString()}` : '';
      const data = await api.request('GET', `/api/leads${qs}`);
      const rows = data.leads || data;
      return Array.isArray(rows) ? rows.map(normalizeLead) : [];
    },
    async updateStage(leadId, stage) {
      return await api.request('PATCH', `/api/leads/${leadId}/stage`, {
        stage: leadStageToApi(stage),
      });
    },
    async updateNotes(leadId, notes) {
      return await api.request('PATCH', `/api/leads/${leadId}`, { notes });
    },
    async create(leadData) {
      const data = await api.request('POST', '/api/leads', {
        name: leadData.name,
        phone: leadData.phone,
        email: leadData.email,
        stage: leadStageToApi(leadData.stage || 'New'),
        notes: leadData.notes,
        agentId: leadData.agentId || null,
      });
      return normalizeLead(data.lead || data);
    },
  },

  campaigns: {
    async list({ limit, offset } = {}) {
      const params = new URLSearchParams();
      if (limit != null) params.set('limit', String(limit));
      if (offset != null) params.set('offset', String(offset));
      const qs = params.toString() ? `?${params.toString()}` : '';
      const data = await api.request('GET', `/api/campaigns${qs}`);
      const rows = data.campaigns || data;
      return Array.isArray(rows) ? rows.map(normalizeCampaign) : [];
    },
    async create(campaignData) {
      const data = await api.request('POST', '/api/campaigns', {
        name: campaignData.name,
        clientRequestId: campaignData.clientRequestId,
        agentId: campaignData.agentId || campaignData.agent_id,
        expectedScriptVersion: campaignData.expectedScriptVersion,
        concurrency: campaignData.concurrencyLimit || campaignData.concurrency || 5,
        maxAttempts: campaignData.maxAttemptsPerContact || campaignData.maxAttempts,
        retryDelayMinutes: campaignData.retryDelayMinutes,
        fromE164: campaignData.fromE164,
        description: campaignData.description || campaignData.objective,
        defaultCountry: campaignData.defaultCountry || 'US',
        contactListId: campaignData.contactListId,
        contacts: campaignData.contacts,
        autoStart: campaignData.autoStart ?? false,
        consentConfirmed: campaignData.consentConfirmed ?? false,
        consentVersion: campaignData.consentVersion || '2026-10-v1',
        dndScrubEnabled: campaignData.dndScrubEnabled ?? true,
        callingWindow: campaignData.callingWindow,
      });
      if (data.ok === false) throw new Error(data.error?.message || data.error || "Campaign could not be created");
      const row = data.campaign || data;
      return normalizeCampaign({
        ...row,
        name: row.name || campaignData.name,
        totalContacts: row.totalContacts ?? data.totalContacts ?? campaignData.contacts?.length ?? 0,
        dndExcludedCount: row.dndExcludedCount ?? data.dndExcludedCount ?? 0,
        objective: campaignData.objective || campaignData.description,
      });
    },
    async toggleStatus(id, currentStatus) {
      const next = currentStatus === 'running' ? 'paused' : 'running';
      await api.request('PATCH', `/api/campaigns/${id}/status`, { status: next });
      return next;
    },
    async start(id) {
      return await api.request('POST', `/api/campaigns/${id}/start`);
    },
    async importContacts(id, contacts) {
      return await api.request('POST', `/api/campaigns/${id}/contacts/import`, { contacts });
    },
    async analytics(id) {
      return await api.request('GET', `/api/campaigns/${id}/analytics`);
    },
    async validateVariables(agentId, contacts) {
      return await api.request('POST', '/api/campaigns/validate-variables', {
        agentId,
        contacts,
      });
    },
  },

  dnc: {
    async list({ status = 'active', search = '', page = 1, limit = 50 } = {}) {
      const qs = new URLSearchParams({ status, page: String(page), limit: String(limit) });
      if (search) qs.set('search', search);
      return await api.request('GET', `/api/dnc?${qs}`);
    },
    async add(phone, reason = 'manual_operator') {
      return await api.request('POST', '/api/dnc', { phoneE164: phone, reason });
    },
    async bulkAdd(phones, reason = 'bulk_upload') {
      return await api.request('POST', '/api/dnc/bulk', { phones, reason });
    },
    async deactivate(phone, removalReason, reconsentConfirmed = true) {
      return await api.request('POST', `/api/dnc/${encodeURIComponent(phone)}/deactivate`, {
        removalReason,
        reconsentConfirmed: Boolean(reconsentConfirmed),
      });
    },
  },

  contacts: {
    async parse(payload) {
      return await api.request('POST', '/api/contacts/parse', payload);
    },
    async normalizePreview(payload) {
      return await api.request('POST', '/api/contacts/normalize-preview', payload);
    },
    async getTemplates() {
      return await api.request('GET', '/api/contacts/templates');
    },
    async saveTemplate(payload) {
      return await api.request('POST', '/api/contacts/templates', payload);
    },
    async getLists() {
      return await api.request('GET', '/api/contacts/lists');
    },
    async createList(payload) {
      return await api.request('POST', '/api/contacts/lists', payload);
    },
    async getListContacts(listId) {
      return await api.request('GET', `/api/contacts/lists/${listId}/contacts`);
    },
  },

  billing: {
    async getWallet() {
      return await api.request('GET', '/api/billing/wallet');
    },
    /** Server-authoritative prices: number rental, top-up bounds, call rates. */
    async getCatalog() {
      return await api.request('GET', '/api/billing/catalog');
    },
    /** Pre-tax and GST breakdown for an amount, before checkout opens. */
    async quoteTopup(amount, currency) {
      return await api.request('POST', '/api/billing/quote', { amount, currency });
    },
    /** `currency` is the account's charge currency (USD when international is on). */
    async createRazorpayOrder(amount, currency, expectedTotalMinor) {
      return await api.request('POST', '/api/billing/razorpay/create-order', { amount, currency, expectedTotalMinor });
    },
    async verifyRazorpayPayment(payload) {
      return await api.request('POST', '/api/billing/razorpay/verify', payload);
    },
    async listInvoices() {
      const data = await api.request('GET', '/api/billing/invoices');
      return data.invoices || [];
    },
    async getInvoice(invoiceId) {
      return await api.request('GET', `/api/billing/invoices/${invoiceId}`);
    },
    async downloadInvoicePdf(invoiceId, invoiceNumber = 'invoice') {
      const { blob, filename } = await api.requestBlob(
        'GET',
        `/api/billing/invoices/${invoiceId}/pdf`
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename || `${invoiceNumber}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    },
    async getBillingProfile() {
      return await api.request('GET', '/api/billing/profile');
    },
    async updateBillingProfile(payload) {
      return await api.request('PUT', '/api/billing/profile', payload);
    },
    async razorpayConfig() {
      return await api.request('GET', '/api/billing/razorpay/config');
    },
    async listTransactions(limit = 50, mine = false) {
      const qs = new URLSearchParams({ limit: String(limit) });
      if (mine) qs.set('mine', 'true');
      const data = await api.request('GET', `/api/billing/transactions?${qs.toString()}`);
      return data.transactions || [];
    },
    async getLastSession() {
      return await api.request('GET', '/api/billing/last-session');
    },
  },

  support: {
    async getConfig() {
      const data = await api.request('GET', '/api/support/config');
      return data.config || {};
    },
    async submitInquiry(payload) {
      return await api.request('POST', '/api/support/contact', payload);
    },
  },

  tenant: {
    async getDeletePreflight() {
      return await api.request('GET', '/api/tenant/delete-preflight');
    },
    async sendDeleteOtp() {
      return await api.request('POST', '/api/tenant/delete-otp');
    },
    async deleteWorkspace({ currentPassword, otpCode, confirmationName, reason, forfeitBalanceConfirmed }) {
      return await api.request('POST', '/api/tenant/delete', {
        current_password: currentPassword || null,
        otp_code: otpCode || null,
        confirmation_name: confirmationName,
        reason: reason || null,
        forfeit_balance_confirmed: Boolean(forfeitBalanceConfirmed),
      });
    },
    async cancelDelete() {
      return await api.request('POST', '/api/tenant/delete/cancel');
    },
    async createExport() {
      return await api.request('POST', '/api/tenant/export');
    },
    async getExportStatus(jobId) {
      return await api.request('GET', `/api/tenant/export/${jobId}`);
    },
    async exportAgents() {
      const token = sessionStorage.getItem('voxly_auth_token') || localStorage.getItem('voxly_auth_token');
      const res = await fetch('/api/tenant/export/agents', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error('Could not download agents export');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'workspace_agents_backup.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    },
    async downloadExportArchive(jobId) {
      const token = sessionStorage.getItem('voxly_auth_token') || localStorage.getItem('voxly_auth_token');
      const res = await fetch(`/api/tenant/export/${jobId}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error('Could not download archive');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `workspace_export_${jobId}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    },
  },

  brain: {
    async load(agentId) {
      return await api.request('GET', `/api/agents/${agentId}/business-brain`);
    },
    async saveDraft(agentId, sections, expectedRevision) {
      if (!expectedRevision) throw new Error('Reload and review the latest draft before saving.');
      return await api.request('PUT', `/api/agents/${agentId}/business-brain/draft`, { sections, expected_revision: expectedRevision });
    },
    async publish(agentId, expectedRevision) {
      if (!expectedRevision) throw new Error('Review the latest draft before publishing.');
      return await api.request('POST', `/api/agents/${agentId}/business-brain/publish`, { expected_revision: expectedRevision });
    },
  },
};
