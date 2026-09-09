"use client";

import { useCallback, useEffect, useRef } from "react";

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

type PrefsCacheEntry = {
  loaded: boolean;
  patched: boolean;
  data: TestStudioUiPrefs | null;
  promise: Promise<TestStudioUiPrefs | null> | null;
};

const prefsCache = new Map<string, PrefsCacheEntry>();

function cacheEntry(sessionId: string): PrefsCacheEntry {
  let entry = prefsCache.get(sessionId);
  if (!entry) {
    entry = { loaded: false, patched: false, data: null, promise: null };
    prefsCache.set(sessionId, entry);
  }
  return entry;
}

export function patchPrefsCache(sessionId: string, patch: TestStudioUiPrefs) {
  const entry = cacheEntry(sessionId);
  entry.loaded = true;
  entry.patched = true;
  entry.data = { ...(entry.data || {}), ...patch };
}

function fetchPrefsForSession(sessionId: string): Promise<TestStudioUiPrefs | null> {
  const entry = cacheEntry(sessionId);
  if (entry.loaded) {
    return Promise.resolve(entry.data);
  }
  if (!entry.promise) {
    entry.promise = fetch(
      `/api/test-studio/prefs?sessionId=${encodeURIComponent(sessionId)}`,
      { credentials: "include" }
    )
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        const incoming =
          j?.prefs && Object.keys(j.prefs).length > 0 ? (j.prefs as TestStudioUiPrefs) : null;
        if (entry.patched && entry.data) {
          entry.data = { ...(incoming || {}), ...entry.data };
        } else {
          entry.data = incoming;
        }
        entry.loaded = true;
        return entry.data;
      })
      .catch(() => {
        entry.loaded = true;
        entry.data = null;
        return null;
      });
  }
  return entry.promise;
}

export function useTestStudioPrefs(
  sessionId: string,
  prefs: TestStudioUiPrefs,
  onLoaded?: (loaded: TestStudioUiPrefs) => void
) {
  const loadedRef = useRef(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSavedRef = useRef("");
  const onLoadedRef = useRef(onLoaded);
  onLoadedRef.current = onLoaded;

  useEffect(() => {
    loadedRef.current = false;
    lastSavedRef.current = "";
    let cancelled = false;
    fetchPrefsForSession(sessionId).then((loaded) => {
      if (cancelled || loadedRef.current) return;
      onLoadedRef.current?.(loaded || {});
      loadedRef.current = true;
    });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const persist = useCallback(
    (next: TestStudioUiPrefs) => {
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
          body: JSON.stringify({ sessionId, ...next }),
        }).catch(() => {});
      }, 1200);
    },
    [sessionId]
  );

  useEffect(() => {
    persist(prefs);
  }, [prefs, persist]);

  return { markLoaded: () => { loadedRef.current = true; } };
}
