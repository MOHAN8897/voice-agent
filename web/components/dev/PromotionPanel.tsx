"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";

type AuditEntry = {
  id: string;
  actor: string;
  action: string;
  resource_type: string;
  resource_id: string;
  created_at?: string;
};

export function PromotionPanel() {
  const [target, setTarget] = useState<"staging" | "production">("staging");
  const [reason, setReason] = useState("");
  const [status, setStatus] = useState("");
  const [lastPromotionId, setLastPromotionId] = useState("");
  const [promoteOpen, setPromoteOpen] = useState(false);
  const [rollbackOpen, setRollbackOpen] = useState(false);
  const [audit, setAudit] = useState<AuditEntry[]>([]);

  useEffect(() => {
    refreshPortalSession("dev").then(() =>
      portalFetch("dev", "/api/dev/audit-log").then(async (r) => {
        if (r.ok) {
          const j = await r.json();
          setAudit(j.entries || []);
        }
      })
    );
  }, []);

  async function promote() {
    setStatus("Promoting tier assignments…");
    const r = await portalFetch("dev", "/api/dev/promote", {
      method: "POST",
      body: JSON.stringify({ targetEnvironment: target, reason }),
    });
    const j = await r.json();
    setPromoteOpen(false);
    if (r.ok) {
      setLastPromotionId(j.promotion_id || "");
      setStatus(`Promoted ${j.tier_rows_copied} tier rows to ${target}`);
      const a = await portalFetch("dev", "/api/dev/audit-log");
      if (a.ok) setAudit((await a.json()).entries || []);
    } else {
      setStatus("Promotion failed");
    }
  }

  async function rollback() {
    setStatus("Rolling back…");
    const r = await portalFetch("dev", `/api/promotions/${lastPromotionId}/rollback`, { method: "POST" });
    const j = await r.json();
    setRollbackOpen(false);
    setStatus(r.ok ? `Rollback synced ${j.tier_rows_synced} rows from env` : "Rollback failed");
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <DevCard title="Environment promotion" delayMs={40}>
          <div className="space-y-4">
            <div className="flex gap-2">
              {(["staging", "production"] as const).map((env) => (
                <button
                  key={env}
                  type="button"
                  onClick={() => setTarget(env)}
                  className={`rounded-xl px-4 py-2 text-sm capitalize ${
                    target === env
                      ? "bg-accent text-white"
                      : "border border-surface-border text-text-muted hover:border-accent/40"
                  }`}
                >
                  {env}
                </button>
              ))}
            </div>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Promotion reason (required)"
              className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm"
            />
            <Button type="button" onClick={() => (reason.trim() ? setPromoteOpen(true) : setStatus("Add a promotion reason"))}>
              Promote tiers
            </Button>
          </div>
        </DevCard>

        <DevCard title="Rollback" delayMs={80}>
          <p className="text-sm text-text-muted">
            Last promotion ID: <span className="font-mono text-text">{lastPromotionId || "—"}</span>
          </p>
          <Button type="button" variant="secondary" className="mt-4" onClick={() => setRollbackOpen(true)}>
            Rollback from env
          </Button>
        </DevCard>
      </div>

      <DevCard title="Audit log" description="Promotions, rollbacks, and config versions" delayMs={120}>
        <ul className="max-h-80 space-y-2 overflow-y-auto text-sm">
          {audit.length === 0 ? (
            <li className="text-text-muted">No audit entries yet.</li>
          ) : (
            audit.map((e) => (
              <li key={e.id} className="rounded-lg border border-surface-border-subtle px-3 py-2">
                <div className="flex justify-between gap-2">
                  <span className="font-mono text-xs text-accent">{e.action}</span>
                  <span className="text-xs text-text-subtle">{e.created_at?.slice(0, 19) || ""}</span>
                </div>
                <p className="mt-1 text-text-muted">
                  {e.actor} · {e.resource_type}/{e.resource_id}
                </p>
              </li>
            ))
          )}
        </ul>
      </DevCard>

      {status && <p className="text-sm text-text-muted">{status}</p>}

      <ConfirmDialog
        open={promoteOpen}
        title={`Promote to ${target}?`}
        description="This copies tier stack assignments from the current environment to the target. Historical calls are not mutated."
        confirmLabel="Promote"
        onConfirm={promote}
        onCancel={() => setPromoteOpen(false)}
      />
      <ConfirmDialog
        open={rollbackOpen}
        title="Rollback tier assignments?"
        description="Syncs tier cache from current environment variables. Use after a bad promotion."
        confirmLabel="Rollback"
        variant="secondary"
        onConfirm={rollback}
        onCancel={() => setRollbackOpen(false)}
      />
    </div>
  );
}
