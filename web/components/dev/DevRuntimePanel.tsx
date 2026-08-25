"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";

type Catalog = {
  stt?: { vad?: { silenceMs?: number[]; threshold?: number[] } };
  openai?: {
    defaults?: Record<string, unknown>;
    temperature?: number[];
    maxTokens?: number[];
    brainPromptBudget?: number[];
  };
  tts?: { voicePresets?: { id: string; label: string }[] };
};

export function DevRuntimePanel() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [status, setStatus] = useState("");

  const load = useCallback(async () => {
    await refreshPortalSession("dev");
    const [catR, runR] = await Promise.all([
      fetch("/api/settings/catalog", { credentials: "include" }),
      fetch("/api/settings/runtime?sessionId=dev-studio", { credentials: "include" }),
    ]);
    if (catR.ok) setCatalog(await catR.json());
    if (runR.ok) {
      const j = await runR.json();
      setValues(j.values || {});
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function save(patch: Record<string, unknown>) {
    setStatus("Saving runtime…");
    const r = await portalFetch("dev", "/api/settings/runtime", {
      method: "POST",
      body: JSON.stringify({ sessionId: "dev-studio", ...patch }),
    });
    setStatus(r.ok ? "Runtime updated" : "Save failed");
    if (r.ok) await load();
  }

  const defaults = catalog?.openai?.defaults || {};

  return (
    <div className="space-y-6">
      <DevCard title="Voice runtime fine-tune" description="STT VAD, barge-in, TTS chunking, LLM budget — dev session overlay">
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="space-y-4">
            <label className="block text-sm">
              <span className="text-text-muted">STT silence (ms)</span>
              <input
                type="number"
                className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm"
                value={Number(values.sttSilenceMs ?? defaults.sttSilenceMs ?? 500)}
                onChange={(e) => setValues((v) => ({ ...v, sttSilenceMs: Number(e.target.value) }))}
              />
            </label>
            <label className="block text-sm">
              <span className="text-text-muted">Barge min words</span>
              <input
                type="number"
                className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm"
                value={Number(values.bargeMinWords ?? defaults.bargeMinWords ?? 3)}
                onChange={(e) => setValues((v) => ({ ...v, bargeMinWords: Number(e.target.value) }))}
              />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={Boolean(values.bargeRequireVad ?? defaults.bargeRequireVad ?? true)}
                onChange={(e) => setValues((v) => ({ ...v, bargeRequireVad: e.target.checked }))}
              />
              <span className="text-text-muted">Barge requires VAD start</span>
            </label>
          </div>
          <div className="space-y-4">
            <label className="block text-sm">
              <span className="text-text-muted">Brain prompt budget tokens</span>
              <input
                type="number"
                className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm"
                value={Number(values.brainPromptBudgetTokens ?? defaults.brainPromptBudgetTokens ?? 2000)}
                onChange={(e) => setValues((v) => ({ ...v, brainPromptBudgetTokens: Number(e.target.value) }))}
              />
            </label>
            <label className="block text-sm">
              <span className="text-text-muted">TTS min buffer / max chunk</span>
              <div className="mt-2 flex gap-2">
                <input
                  type="number"
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm"
                  value={Number(values.ttsMinBuffer ?? defaults.ttsMinBuffer ?? 30)}
                  onChange={(e) => setValues((v) => ({ ...v, ttsMinBuffer: Number(e.target.value) }))}
                />
                <input
                  type="number"
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm"
                  value={Number(values.ttsMaxChunk ?? defaults.ttsMaxChunk ?? 80)}
                  onChange={(e) => setValues((v) => ({ ...v, ttsMaxChunk: Number(e.target.value) }))}
                />
              </div>
            </label>
            <label className="block text-sm">
              <span className="text-text-muted">Voice preset</span>
              <select
                className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm"
                value={String(values.voicePresetId ?? defaults.voicePresetId ?? "")}
                onChange={(e) => setValues((v) => ({ ...v, voicePresetId: e.target.value }))}
              >
                {(catalog?.tts?.voicePresets || []).map((p) => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))}
              </select>
            </label>
          </div>
        </div>
        <div className="mt-6 flex gap-3">
          <Button type="button" onClick={() => save(values)}>Apply to dev-studio session</Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() =>
              fetch("/api/settings/runtime?sessionId=dev-studio", {
                method: "DELETE",
                credentials: "include",
              }).then(() => load())
            }
          >
            Clear overrides
          </Button>
        </div>
      </DevCard>
      {status && <p className="text-sm text-text-muted">{status}</p>}
    </div>
  );
}
