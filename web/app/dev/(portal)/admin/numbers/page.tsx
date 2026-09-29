"use client";

import { useState } from "react";
import { DevCard } from "@/components/dev/DevCard";
import {
  AdminError,
  AdminLoading,
  AdminPageHeader,
  AdminStat,
} from "@/components/admin/AdminNav";
import {
  SkeuoBadge,
  SkeuoButton,
  SkeuoInput,
  SkeuoTable,
  SkeuoTableBody,
  SkeuoTableHead,
  SkeuoTableRow,
  SkeuoTd,
  SkeuoTh,
} from "@/components/ui/skeuo";
import { adminAction, formatWhen, useAdminResource } from "@/lib/useAdminResource";

type Assignment = {
  e164: string;
  numberId: string;
  tenant: string;
  tenantId: string;
  agent: string | null;
  agentId: string | null;
  purchaseStatus: string | null;
  stripeSubscriptionId: string | null;
  telnyxNumberId: string | null;
  createdAt: string | null;
};

type Tenant = { tenantId: string; name: string };
type Agent = { agent_id?: string; agentId?: string; id?: string; name: string; tenant_id?: string; tenantId?: string };

const PURCHASE_TONE: Record<string, "success" | "warning" | "danger" | "muted"> = {
  active: "success",
  paid: "success",
  failed: "danger",
  refunded: "muted",
  pending: "warning",
};

export default function AdminNumbersPage() {
  const numbers = useAdminResource<{ assignments: Assignment[] }>(
    "/api/dev/admin/phone-assignments"
  );
  const tenants = useAdminResource<{ tenants: Tenant[] }>("/api/dev/admin/tenants");
  const agents = useAdminResource<{ agents: Agent[] }>("/api/agents");

  const [busy, setBusy] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [newNumber, setNewNumber] = useState("");
  const [newTenant, setNewTenant] = useState("");
  const [query, setQuery] = useState("");

  const rows = (numbers.data?.assignments ?? []).filter((a) =>
    query.trim()
      ? `${a.e164} ${a.tenant} ${a.agent ?? ""}`.toLowerCase().includes(query.trim().toLowerCase())
      : true
  );

  async function run(key: string, fn: () => Promise<void>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy("");
    }
  }

  function allocate() {
    return run("allocate", async () => {
      await adminAction("/api/dev/admin/numbers/allocate", {
        method: "POST",
        body: { e164: newNumber.trim(), tenantId: newTenant },
      });
      setNewNumber("");
      await numbers.reload();
    });
  }

  function reassign(a: Assignment, tenantId: string) {
    return run(`reassign:${a.numberId}`, async () => {
      await adminAction(`/api/dev/admin/numbers/${a.numberId}`, {
        method: "PATCH",
        body: { tenantId },
      });
      await numbers.reload();
    });
  }

  function release(a: Assignment) {
    if (
      !window.confirm(
        `Release ${a.e164}? It stops routing immediately. The rental is not refunded automatically.`
      )
    ) {
      return;
    }
    return run(`release:${a.numberId}`, async () => {
      await adminAction(`/api/dev/admin/numbers/${a.numberId}/release`, { method: "POST" });
      await numbers.reload();
    });
  }

  return (
    <div className="space-y-6 p-6">
      <AdminPageHeader
        title="Phone numbers"
        description="Numbers are routed to a tenant, and optionally pinned to one agent so inbound calls reach the right brain."
      />

      <AdminError error={error} />
      <AdminError error={numbers.error} />
      <AdminError error={tenants.error} />

      <div className="grid gap-4 sm:grid-cols-3">
        <AdminStat label="Active numbers" value={numbers.data?.assignments.length ?? "—"} />
        <AdminStat
          label="Provisioned"
          value={(numbers.data?.assignments ?? []).filter((a) => a.telnyxNumberId).length}
          hint="carrier id present"
        />
        <AdminStat
          label="Unassigned to agent"
          value={(numbers.data?.assignments ?? []).filter((a) => !a.agentId).length}
          tone={(numbers.data?.assignments ?? []).some((a) => !a.agentId) ? "warn" : "good"}
          hint="inbound routing not pinned"
        />
      </div>

      <DevCard title="Allocate a number" description="Manually attach an existing number to a tenant.">
        <div className="flex flex-wrap items-end gap-3">
          <SkeuoInput
            placeholder="+14155550123"
            value={newNumber}
            onChange={(e) => setNewNumber(e.target.value)}
            aria-label="Number in E.164"
          />
          <select
            value={newTenant}
            onChange={(e) => setNewTenant(e.target.value)}
            aria-label="Tenant"
            className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
          >
            <option value="">Select tenant…</option>
            {(tenants.data?.tenants ?? []).map((t) => (
              <option key={t.tenantId} value={t.tenantId}>
                {t.name}
              </option>
            ))}
          </select>
          <SkeuoButton
            onClick={allocate}
            disabled={!newNumber.trim() || !newTenant || busy === "allocate"}
          >
            {busy === "allocate" ? "Allocating…" : "Allocate"}
          </SkeuoButton>
        </div>
      </DevCard>

      <DevCard title="Assignments">
        <div className="mb-3">
          <SkeuoInput
            placeholder="Filter by number, tenant, or agent"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Filter numbers"
            className="max-w-sm"
          />
        </div>
        <AdminLoading loading={numbers.loading} />
        <SkeuoTable>
          <SkeuoTableHead>
            <SkeuoTh>Number</SkeuoTh>
            <SkeuoTh>Tenant</SkeuoTh>
            <SkeuoTh>Agent</SkeuoTh>
            <SkeuoTh>Purchase</SkeuoTh>
            <SkeuoTh>Created</SkeuoTh>
            <SkeuoTh className="text-right">Actions</SkeuoTh>
          </SkeuoTableHead>
          <SkeuoTableBody>
            {rows.map((a) => (
              <SkeuoTableRow key={a.numberId}>
                <SkeuoTd className="font-mono">{a.e164}</SkeuoTd>
                <SkeuoTd className="text-sm">{a.tenant}</SkeuoTd>
                <SkeuoTd className="text-sm text-text-muted">
                  {a.agent ?? (
                    <SkeuoBadge tone="warning">not pinned</SkeuoBadge>
                  )}
                </SkeuoTd>
                <SkeuoTd>
                  <SkeuoBadge tone={PURCHASE_TONE[a.purchaseStatus ?? ""] ?? "muted"}>
                    {a.purchaseStatus ?? "manual"}
                  </SkeuoBadge>
                </SkeuoTd>
                <SkeuoTd className="text-xs text-text-muted">{formatWhen(a.createdAt)}</SkeuoTd>
                <SkeuoTd className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    <select
                      defaultValue={a.tenantId}
                      onChange={(e) => e.target.value !== a.tenantId && reassign(a, e.target.value)}
                      disabled={busy === `reassign:${a.numberId}`}
                      aria-label={`Reassign ${a.e164}`}
                      className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-2 py-1 text-xs text-text"
                    >
                      {(tenants.data?.tenants ?? []).map((t) => (
                        <option key={t.tenantId} value={t.tenantId}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                    <SkeuoButton
                      variant="ghost"
                      disabled={busy === `release:${a.numberId}`}
                      onClick={() => release(a)}
                    >
                      Release
                    </SkeuoButton>
                  </div>
                </SkeuoTd>
              </SkeuoTableRow>
            ))}
            {rows.length === 0 && !numbers.loading && (
              <SkeuoTableRow>
                <SkeuoTd className="text-text-muted">
                  No active numbers.
                </SkeuoTd>
              </SkeuoTableRow>
            )}
          </SkeuoTableBody>
        </SkeuoTable>
      </DevCard>
    </div>
  );
}
