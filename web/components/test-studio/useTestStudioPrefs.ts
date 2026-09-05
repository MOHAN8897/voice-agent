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

function prefsKey(prefs: TestStudioUiPrefs): string {
  return JSON.stringify(prefs);
}

let globalPrefsLoaded = false;
let globalPrefsData: TestStudioUiPrefs | null = null;
let globalPrefsPromise: Promise<TestStudioUiPrefs | null> | null = null;

function fetchPrefsOnce(): Promise<TestStudioUiPrefs | null> {
  if (globalPrefsLoaded) {
    return Promise.resolve(globalPrefsData);
  }
  if (!globalPrefsPromise) {
    globalPrefsPromise = fetch(
      `/api/test-studio/prefs?sessionId=${encodeURIComponent(TEST_STUDIO_SESSION_ID)}`,
      { credentials: "include" }
    )
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        globalPrefsLoaded = true;
        if (j?.prefs && Object.keys(j.prefs).length > 0) {
          globalPrefsData = j.prefs as TestStudioUiPrefs;
          return globalPrefsData;
        }
        globalPrefsData = null;
        return null;
      })
      .catch(() => {
        globalPrefsLoaded = true;
        globalPrefsData = null;
        return null;
      });
  }
  return globalPrefsPromise;
}

export function useTestStudioPrefs(
  prefs: TestStudioUiPrefs,
  onLoaded?: (loaded: TestStudioUiPrefs) => void
) {
  const loadedRef = useRef(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSavedRef = useRef("");
  const onLoadedRef = useRef(onLoaded);
  onLoadedRef.current = onLoaded;

  useEffect(() => {
    let cancelled = false;
    fetchPrefsOnce().then((loaded) => {
      if (cancelled || loadedRef.current) return;
      if (loaded) {
        onLoadedRef.current?.(loaded);
      }
      loadedRef.current = true;
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const persist = useCallback((next: TestStudioUiPrefs) => {
    if (!loadedRef.current) return;
    const key = prefsKey(next);
    if (key === lastSavedRef.current) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      lastSavedRef.current = key;
      fetch("/api/test-studio/prefs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ sessionId: TEST_STUDIO_SESSION_ID, ...next }),
      }).catch(() => {});
    }, 1200);
  }, []);

  useEffect(() => {
    persist(prefs);
  }, [prefs, persist]);

  return { markLoaded: () => { loadedRef.current = true; } };
}
