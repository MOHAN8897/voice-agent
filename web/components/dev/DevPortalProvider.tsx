"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { refreshPortalSession } from "@/lib/auth-client";

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
        const ok = await refreshPortalSession("dev");
        const r = await fetch("/api/auth/dev-me", { credentials: "include", cache: "no-store" });
        if (!r.ok) {
          if (!cancelled) {
            setError(ok ? "Session check failed" : "Dev session required. Sign in at /dev/login");
            setReady(true);
          }
          return;
        }
        const j = await r.json();
        if (!cancelled) {
          setAuthenticated(Boolean(j.authenticated));
          setSubject(j.subject || null);
          setReady(true);
        }
      } catch {
        if (!cancelled) {
          setError("Cannot reach API. Start the backend on port 8000.");
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
        <div className="flex min-h-[40vh] items-center justify-center p-8">
          <p className="text-sm text-text-muted">Loading developer portal…</p>
        </div>
      )}
    </DevPortalContext.Provider>
  );
}

export function useDevPortal() {
  return useContext(DevPortalContext);
}
