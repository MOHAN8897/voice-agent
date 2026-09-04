export type PortalKind = "dev" | "app";

/** Avoid infinite "Checking session…" when API/tunnel is slow or unreachable. */
export const AUTH_SESSION_TIMEOUT_MS = 12_000;

const CSRF_KEY: Record<PortalKind, string> = {
  dev: "vani_dev_csrf",
  app: "vani_app_csrf",
};

export function storeCsrfToken(kind: PortalKind, token: string) {
  if (typeof window !== "undefined") {
    sessionStorage.setItem(CSRF_KEY[kind], token);
  }
}

export function getCsrfToken(kind: PortalKind): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(CSRF_KEY[kind]);
}

export function clearCsrfToken(kind: PortalKind) {
  if (typeof window !== "undefined") {
    sessionStorage.removeItem(CSRF_KEY[kind]);
  }
}

export function sessionMeEndpoint(kind: PortalKind): string {
  return kind === "dev" ? "/api/auth/dev-me" : "/api/auth/me";
}

export async function fetchPortalSession(
  kind: PortalKind,
  timeoutMs = AUTH_SESSION_TIMEOUT_MS
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(sessionMeEndpoint(kind), {
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

export function portalSessionErrorMessage(kind: PortalKind, err: unknown): string {
  if (err instanceof DOMException && err.name === "AbortError") {
    const local =
      typeof window !== "undefined" &&
      (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1");
    if (!local) {
      return "Session check timed out over the public tunnel. Open http://localhost:3000/dev/login on this machine, or restart with npm run share (production web build).";
    }
    return "Session check timed out. Confirm the API is running on port 8000.";
  }
  return kind === "dev"
    ? "Cannot reach API. Start the backend on port 8000."
    : "Cannot reach API. Start the backend before signing in.";
}

export async function portalFetch(
  kind: PortalKind,
  input: string,
  init: RequestInit = {}
): Promise<Response> {
  const headers = new Headers(init.headers);
  const csrf = getCsrfToken(kind);
  if (csrf) {
    headers.set("X-CSRF-Token", csrf);
  }
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(input, {
    ...init,
    headers,
    credentials: "include",
  });
}

export async function portalLogout(kind: PortalKind, redirectTo: string) {
  const endpoint = kind === "dev" ? "/api/dev/logout" : "/api/app/logout";
  try {
    const r = await portalFetch(kind, endpoint, { method: "POST" });
    if (!r.ok) {
      await fetch(endpoint, { method: "GET", credentials: "include" });
    }
  } catch {
    try {
      await fetch(endpoint, { method: "GET", credentials: "include" });
    } catch {
      /* last resort — still clear client state */
    }
  } finally {
    clearCsrfToken("dev");
    clearCsrfToken("app");
    if (typeof window !== "undefined") {
      window.location.replace(redirectTo);
    }
  }
}

export async function refreshPortalSession(kind: PortalKind): Promise<boolean> {
  try {
    const r = await fetchPortalSession(kind);
    if (!r.ok) return false;
    const j = await r.json();
    if (j.authenticated && j.csrf_token) {
      storeCsrfToken(kind, j.csrf_token);
    }
    return Boolean(j.authenticated);
  } catch {
    return false;
  }
}
