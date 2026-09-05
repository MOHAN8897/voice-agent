"use client";

import { useCallback, useEffect, useState } from "react";
import { ensureArray } from "@/lib/ensure-array";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";
import {
  defaultStackForm,
  type ProviderEntry,
  type StackForm,
  type TierResolved,
} from "@/lib/test-studio-stack";

type TierRow = { tier: string; resolved?: TierResolved };

export function useStackCatalog(portal: "app" | "dev") {
  const [providers, setProviders] = useState<ProviderEntry[]>([]);
  const [tierStacks, setTierStacks] = useState<Record<string, TierResolved>>({});
  const [sttModes, setSttModes] = useState<string[]>(["transcribe", "translate"]);
  const [sttStreamTypes, setSttStreamTypes] = useState<string[]>(["fast", "accurate"]);
  const [catalog, setCatalog] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (portal === "dev") await refreshPortalSession("dev");

      let catalogRes = await portalFetch("dev", "/api/dev/stack/catalog");
      if (!catalogRes.ok) {
        catalogRes = await fetch("/api/settings/catalog", { credentials: "include" });
      }
      if (!catalogRes.ok) {
        setError(`Could not load provider catalog (${catalogRes.status}).`);
        return;
      }
      const cat = await catalogRes.json();
      setCatalog(cat);
      const raw = cat.providers?.providers ?? cat.providers ?? [];
      setProviders(ensureArray<ProviderEntry>(raw));
      setSttModes(ensureArray<string>(cat.stt?.modes));
      setSttStreamTypes(ensureArray<string>(cat.stt?.streamTypes));

      if (portal === "dev") {
        const tierRes = await portalFetch("dev", "/api/dev/stack/tiers");
        if (tierRes.ok) {
          const j = await tierRes.json();
          const map: Record<string, TierResolved> = {};
          for (const row of ensureArray<TierRow>(j.tiers)) {
            if (row.resolved) map[row.tier] = row.resolved;
          }
          setTierStacks(map);
        }
      }
    } catch {
      setError("Failed to load stack catalog.");
    } finally {
      setLoading(false);
    }
  }, [portal]);

  useEffect(() => {
    load();
  }, [load]);

  const stackForTier = useCallback((tier: string): StackForm => {
    return defaultStackForm(tierStacks[tier]);
  }, [tierStacks]);

  return { providers, tierStacks, sttModes, sttStreamTypes, catalog, loading, error, reload: load, stackForTier };
}
