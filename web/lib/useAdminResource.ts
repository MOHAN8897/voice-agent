"use client";

import { useCallback, useEffect, useState } from "react";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";

/**
 * Authenticated dev-portal fetch (includes X-CSRF-Token for mutating calls).
 *
 * Lives here rather than in a page because the admin console spans several routes.
 * Non-2xx responses throw with the server's own message, so a permission problem
 * never renders as an empty table.
 */
export async function devFetch(
  path: string,
  init: RequestInit = {}
): Promise<unknown> {
  let res = await portalFetch("dev", path, init);
  // Session CSRF can go stale after long idle — refresh once then retry.
  if (res.status === 403) {
    const probe = await res.clone().text();
    if (/csrf/i.test(probe)) {
      await refreshPortalSession("dev");
      res = await portalFetch("dev", path, init);
    }
  }
  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!res.ok) {
    // The API returns the message in a few shapes depending on which error handler
    // answered: {detail: string}, {detail: {error: {message}}}, or {error: {...}}.
    const detail = body as {
      detail?: string | { error?: { message?: string } };
      error?: { message?: string };
    } | null;
    const asObject = typeof detail === "object" && detail !== null ? detail : null;
    const detailField = asObject?.detail;
    const message =
      (typeof detailField === "string" ? detailField : undefined) ??
      (typeof detailField === "object" && detailField !== null
        ? detailField.error?.message
        : undefined) ??
      asObject?.error?.message ??
      (typeof body === "string" && body ? body : undefined) ??
      `${res.status} ${res.statusText}`;
    throw new Error(message);
  }
  return body;
}

/**
 * One loader for the admin console.
 *
 * Every value rendered here comes from `/api/dev/admin/*`. The admin screens must
 * never substitute a plausible number for a missing one, so a failed load is
 * surfaced as an error state rather than a zero.
 */
export function useAdminResource<T>(path: string, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const body = (await devFetch(path)) as T;
      setData(body);
    } catch (e) {
      setError(e instanceof Error ? e.message : `Could not load ${path}`);
      setData(null);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, ...deps]);

  return { data, error, loading, reload: load };
}

/**
 * Perform a mutating admin action and return the parsed response.
 *
 * Throws the server's own error message so a permission failure never renders as
 * a silently ignored click.
 */
export async function adminAction<T = unknown>(
  path: string,
  init: { method?: string; body?: unknown } = {}
): Promise<T> {
  return (await devFetch(path, {
    method: init.method ?? "POST",
    ...(init.body === undefined
      ? {}
      : {
          body: JSON.stringify(init.body),
          headers: { "Content-Type": "application/json" },
        }),
  })) as T;
}

export function formatUsd(cents: number | null | undefined): string {
  const v = Number(cents ?? 0) / 100;
  return v.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

export function formatInr(paise: number | null | undefined): string {
  const v = Number(paise ?? 0) / 100;
  return v.toLocaleString("en-IN", { style: "currency", currency: "INR" });
}

export function formatMinutes(seconds: number | null | undefined): string {
  const m = Number(seconds ?? 0) / 60;
  if (m < 1) return `${Math.round(Number(seconds ?? 0))}s`;
  if (m < 60) return `${m.toFixed(1)} min`;
  return `${Math.floor(m / 60)}h ${Math.round(m % 60)}m`;
}

export function formatDay(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

export function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}
