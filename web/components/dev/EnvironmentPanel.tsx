"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";
import { ensureArray } from "@/lib/ensure-array";

type EnvRow = {
  env_name: string;
  field: string;
  type: string;
  value?: string | boolean;
  configured?: boolean;
  masked?: string;
  source?: string;
  editable?: boolean;
  cleared?: boolean;
};

type EnvGroup = Record<string, EnvRow[]>;

type SaveResult = {
  applied_keys?: string[];
  rejected?: Array<{ field: string; reason: string }>;
};

function StatusBadge({ configured, on }: { configured?: boolean; on?: boolean }) {
  if (on !== undefined) {
    return on ? (
      <span className="rounded-full bg-success/15 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-success">
        On
      </span>
    ) : (
      <span className="rounded-full bg-surface-raised px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
        Off
      </span>
    );
  }
  if (configured) {
    return (
      <span className="rounded-full bg-success/15 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-success">
        Configured
      </span>
    );
  }
  return (
    <span className="rounded-full border border-dashed border-surface-border px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-text-subtle">
      Not set
    </span>
  );
}

function SourceBadge({ source }: { source?: string }) {
  if (!source) return null;
  return (
    <span className="rounded-md bg-surface-raised px-1.5 py-0.5 font-mono text-[10px] uppercase text-text-subtle">
      {source}
    </span>
  );
}

function SecretRow({
  row,
  draft,
  onDraft,
  onRevert,
  onClear,
}: {
  row: EnvRow;
  draft: string;
  onDraft: (v: string) => void;
  onRevert: () => void;
  onClear: () => void;
}) {
  const configured = Boolean(row.configured);
  const cleared = Boolean(row.cleared);
  return (
    <div
      className={`rounded-xl border p-4 transition-colors ${
        configured ? "border-success/25 bg-success/[0.04]" : "border-dashed border-surface-border bg-surface-raised/40"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-mono text-xs font-medium text-text">{row.env_name}</p>
          <p className="mt-0.5 font-mono text-[10px] text-text-subtle">{row.field}</p>
        </div>
        <div className="flex items-center gap-2">
          <SourceBadge source={row.source} />
          <StatusBadge configured={configured} />
        </div>
      </div>
      <div className="mt-3">
        {configured ? (
          <div className="rounded-lg border border-surface-border-subtle bg-surface px-3 py-2.5 font-mono text-sm text-text-muted">
            {row.masked || "••••••••"}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-surface-border px-3 py-2.5 text-sm text-text-subtle">
            {cleared ? "Cleared in overlay — .env value hidden" : "Empty — no value in .env or overlay"}
          </div>
        )}
        <input
          type="password"
          placeholder={configured ? "Paste new key to replace" : "Paste key to configure"}
          className="mt-2 w-full rounded-xl border border-surface-border bg-surface px-3 py-2 text-sm"
          value={draft}
          onChange={(e) => onDraft(e.target.value)}
        />
        {row.source === "overlay" && (
          <div className="mt-2 flex flex-wrap gap-3">
            <button type="button" onClick={onRevert} className="text-xs text-text-muted hover:text-accent">
              Revert to .env
            </button>
            {configured && (
              <button type="button" onClick={onClear} className="text-xs text-text-muted hover:text-warning">
                Clear key
              </button>
            )}
          </div>
        )}
        {row.source === "env" && configured && (
          <button type="button" onClick={onClear} className="mt-2 text-xs text-text-muted hover:text-warning">
            Clear key (hide .env value)
          </button>
        )}
      </div>
    </div>
  );
}

function StringConfigRow({
  row,
  value,
  onChange,
  onRevert,
}: {
  row: EnvRow;
  value: string;
  onChange: (v: string) => void;
  onRevert: () => void;
}) {
  const configured = Boolean(value?.trim());
  return (
    <div className="rounded-xl border border-surface-border-subtle bg-surface-raised p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-mono text-xs font-medium text-text">{row.env_name}</p>
        <div className="flex items-center gap-2">
          <SourceBadge source={row.source} />
          <StatusBadge configured={configured} />
        </div>
      </div>
      <input
        type="text"
        className="mt-3 w-full rounded-xl border border-surface-border bg-surface px-3 py-2 text-sm font-mono"
        value={value}
        placeholder="Not set"
        onChange={(e) => onChange(e.target.value)}
      />
      {row.source === "overlay" && (
        <button type="button" onClick={onRevert} className="mt-2 text-xs text-text-muted hover:text-accent">
          Revert to .env
        </button>
      )}
    </div>
  );
}

function ToggleRow({
  row,
  checked,
  onChange,
  onRevert,
}: {
  row: EnvRow;
  checked: boolean;
  onChange: (v: boolean) => void;
  onRevert?: () => void;
}) {
  return (
    <label
      className={`flex items-center justify-between gap-3 rounded-xl border p-3 transition-colors ${
        checked ? "border-success/25 bg-success/[0.04]" : "border-surface-border-subtle bg-surface-raised"
      }`}
    >
      <div className="min-w-0">
        <p className="font-mono text-xs font-medium text-text">{row.env_name}</p>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <SourceBadge source={row.source} />
          <StatusBadge on={checked} />
        </div>
        {row.source === "overlay" && onRevert && (
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              onRevert();
            }}
            className="mt-1 text-xs text-text-muted hover:text-accent"
          >
            Revert to .env
          </button>
        )}
      </div>
      <input
        type="checkbox"
        className="h-4 w-4 shrink-0 accent-accent"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
    </label>
  );
}

export function EnvironmentPanel() {
  const [groups, setGroups] = useState<EnvGroup>({});
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [toggles, setToggles] = useState<Record<string, boolean>>({});
  const [strings, setStrings] = useState<Record<string, string>>({});
  const [status, setStatus] = useState("");
  const [saveResult, setSaveResult] = useState<SaveResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [overlayKeys, setOverlayKeys] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    await refreshPortalSession("dev");
    const r = await portalFetch("dev", "/api/dev/environment");
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      setError(
        j.detail?.error?.message ||
          `Failed to load environment (${r.status}). Sign in at /dev/login`
      );
      setLoading(false);
      return;
    }
    const j = await r.json();
    const env = j.environment || {};
    const g = env.groups || {};
    setGroups(g);
    setOverlayKeys(env.overlay_keys || []);
    const t: Record<string, boolean> = {};
    const s: Record<string, string> = {};
    Object.values(g).flat().forEach((row) => {
      const r = row as EnvRow;
      if (r.type === "toggle" && r.editable) t[r.field] = Boolean(r.value);
      if (r.type === "string") {
        if (typeof r.value === "string") s[r.field] = r.value;
        else if (r.value != null) s[r.field] = String(r.value);
      }
    });
    setToggles(t);
    setStrings(s);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function clearSecret(field: string) {
    setStatus(`Clearing ${field}…`);
    const r = await portalFetch("dev", "/api/dev/environment", {
      method: "PATCH",
      body: JSON.stringify({ [field]: "" }),
    });
    if (r.ok) {
      setStatus(`Cleared ${field} in overlay`);
      setDraft((d) => {
        const next = { ...d };
        delete next[field];
        return next;
      });
      await load();
    } else {
      const j = await r.json().catch(() => ({}));
      setStatus(j.detail?.error?.message || `Could not clear ${field}`);
    }
  }

  async function revertField(field: string) {
    setStatus(`Reverting ${field}…`);
    const r = await portalFetch("dev", `/api/dev/environment/${encodeURIComponent(field)}`, {
      method: "DELETE",
    });
    if (r.ok) {
      setStatus(`Reverted ${field} — using .env value`);
      setDraft((d) => {
        const next = { ...d };
        delete next[field];
        return next;
      });
      await load();
    } else {
      setStatus(`Could not revert ${field}`);
    }
  }

  const secretRows = useMemo(
    () => (groups.provider_keys || []).concat(groups.telephony || []).filter((r) => r.type === "secret"),
    [groups]
  );

  const toggleRows = useMemo(() => {
    const platformToggles = (groups.platform || []).filter((r) => r.type === "toggle" && r.editable);
    return [
      ...(groups.provider_toggles || []),
      ...(groups.telephony || []).filter((r) => r.type === "toggle"),
      ...platformToggles,
    ];
  }, [groups]);

  const telephonyStrings = useMemo(
    () => (groups.telephony || []).filter((r) => r.type === "string"),
    [groups]
  );

  const registryToggle = useMemo(
    () => (groups.platform || []).find((r) => r.field === "use_provider_registry"),
    [groups]
  );

  const stats = useMemo(() => {
    const secretsConfigured = secretRows.filter((r) => r.configured).length;
    const togglesOn = toggleRows.filter((r) => toggles[r.field] ?? Boolean(r.value)).length;
    return {
      secretsConfigured,
      secretsTotal: secretRows.length,
      togglesOn,
      togglesTotal: toggleRows.length,
    };
  }, [secretRows, toggleRows, toggles]);

  async function save() {
    setSaving(true);
    setStatus("Saving to server overlay…");
    setSaveResult(null);
    const patch: Record<string, unknown> = { ...toggles };
    Object.entries(strings).forEach(([k, v]) => {
      if (typeof v === "string" && v.trim()) patch[k] = v.trim();
    });
    Object.entries(draft).forEach(([k, v]) => {
      if (v.trim()) patch[k] = v.trim();
    });
    const r = await portalFetch("dev", "/api/dev/environment", {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
    const j = await r.json().catch(() => ({}));
    if (r.ok) {
      setSaveResult({ applied_keys: j.applied_keys, rejected: j.rejected });
      const applied = (j.applied_keys || []).length;
      setStatus(
        applied > 0
          ? `Saved ${applied} field(s) to data/dev_secrets.json — provider registry reloaded`
          : "No changes applied"
      );
      setDraft({});
      await load();
    } else {
      setStatus(j.detail?.error?.message || `Save failed (${r.status})`);
    }
    setSaving(false);
  }

  async function reloadRegistry() {
    setStatus("Reloading overlay from disk…");
    const r = await portalFetch("dev", "/api/dev/environment/reload", { method: "POST" });
    setStatus(r.ok ? "Overlay reloaded" : "Reload failed");
    if (r.ok) await load();
  }

  if (loading) return <p className="text-sm text-text-muted">Loading environment…</p>;
  if (error) return <p className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">{error}</p>;

  const platformRows = (groups.platform || []).filter((r) => r.type === "string");

  return (
    <div className="space-y-6">
      <DevCard
        title="Environment overview"
        description="UI changes persist to data/dev_secrets.json and apply immediately (overlay over .env)"
        delayMs={0}
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-xl border border-surface-border-subtle bg-surface-raised p-4">
            <p className="text-xs text-text-muted">API keys configured</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-text">
              {stats.secretsConfigured}
              <span className="text-base font-normal text-text-subtle"> / {stats.secretsTotal}</span>
            </p>
          </div>
          <div className="rounded-xl border border-surface-border-subtle bg-surface-raised p-4">
            <p className="text-xs text-text-muted">Provider toggles on</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-text">
              {stats.togglesOn}
              <span className="text-base font-normal text-text-subtle"> / {stats.togglesTotal}</span>
            </p>
          </div>
          <div className="rounded-xl border border-surface-border-subtle bg-surface-raised p-4">
            <p className="text-xs text-text-muted">Overlay keys</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-text">{overlayKeys.length}</p>
          </div>
        </div>
      </DevCard>

      <DevCard title="Platform mode" description="Config mode controls how stacks resolve at call/start" delayMs={40}>
        <div className="grid gap-4 sm:grid-cols-3">
          {platformRows.map((row) => (
            <div key={row.field} className="rounded-xl border border-surface-border-subtle bg-surface-raised p-4">
              <div className="flex items-center justify-between gap-2">
                <p className="font-mono text-xs font-medium text-text">{row.env_name}</p>
                <SourceBadge source={row.source} />
              </div>
              <select
                className="mt-3 w-full rounded-xl border border-surface-border bg-surface px-3 py-2 text-sm"
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
              {row.source === "overlay" && (
                <button
                  type="button"
                  onClick={() => revertField(row.field)}
                  className="mt-2 text-xs text-text-muted hover:text-accent"
                >
                  Revert to .env
                </button>
              )}
            </div>
          ))}
        </div>
        {registryToggle && (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-surface-border-subtle bg-surface-raised p-4">
            <div>
              <p className="font-mono text-xs font-medium text-text">{registryToggle.env_name}</p>
              <p className="mt-1 text-xs text-text-muted">Read-only — set USE_PROVIDER_REGISTRY in .env</p>
            </div>
            <div className="flex items-center gap-2">
              <SourceBadge source={registryToggle.source} />
              <StatusBadge on={Boolean(registryToggle.value)} />
            </div>
          </div>
        )}
      </DevCard>

      <DevCard title="Provider toggles" description="Enable or disable provider adapters" delayMs={80}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {toggleRows.map((row) => (
            <ToggleRow
              key={row.field}
              row={row}
              checked={toggles[row.field] ?? Boolean(row.value)}
              onChange={(v) => setToggles((t) => ({ ...t, [row.field]: v }))}
              onRevert={row.source === "overlay" ? () => revertField(row.field) : undefined}
            />
          ))}
        </div>
      </DevCard>

      <DevCard
        title="API keys & credentials"
        description="Stored in overlay — never echoed in full after save"
        delayMs={120}
      >
        <div className="grid gap-4 lg:grid-cols-2">
          {secretRows.map((row) => (
            <SecretRow
              key={row.field}
              row={row}
              draft={draft[row.field] || ""}
              onDraft={(v) => setDraft((d) => ({ ...d, [row.field]: v }))}
              onRevert={() => revertField(row.field)}
              onClear={() => clearSecret(row.field)}
            />
          ))}
        </div>
      </DevCard>

      <DevCard title="Telephony URLs & numbers" description="Active PSTN provider, webhook base, caller IDs" delayMs={160}>
        <div className="grid gap-4 lg:grid-cols-3">
          {telephonyStrings.map((row) => (
            <StringConfigRow
              key={row.field}
              row={row}
              value={strings[row.field] || ""}
              onChange={(v) => setStrings((s) => ({ ...s, [row.field]: v }))}
              onRevert={() => revertField(row.field)}
            />
          ))}
        </div>
      </DevCard>

      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save environment"}
        </Button>
        <Button type="button" variant="secondary" onClick={() => load()}>Refresh</Button>
        <Button type="button" variant="ghost" onClick={reloadRegistry}>Reload registry</Button>
      </div>

      {status && <p className="text-sm text-text-muted">{status}</p>}

      {saveResult?.applied_keys && saveResult.applied_keys.length > 0 && (
        <p className="text-xs font-mono text-success">
          Applied: {saveResult.applied_keys.join(", ")}
        </p>
      )}
      {saveResult?.rejected && ensureArray(saveResult.rejected).length > 0 && (
        <p className="text-xs text-warning">
          Skipped: {ensureArray<{ field: string; reason: string }>(saveResult.rejected).map((r) => `${r.field} (${r.reason})`).join(", ")}
        </p>
      )}
    </div>
  );
}
