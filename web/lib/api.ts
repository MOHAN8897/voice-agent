const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export async function apiGet<T = unknown>(path: string): Promise<T> {
  const url = API_BASE ? `${API_BASE}${path}` : path;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export function wsUrl(path: string): string {
  const base = process.env.NEXT_PUBLIC_API_URL || (typeof window !== "undefined" ? window.location.origin : "");
  const wsBase = base.replace(/^http/, "ws");
  return `${wsBase}${path}`;
}
