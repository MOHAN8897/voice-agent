export type PortalKind = "dev" | "app";

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
  const endpoint = kind === "dev" ? "/api/auth/dev-me" : "/api/auth/me";
  try {
    const r = await fetch(endpoint, { credentials: "include", cache: "no-store" });
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
