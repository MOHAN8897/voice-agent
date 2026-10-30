"use client";

import { useCallback, useEffect, useState } from "react";
import { portalFetch } from "@/lib/auth-client";

/** Platform-wide switch: synthesize the greeting while the call rings. */
export function PrewarmGreetingCard() {
  const [prewarmGreetingEnabled, setPrewarmGreetingEnabled] = useState<boolean>(true);
  const [prewarmLoading, setPrewarmLoading] = useState<boolean>(false);

  const loadPrewarmGreeting = useCallback(async () => {
    try {
      const res = await portalFetch("dev", "/api/dev/stack/prewarm-greeting");
      if (!res.ok) return;
      const data = await res.json();
      if (typeof data.enabled === "boolean") setPrewarmGreetingEnabled(data.enabled);
    } catch {
      // Non-blocking prewarm greeting fetch
    }
  }, []);

  useEffect(() => {
    void loadPrewarmGreeting();
  }, [loadPrewarmGreeting]);

  const togglePrewarmGreeting = async (nextState: boolean) => {
    setPrewarmLoading(true);
    try {
      const res = await portalFetch("dev", "/api/dev/stack/prewarm-greeting", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: nextState }),
      });
      if (res.ok) setPrewarmGreetingEnabled(nextState);
    } catch {
      // Non-blocking error handling
    } finally {
      setPrewarmLoading(false);
    }
  };

  return (
    <div className="mt-6 rounded-xl border border-surface-border-subtle bg-surface-raised/40 p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="max-w-2xl">
          <div className="flex items-center gap-2.5">
            <h4 className="text-sm font-semibold text-text">
              Global Prewarm Greeting (Instant First Audio)
            </h4>
            <span
              className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider border ${
                prewarmGreetingEnabled
                  ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                  : "bg-surface-border/20 text-text-subtle border-surface-border/40"
              }`}
            >
              {prewarmGreetingEnabled ? "Active (Global)" : "Disabled (Standard Playout)"}
            </span>
          </div>
          <p className="mt-2 text-xs text-text-muted leading-relaxed">
            Pre-synthesizes the outbound agent greeting during carrier ring and connection time so caller hears the opening instantly (&lt;200ms) upon answering. Applies to all PSTN calls globally. When disabled, the agent synthesizes greeting on live stream pickup.
          </p>
          <div className="mt-2 flex items-center gap-2">
            <span className="text-[10px] font-mono text-text-subtle">
              API: PATCH /api/dev/stack/prewarm-greeting
            </span>
            <span className="text-[10px] text-text-subtle">·</span>
            <span className="text-[10px] text-text-subtle">
              Scope: Universal Platform
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            disabled={prewarmLoading}
            onClick={() => void togglePrewarmGreeting(!prewarmGreetingEnabled)}
            className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-accent-primary focus:ring-offset-2 ${
              prewarmGreetingEnabled ? "bg-emerald-500" : "bg-surface-border"
            } ${prewarmLoading ? "opacity-50 cursor-not-allowed" : ""}`}
            role="switch"
            aria-checked={prewarmGreetingEnabled}
            aria-label="Toggle Prewarm Greeting"
          >
            <span
              aria-hidden="true"
              className={`pointer-events-none inline-block size-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                prewarmGreetingEnabled ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
          <span className="text-xs font-medium text-text select-none min-w-[58px]">
            {prewarmGreetingEnabled ? "Enabled" : "Disabled"}
          </span>
        </div>
      </div>
    </div>
  );
}
