"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import {
  fetchPortalSession,
  getCsrfToken,
  portalSessionErrorMessage,
  storeCsrfToken,
} from "@/lib/auth-client";

type DevPortalContextValue = {
  ready: boolean;
  authenticated: boolean;
  subject: string | null;
  error: string | null;
};

const DevPortalContext = createContext<DevPortalContextValue>({
  ready: false,
  authenticated: false,
  subject: null,
  error: null,
});

export function DevPortalProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [subject, setSubject] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetchPortalSession("dev");
        if (!r.ok) {
          if (!cancelled) {
            const hasExistingToken = Boolean(getCsrfToken("dev"));
            if (r.status === 401) {
              setError("Dev session required. Sign in at /dev/login");
              setAuthenticated(false);
            } else if (hasExistingToken) {
              // Service temporarily degraded or restarting: keep panel loaded
              setAuthenticated(true);
              setError("Backend services temporarily unreachable. Retrying automatically…");
            } else {
              setError("Session check failed");
              setAuthenticated(false);
            }
          }
          return;
        }
        const j = await r.json();
        if (!cancelled) {
          setAuthenticated(Boolean(j.authenticated));
          setSubject(j.subject || null);
          if (j.csrf_token) {
            storeCsrfToken("dev", j.csrf_token);
          }
        }
      } catch (err) {
        if (!cancelled) {
          const hasExistingToken = Boolean(getCsrfToken("dev"));
          if (hasExistingToken) {
            setAuthenticated(true);
            setError("Backend network connection interrupted. Admin tools remain active.");
          } else {
            setError(portalSessionErrorMessage("dev", err));
            setAuthenticated(false);
          }
        }
      } finally {
        if (!cancelled) {
          setReady(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <DevPortalContext.Provider value={{ ready, authenticated, subject, error }}>
      {!ready ? (
        <div className="flex min-h-[40vh] flex-col items-center justify-center gap-2 p-8 text-center">
          <p className="text-sm text-text-muted">Loading developer portal…</p>
          <p className="max-w-md text-xs text-text-muted">
            If this stays here, open{" "}
            <a href="http://localhost:3000/dev/login" className="text-accent underline">
              localhost:3000/dev/login
            </a>{" "}
            or restart with <code className="text-text">npm run share</code>.
          </p>
        </div>
      ) : authenticated ? (
        <>
          {error && (
            <div className="border-b border-warning/30 bg-warning/10 px-6 py-3 text-sm text-warning">
              {error}
            </div>
          )}
          {children}
        </>
      ) : (
        <main className="flex min-h-screen items-center justify-center bg-surface-chassis p-6">
          <section className="w-full max-w-md rounded-skeuo-lg border border-surface-border-subtle bg-surface-panel p-6 text-center shadow-lg">
            <h1 className="text-lg font-semibold text-text">Developer sign-in required</h1>
            <p className="mt-2 text-sm text-text-muted" role={error ? "alert" : undefined}>
              {error || "Sign in with an authorized developer account to open this panel."}
            </p>
            <Link
              href="/dev/login"
              className="mt-5 inline-flex min-h-10 items-center justify-center rounded-skeuo-sm bg-accent-primary px-4 py-2 text-sm font-semibold text-white"
            >
              Sign in to developer portal
            </Link>
          </section>
        </main>
      )}
    </DevPortalContext.Provider>
  );
}

export function useDevPortal() {
  return useContext(DevPortalContext);
}
