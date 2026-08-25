"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";

type EnvRow = {
  env_name: string;
  field: string;
  type: string;
  value?: string | boolean;
  configured?: boolean;
  masked?: string;
  source?: string;
};

type EnvGroup = Record<string, EnvRow[]>;

export function EnvironmentPanel() {
  const [groups, setGroups] = useState<EnvGroup>({});
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [toggles, setToggles] = useState<Record<string, boolean>>({});
  const [strings, setStrings] = useState<Record<string, string>>({});
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    await refreshPortalSession("dev");
    const r = await portalFetch("dev", "/api/dev/environment");
    if (!r.ok) {
      setError(`Failed to load environment (${r.status}). Sign in at /dev/login`);
      setLoading(false);
      return;
    }
    const j = await r.json();
    const g = j.environment?.groups || {};
    setGroups(g);
    const t: Record<string, boolean> = {};
    const s: Record<string, string> = {};
    Object.values(g).flat().forEach((row) => {
      const r = row as EnvRow;
      if (r.type === "toggle") t[r.field] = Boolean(r.value);
      if (r.type === "string" && typeof r.value === "string") s[r.field] = r.value;
    });
    setToggles(t);
    setStrings(s);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const secretRows = useMemo(
    () => (groups.provider_keys || []).concat(groups.telephony || []).filter((r) => r.type === "secret"),
    [groups]
  );

  async function save() {
    setStatus("Saving…");
    const patch: Record<string, unknown> = { ...toggles, ...strings };
    Object.entries(draft).forEach(([k, v]) => {
      if (v.trim()) patch[k] = v.trim();
    });
    const r = await portalFetch("dev", "/api/dev/environment", {
      method: "PUT",
      body: JSON.stringify(patch),
    });
    setStatus(r.ok ? "Saved — provider registry reloaded" : "Save failed");
    if (r.ok) {
      setDraft({});
      await load();
    }
  }

  if (loading) return <p className="text-sm text-text-muted">Loading environment…</p>;
  if (error) return <p className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">{error}</p>;

  const platformRows = (groups.platform || []).filter((r) => r.type === "string");

  return (
    <div className="space-y-6">
      <DevCard title="Platform mode" description="Config mode controls how stacks resolve at call/start" delayMs={0}>
        <div className="grid gap-4 sm:grid-cols-3">
          {platformRows.map((row) => (
            <div key={row.field}>
              <p className="label-caps text-text-subtle">{row.env_name}</p>
              <select
                className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm"
                value={strings[row.field] || String(row.value)}
                onChange={(e) => setStrings((s) => ({ ...s, [row.field]: e.target.value }))}
              >
                {row.field === "voice_agent_config_mode" && (
                  <>
                    <option value="frontend">frontend</option>
                    <option value="env">env</option>
                  </>
                )}
                {row.field === "voice_agent_tier" && (
                  <>
                    <option value="low">low</option>
                    <option value="medium">medium</option>
                    <option value="premium">premium</option>
                  </>
                )}
                {row.field === "app_environment" && (
                  <>
                    <option value="development">development</option>
                    <option value="staging">staging</option>
                    <option value="production">production</option>
                  </>
                )}
              </select>
              <p className="mt-1 text-xs text-text-subtle">source: {row.source}</p>
            </div>
          ))}
        </div>
      </DevCard>

      <DevCard title="Provider toggles" delayMs={60}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {(groups.provider_toggles || []).map((row) => (
            <label
              key={row.field}
              className="flex items-center justify-between rounded-xl border border-surface-border-subtle bg-surface-raised px-3 py-2"
            >
              <span className="text-sm text-text">{row.env_name}</span>
              <input
                type="checkbox"
                checked={toggles[row.field] ?? Boolean(row.value)}
                onChange={(e) => setToggles((t) => ({ ...t, [row.field]: e.target.checked }))}
              />
            </label>
          ))}
        </div>
      </DevCard>

      <DevCard
        title="API keys"
        description="Stored server-side in data/dev_secrets.json — masked in UI"
        delayMs={120}
      >
        <div className="space-y-4">
          {secretRows.map((row) => (
            <div key={row.field}>
              <label className="text-sm font-medium text-text">{row.env_name}</label>
              <p className="mt-0.5 text-xs text-text-muted">
                {row.configured ? `Current: ${row.masked}` : "Not configured"} · {row.source}
              </p>
              <input
                type="password"
                placeholder="Paste new key to update"
                className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm"
                value={draft[row.field] || ""}
                onChange={(e) => setDraft((d) => ({ ...d, [row.field]: e.target.value }))}
              />
            </div>
          ))}
        </div>
      </DevCard>

      <Button type="button" onClick={save}>Save environment</Button>
      {status && <p className="text-sm text-text-muted">{status}</p>}
    </div>
  );
}
