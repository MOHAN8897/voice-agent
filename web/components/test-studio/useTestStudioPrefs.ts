"use client";

import { useCallback, useEffect, useRef } from "react";
import { TEST_STUDIO_SESSION_ID } from "@/lib/test-studio-stack";

export type TestStudioUiPrefs = {
  studioTab?: "live" | "config" | "tune" | "debug";
  stackMode?: "tier" | "custom";
  tier?: string;
  channel?: "agent" | "pstn" | "browser";
  language?: string;
  stack?: Record<string, unknown>;
  fineTuneTab?: string;
};

export function useTestStudioPrefs(
  prefs: TestStudioUiPrefs,
  onLoaded?: (loaded: TestStudioUiPrefs) => void
) {
  const loadedRef = useRef(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/test-studio/prefs?sessionId=${encodeURIComponent(TEST_STUDIO_SESSION_ID)}`, {
      credentials: "include",
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (cancelled || loadedRef.current) return;
        if (j?.prefs && Object.keys(j.prefs).length > 0) {
          onLoaded?.(j.prefs as TestStudioUiPrefs);
        }
        loadedRef.current = true;
      })
      .catch(() => {
        loadedRef.current = true;
      });
    return () => {
      cancelled = true;
    };
  }, [onLoaded]);

  const persist = useCallback((next: TestStudioUiPrefs) => {
    if (!loadedRef.current) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      fetch("/api/test-studio/prefs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ sessionId: TEST_STUDIO_SESSION_ID, ...next }),
      }).catch(() => {});
    }, 600);
  }, []);

  useEffect(() => {
    persist(prefs);
  }, [prefs, persist]);

  return { markLoaded: () => { loadedRef.current = true; } };
}
