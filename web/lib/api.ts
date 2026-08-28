/** API origin — matches next.config rewrites default when env is unset. */
export function apiOrigin(): string {
  const strip = (u: string) => u.replace(/\/$/, "");
  if (typeof window === "undefined") {
    return strip(
      process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    );
  }
  if (process.env.NEXT_PUBLIC_API_URL) return strip(process.env.NEXT_PUBLIC_API_URL);
  // Next dev only proxies /api/*; /ws/* must hit the FastAPI host directly.
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
