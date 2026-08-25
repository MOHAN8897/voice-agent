"use client";

import { useEffect, useState } from "react";
import { ensureArray } from "@/lib/ensure-array";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";

type ProviderRow = {
  id: string;
  enabled?: boolean;
  configured?: boolean;
  healthy?: boolean;
  adapter_available?: boolean;
  stages?: string[];
};

export function ProviderStatusGrid() {
  const [rows, setRows] = useState<ProviderRow[]>([]);
  const [chains, setChains] = useState<Record<string, string[]>>({ stt: [], llm: [], tts: [] });
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("");
  const [probeResults, setProbeResults] = useState<Record<string, { healthy?: boolean; latency_ms?: number }>>({});

  async function load() {
    await refreshPortalSession("dev");
    const r = await portalFetch("dev", "/api/dev/providers/status");
    if (r.ok) {
      const j = await r.json();
      setRows(ensureArray(j.providers));
      setChains(j.fallback_chains || { stt: [], llm: [], tts: [] });
    }
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  async function saveFallback() {
    setStatus("Saving fallback chains…");
    const r = await portalFetch("dev", "/api/dev/providers/fallback", {
      method: "PUT",
      body: JSON.stringify(chains),
    });
    setStatus(r.ok ? "Fallback chains saved" : "Save failed");
  }

  async function probe(id: string) {
    const r = await portalFetch("dev", `/api/dev/providers/${id}/probe`, { method: "POST" });
    const j = await r.json();
    setProbeResults((prev) => ({ ...prev, [id]: j }));
  }

  async function validate(id: string) {
    const r = await portalFetch("dev", `/api/dev/providers/${id}/validate-selection`, {
      method: "POST",
      body: JSON.stringify({ language: "te-IN" }),
    });
    const j = await r.json();
    setStatus(j.ok ? `Validate ${id}: OK` : `Validate ${id}: ${j.error?.message || "failed"}`);
  }

  if (loading) return <p className="text-sm text-text-muted">Loading provider status…</p>;

  return (
    <div className="space-y-6">
      <DevCard title="Fallback chains" description="Stage fallback order when primary provider fails">
        <div className="grid gap-4 sm:grid-cols-3">
          {(["stt", "llm", "tts"] as const).map((stage) => (
            <label key={stage} className="block text-sm">
              <span className="text-text-muted uppercase">{stage}</span>
              <input
                type="text"
                className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm font-mono"
                value={(chains[stage] || []).join(", ")}
                onChange={(e) =>
                  setChains((c) => ({
                    ...c,
                    [stage]: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                  }))
                }
              />
            </label>
          ))}
        </div>
        <Button type="button" variant="secondary" className="mt-4" onClick={saveFallback}>
          Save fallback chains
        </Button>
      </DevCard>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {rows.map((p, i) => (
          <DevCard key={p.id} delayMs={i * 50}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-semibold text-text">{p.id}</p>
                <p className="mt-1 font-mono text-[10px] uppercase tracking-wider text-text-subtle">
                  {(p.stages || []).join(" · ") || (p.enabled ? "enabled" : "disabled")}
                </p>
              </div>
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                  p.configured && p.adapter_available
                    ? "bg-success/15 text-success"
                    : "bg-warning/15 text-warning"
                }`}
              >
                {p.configured ? (p.adapter_available ? "ready" : "stub") : "missing key"}
              </span>
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-2 text-xs text-text-muted">
              <div>
                <dt>Configured</dt>
                <dd className="font-mono text-text">{p.configured ? "yes" : "no"}</dd>
              </div>
              <div>
                <dt>Probe</dt>
                <dd className="font-mono text-text">
                  {probeResults[p.id]?.latency_ms != null
                    ? `${probeResults[p.id].latency_ms}ms`
                    : "—"}
                </dd>
              </div>
            </dl>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button type="button" variant="ghost" onClick={() => probe(p.id)}>Health probe</Button>
              <Button type="button" variant="ghost" onClick={() => validate(p.id)}>Validate</Button>
            </div>
          </DevCard>
        ))}
      </div>
      {status && <p className="text-sm text-text-muted">{status}</p>}
    </div>
  );
}
