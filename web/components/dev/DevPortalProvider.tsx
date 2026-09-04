"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import {
  fetchPortalSession,
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
            setError(
              r.status === 401
                ? "Dev session required. Sign in at /dev/login"
                : "Session check failed"
            );
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
          setError(portalSessionErrorMessage("dev", err));
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
      {error && (
        <div className="border-b border-warning/30 bg-warning/10 px-6 py-3 text-sm text-warning">
          {error}
        </div>
      )}
      {ready ? children : (
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
      )}
    </DevPortalContext.Provider>
  );
}

export function useDevPortal() {
  return useContext(DevPortalContext);
}
