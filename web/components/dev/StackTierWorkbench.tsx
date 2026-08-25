"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";

type ModelOption = { id: string; label?: string };
type ProviderEntry = {
  id: string;
  label?: string;
  enabled?: boolean;
  configured?: boolean;
  models?: { stt?: ModelOption[]; llm?: ModelOption[]; tts?: ModelOption[] };
};

type TierRow = {
  tier: string;
  resolved?: {
    stt?: { provider?: string; model?: string };
    llm?: { provider?: string; model?: string };
    tts?: { provider?: string; model?: string };
    language?: string;
  };
  error?: string;
};

type StackForm = {
  sttProvider: string;
  sttModel: string;
  llmProvider: string;
  llmModel: string;
  ttsProvider: string;
  ttsModel: string;
  language: string;
};

function defaultForm(row?: TierRow["resolved"]): StackForm {
  return {
    sttProvider: row?.stt?.provider || "sarvam",
    sttModel: row?.stt?.model || "saaras:v3",
    llmProvider: row?.llm?.provider || "openai",
    llmModel: row?.llm?.model || "gpt-5.6-luna",
    ttsProvider: row?.tts?.provider || "sarvam",
    ttsModel: row?.tts?.model || "bulbul:v3",
    language: row?.language || "te-IN",
  };
}

export function StackTierWorkbench() {
  const [tiers, setTiers] = useState<TierRow[]>([]);
  const [providers, setProviders] = useState<ProviderEntry[]>([]);
  const [configMode, setConfigMode] = useState("frontend");
  const [selected, setSelected] = useState("medium");
  const [form, setForm] = useState<StackForm>(defaultForm());
  const [status, setStatus] = useState("");
  const [testResult, setTestResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadTiers = useCallback(async () => {
    const tierRes = await portalFetch("dev", "/api/dev/stack/tiers");
    if (!tierRes.ok) {
      setError(`Could not load tiers (${tierRes.status}). Check dev login and API.`);
      return;
    }
    const j = await tierRes.json();
    setTiers(j.tiers || []);
    setConfigMode(j.config_mode || "frontend");
    const row = (j.tiers || []).find((t: TierRow) => t.tier === selected);
    if (row?.resolved) setForm(defaultForm(row.resolved));
  }, [selected]);

  const loadCatalog = useCallback(async () => {
    let catalogRes = await portalFetch("dev", "/api/dev/stack/catalog");
    if (!catalogRes.ok) {
      catalogRes = await fetch("/api/settings/catalog", { credentials: "include" });
    }
    if (!catalogRes.ok) {
      setError(`Could not load provider catalog (${catalogRes.status}). Restart the API server.`);
      return;
    }
    const cat = await catalogRes.json();
    const list = cat.providers?.providers ?? cat.providers ?? [];
    setProviders(Array.isArray(list) ? list : []);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError("");
      await refreshPortalSession("dev");
      await loadCatalog();
      if (!cancelled) await loadTiers();
      if (!cancelled) setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [loadCatalog, loadTiers]);

  useEffect(() => {
    const row = tiers.find((t) => t.tier === selected);
    if (row?.resolved) setForm(defaultForm(row.resolved));
  }, [selected, tiers]);

  const sttProviders = useMemo(() => providers.filter((p) => (p.models?.stt?.length ?? 0) > 0), [providers]);
  const llmProviders = useMemo(() => providers.filter((p) => (p.models?.llm?.length ?? 0) > 0), [providers]);
  const ttsProviders = useMemo(() => providers.filter((p) => (p.models?.tts?.length ?? 0) > 0), [providers]);

  function modelsFor(providerId: string, stage: "stt" | "llm" | "tts") {
    const p = providers.find((x) => x.id === providerId);
    return p?.models?.[stage] || [];
  }

  async function saveTier() {
    setStatus("Saving tier assignment…");
    const r = await portalFetch("dev", `/api/dev/stack/tiers/${selected}`, {
      method: "PUT",
      body: JSON.stringify(form),
    });
    setStatus(r.ok ? "Tier saved to database" : `Save failed (${r.status})`);
    if (r.ok) await loadTiers();
  }

  async function testStack() {
    setStatus("Testing combination…");
    setTestResult(null);
    const r = await portalFetch("dev", "/api/dev/stack/test", {
      method: "POST",
      body: JSON.stringify({
        tier: selected,
        stack: {
          sttProvider: form.sttProvider,
          sttModel: form.sttModel,
          llmProvider: form.llmProvider,
          llmModel: form.llmModel,
          ttsProvider: form.ttsProvider,
          ttsModel: form.ttsModel,
          language: form.language,
        },
      }),
    });
    const j = await r.json();
    if (r.ok) {
      setTestResult((j.resolved as Record<string, unknown>) || j);
      setStatus("Combination resolves successfully");
    } else {
      setStatus(`Stack test failed (${r.status})`);
    }
  }

  if (loading) return <p className="text-sm text-text-muted">Loading stack configuration…</p>;

  return (
    <div className="space-y-6">
      {error && (
        <p className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">{error}</p>
      )}

      <DevCard delayMs={0}>
        <p className="text-sm text-text-muted">
          Resolution mode: <span className="font-mono text-accent">{configMode}</span> · Assign stacks per tier before
          promotion. Enable providers and keys in Environment first.
        </p>
      </DevCard>

      <div className="flex flex-wrap gap-2">
        {["low", "medium", "premium"].map((tier) => (
          <button
            key={tier}
            type="button"
            onClick={() => setSelected(tier)}
            className={`rounded-xl px-4 py-2 text-sm font-medium capitalize transition-all ${
              selected === tier
                ? "bg-accent text-white shadow-glow"
                : "border border-surface-border bg-surface-card text-text-muted hover:border-accent/40"
            }`}
          >
            {tier}
          </button>
        ))}
      </div>

      {sttProviders.length === 0 && llmProviders.length === 0 && (
        <p className="text-sm text-warning">No providers in catalog. Enable toggles and API keys in Environment.</p>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <DevCard title="STT" description="Speech-to-text" delayMs={40}>
          <div className="space-y-3">
            <select
              className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm"
              value={form.sttProvider}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  sttProvider: e.target.value,
                  sttModel: modelsFor(e.target.value, "stt")[0]?.id || f.sttModel,
                }))
              }
            >
              {sttProviders.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label || p.id}{!p.configured ? " (no key)" : ""}
                </option>
              ))}
            </select>
            <select
              className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm"
              value={form.sttModel}
              onChange={(e) => setForm((f) => ({ ...f, sttModel: e.target.value }))}
            >
              {modelsFor(form.sttProvider, "stt").map((m) => (
                <option key={m.id} value={m.id}>{m.label || m.id}</option>
              ))}
            </select>
          </div>
        </DevCard>

        <DevCard title="LLM" delayMs={80}>
          <div className="space-y-3">
            <select
              className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm"
              value={form.llmProvider}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  llmProvider: e.target.value,
                  llmModel: modelsFor(e.target.value, "llm")[0]?.id || f.llmModel,
                }))
              }
            >
              {llmProviders.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label || p.id}{!p.configured ? " (no key)" : ""}
                </option>
              ))}
            </select>
            <select
              className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm"
              value={form.llmModel}
              onChange={(e) => setForm((f) => ({ ...f, llmModel: e.target.value }))}
            >
              {modelsFor(form.llmProvider, "llm").map((m) => (
                <option key={m.id} value={m.id}>{m.label || m.id}</option>
              ))}
            </select>
          </div>
        </DevCard>

        <DevCard title="TTS" delayMs={120}>
          <div className="space-y-3">
            <select
              className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm"
              value={form.ttsProvider}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  ttsProvider: e.target.value,
                  ttsModel: modelsFor(e.target.value, "tts")[0]?.id || f.ttsModel,
                }))
              }
            >
              {ttsProviders.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label || p.id}{!p.configured ? " (no key)" : ""}
                </option>
              ))}
            </select>
            <select
              className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm"
              value={form.ttsModel}
              onChange={(e) => setForm((f) => ({ ...f, ttsModel: e.target.value }))}
            >
              {modelsFor(form.ttsProvider, "tts").map((m) => (
                <option key={m.id} value={m.id}>{m.label || m.id}</option>
              ))}
            </select>
          </div>
        </DevCard>

        <DevCard title="Language" delayMs={160}>
          <select
            className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm"
            value={form.language}
            onChange={(e) => setForm((f) => ({ ...f, language: e.target.value }))}
          >
            <option value="te-IN">te-IN — Telugu</option>
            <option value="en-IN">en-IN — English (India)</option>
            <option value="hi-IN">hi-IN — Hindi</option>
          </select>
        </DevCard>
      </div>

      <DevCard title="Resolved preview" delayMs={200}>
        <pre className="max-h-48 overflow-auto rounded-xl border border-surface-border-subtle bg-surface-raised p-4 font-mono text-xs text-text-muted">
          {JSON.stringify(tiers.find((t) => t.tier === selected) || {}, null, 2)}
        </pre>
        {testResult && (
          <pre className="mt-4 max-h-48 overflow-auto rounded-xl border border-accent/20 bg-accent-dim/30 p-4 font-mono text-xs text-text-muted">
            {JSON.stringify(testResult, null, 2)}
          </pre>
        )}
      </DevCard>

      <div className="flex flex-wrap gap-3">
        <Button type="button" onClick={saveTier}>Save tier</Button>
        <Button type="button" variant="secondary" onClick={testStack}>Test combination</Button>
      </div>
      {status && <p className="text-sm text-text-muted">{status}</p>}
    </div>
  );
}
