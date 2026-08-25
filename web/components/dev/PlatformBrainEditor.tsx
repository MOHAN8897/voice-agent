"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";

type VersionRow = {
  version_id: string;
  status: string;
  activated_at?: string | null;
  preview?: string;
  char_count?: number;
};

type Scenario = { id: string; label: string; passed: boolean; message: string };

type BudgetInfo = {
  brain_prompt_budget_tokens: number;
  platform_body_chars: number;
  estimated_tokens: number;
  budget_utilization_pct: number;
  prompt_caching_enabled: boolean;
};

export function PlatformBrainEditor() {
  const [body, setBody] = useState("");
  const [activePreview, setActivePreview] = useState("");
  const [activeId, setActiveId] = useState("");
  const [versions, setVersions] = useState<VersionRow[]>([]);
  const [compareId, setCompareId] = useState("");
  const [status, setStatus] = useState("");
  const [issues, setIssues] = useState<{ severity: string; code: string; message: string }[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [budget, setBudget] = useState<BudgetInfo | null>(null);
  const [reason, setReason] = useState("");
  const [rollbackTarget, setRollbackTarget] = useState<string | null>(null);
  const [activateOpen, setActivateOpen] = useState(false);

  const load = useCallback(async () => {
    setStatus("Loading…");
    await refreshPortalSession("dev");
    const [draftR, activeR, versionsR, budgetR] = await Promise.all([
      portalFetch("dev", "/api/platform-brain/draft"),
      portalFetch("dev", "/api/platform-brain"),
      portalFetch("dev", "/api/platform-brain/versions"),
      portalFetch("dev", "/api/platform-brain/budget-cache"),
    ]);
    if (draftR.ok) {
      const j = await draftR.json();
      setBody(j.draft?.body || "");
    } else if (activeR.ok) {
      const j = await activeR.json();
      setBody(j.active?.preview || "");
    }
    if (activeR.ok) {
      const j = await activeR.json();
      setActivePreview(j.active?.preview || "");
      setActiveId(j.active?.version_id || "");
    }
    if (versionsR.ok) {
      const j = await versionsR.json();
      setVersions(j.versions || []);
    }
    if (budgetR.ok) {
      setBudget(await budgetR.json());
    }
    setStatus("");
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function validate() {
    setStatus("Validating…");
    const r = await portalFetch("dev", "/api/platform-brain/validate", {
      method: "POST",
      body: JSON.stringify({ body }),
    });
    const j = await r.json();
    setIssues(j.issues || []);
    setStatus(j.ok ? "Validation passed" : "Validation found issues");
  }

  async function runRegression() {
    setStatus("Running regression scenarios…");
    const r = await portalFetch("dev", "/api/platform-brain/regression-check", {
      method: "POST",
      body: JSON.stringify({ body }),
    });
    const j = await r.json();
    setScenarios(j.scenarios || []);
    setStatus(j.ok ? `Regression passed (${j.passed}/${j.total})` : "Regression scenarios failed");
  }

  async function save() {
    setStatus("Saving draft…");
    const r = await portalFetch("dev", "/api/platform-brain/draft", {
      method: "PUT",
      body: JSON.stringify({ body }),
    });
    setStatus(r.ok ? "Draft saved" : "Save failed");
    if (r.ok) await load();
  }

  async function activate() {
    if (!reason.trim()) {
      setStatus("Add a change reason before activating");
      return;
    }
    setStatus("Activating…");
    const r = await portalFetch("dev", "/api/platform-brain/activate", {
      method: "POST",
      body: JSON.stringify({ body, reason }),
    });
    const j = await r.json();
    if (!r.ok && j.error?.scenarios) {
      setScenarios(j.error.scenarios);
    }
    setStatus(r.ok ? `Activated · compiled ${j.compiled}` : j.error?.message || "Activate failed");
    setActivateOpen(false);
    if (r.ok) await load();
  }

  async function rollback(versionId: string) {
    setStatus("Rolling back…");
    const r = await portalFetch("dev", `/api/platform-brain/${versionId}/rollback`, { method: "POST" });
    const j = await r.json();
    setStatus(r.ok ? `Rolled back to ${j.rolled_back_to}` : "Rollback failed");
    setRollbackTarget(null);
    if (r.ok) await load();
  }

  const compareVersion = versions.find((v) => v.version_id === compareId);

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-3">
        <DevCard
          className="lg:col-span-2"
          title="Platform Brain editor"
          description="Identity, safety, language behavior, memory contract, and output rules."
          delayMs={40}
        >
          <textarea
            className="w-full min-h-[420px] rounded-xl border border-surface-border bg-surface-raised p-4 font-mono text-sm text-text focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            aria-label="Platform brain body"
          />
        </DevCard>

        <div className="space-y-4">
          <DevCard title="Active preview" description={`Active: ${activeId || "—"}`} delayMs={80}>
            <p className="text-sm leading-relaxed text-text-muted whitespace-pre-wrap">{activePreview || "—"}</p>
          </DevCard>

          {budget && (
            <DevCard title="Prompt budget & cache" delayMs={100}>
              <dl className="grid grid-cols-2 gap-2 text-xs text-text-muted">
                <div>
                  <dt>Budget tokens</dt>
                  <dd className="font-mono text-text">{budget.brain_prompt_budget_tokens}</dd>
                </div>
                <div>
                  <dt>Est. platform tokens</dt>
                  <dd className="font-mono text-text">{budget.estimated_tokens}</dd>
                </div>
                <div>
                  <dt>Utilization</dt>
                  <dd className="font-mono text-text">{budget.budget_utilization_pct}%</dd>
                </div>
                <div>
                  <dt>Prompt caching</dt>
                  <dd className="font-mono text-text">{budget.prompt_caching_enabled ? "on" : "off"}</dd>
                </div>
              </dl>
            </DevCard>
          )}

          <DevCard title="Validation & regression" delayMs={120}>
            {issues.length > 0 && (
              <ul className="mb-3 space-y-1 text-sm">
                {issues.map((issue) => (
                  <li key={issue.code} className={issue.severity === "blocking" ? "text-red-400" : "text-warning"}>
                    {issue.message}
                  </li>
                ))}
              </ul>
            )}
            {scenarios.length > 0 && (
              <ul className="mb-3 space-y-1 text-xs">
                {scenarios.map((s) => (
                  <li key={s.id} className={s.passed ? "text-success" : "text-red-400"}>
                    {s.passed ? "✓" : "✗"} {s.label}
                  </li>
                ))}
              </ul>
            )}
            <div className="flex flex-col gap-2">
              <Button type="button" variant="secondary" onClick={validate}>Validate</Button>
              <Button type="button" variant="secondary" onClick={runRegression}>Run regression scenarios</Button>
            </div>
          </DevCard>

          <DevCard title="Activation" delayMs={160}>
            <label className="block text-xs font-medium text-text-muted">Change reason</label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. tighten Telugu output contract"
              className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm"
            />
            <div className="mt-4 flex flex-col gap-2">
              <Button type="button" variant="secondary" onClick={save}>Save draft</Button>
              <Button type="button" onClick={() => setActivateOpen(true)}>Activate</Button>
            </div>
          </DevCard>
        </div>
      </div>

      <DevCard title="Version history & compare" description="Emergency rollback re-activates a prior archived version" delayMs={200}>
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-2">
            {versions.map((v) => (
              <div
                key={v.version_id}
                className="flex items-center justify-between rounded-xl border border-surface-border-subtle px-3 py-2 text-sm"
              >
                <button
                  type="button"
                  className="text-left hover:text-accent"
                  onClick={() => setCompareId(v.version_id)}
                >
                  <span className="font-mono text-xs">{v.version_id}</span>
                  <span className="ml-2 text-text-muted">{v.status}</span>
                </button>
                {v.status !== "active" && v.status !== "draft" && (
                  <Button type="button" variant="ghost" onClick={() => setRollbackTarget(v.version_id)}>
                    Rollback
                  </Button>
                )}
              </div>
            ))}
          </div>
          <div className="rounded-xl border border-surface-border-subtle bg-surface-raised p-4 text-sm text-text-muted">
            <p className="font-medium text-text">Compare</p>
            {compareVersion ? (
              <p className="mt-2 whitespace-pre-wrap">{compareVersion.preview}</p>
            ) : (
              <p className="mt-2">Select a version to compare preview.</p>
            )}
          </div>
        </div>
      </DevCard>

      {status && <p className="text-sm text-text-muted">{status}</p>}

      <ConfirmDialog
        open={activateOpen}
        title="Activate platform brain?"
        description="Regression scenarios must pass. This recompiles the default agent brain and affects all calls."
        confirmLabel="Activate"
        onConfirm={activate}
        onCancel={() => setActivateOpen(false)}
      />
      <ConfirmDialog
        open={rollbackTarget !== null}
        title="Emergency rollback?"
        description={`Re-activate version ${rollbackTarget}. Use when production behavior regressed after activation.`}
        confirmLabel="Rollback"
        variant="secondary"
        onConfirm={() => rollbackTarget && rollback(rollbackTarget)}
        onCancel={() => setRollbackTarget(null)}
      />
    </div>
  );
}
