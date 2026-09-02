/** API origin — matches next.config rewrites default when env is unset. */
export function apiOrigin(): string {
  const strip = (u: string) => u.replace(/\/$/, "");
  if (typeof window === "undefined") {
    return strip(
      process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    );
  }
  // Local Next dev: WS must hit FastAPI on :8000, not the public tunnel URL in NEXT_PUBLIC_API_URL.
  const host = window.location.hostname;
  if (host === "localhost" || host === "127.0.0.1") {
    return strip(process.env.NEXT_PUBLIC_API_URL_LOCAL || "http://127.0.0.1:8000");
  }
  if (process.env.NEXT_PUBLIC_API_URL) return strip(process.env.NEXT_PUBLIC_API_URL);
  if (window.location.port === "3000") return "http://localhost:8000";
  return window.location.origin;
}

export async function apiGet<T = unknown>(path: string): Promise<T> {
  const url = `${apiOrigin()}${path}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export function wsUrl(path: string): string {
  const wsBase = apiOrigin().replace(/^http/, "ws");
  return `${wsBase}${path}`;
}
