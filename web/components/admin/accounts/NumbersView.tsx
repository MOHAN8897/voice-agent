"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { SkeuoButton } from "@/components/ui/skeuo";
import {
  DIAL_CODES,
  NUMBER_STATUSES,
  downloadCsv,
  fetchAllRows,
  fetchMatchingIds,
  humanize,
  numberTone,
  runBulk,
  shortDate,
  type AccountNumber,
} from "./model";
import {
  ActionDialog,
  DataTable,
  EmptyState,
  Field,
  FilterSelect,
  Notice,
  SelectionBar,
  StatusBadge,
  TextInput,
  type Column,
} from "./ui";
import { resolveSelection, useAccountList } from "./useAccountList";
import { AddNumberDialog, AgentPicker, CarrierSwitchDialog, WorkspacePicker } from "./dialogs";
import type { ViewProps } from "./AccountsWorkspace";

type NumberAction = "assign_workspace" | "assign_agent" | "unassign_agent" | "release";

const COPY: Record<NumberAction, { verb: string; destructive: boolean; description: string }> = {
  assign_workspace: {
    verb: "Assign to workspace",
    destructive: false,
    description:
      "Inventory numbers go through the normal assignment checks (voice KYC, carrier ownership). Numbers moved from another workspace are unpinned from their old agent. Customer-owned Vobiz numbers cannot be moved between workspaces and will be reported as failed.",
  },
  assign_agent: {
    verb: "Pin to agent",
    destructive: false,
    description: "Incoming calls to these numbers are answered by the chosen agent. Numbers outside the agent's workspace are skipped as failed.",
  },
  unassign_agent: { verb: "Unpin from agent", destructive: false, description: "The numbers stay in their workspace but no agent answers them until pinned again." },
  release: {
    verb: "Release",
    destructive: true,
    description: "Routing stops immediately. Platform numbers return to inventory and become available again. Rental already charged is not refunded.",
  },
};

export function NumbersView({ scopeTenantId, scopeName, initialFilters, onOpen, refreshToken, onChanged }: ViewProps) {
  const list = useAccountList<AccountNumber>("numbers", initialFilters, "created", scopeTenantId);
  const { filters, setFilter } = list;
  const [moreFilters, setMoreFilters] = useState(Boolean(filters.dialCode || filters.purchaseStatus || filters.createdFrom || filters.createdTo || filters.provider));
  const [action, setAction] = useState<NumberAction | null>(null);
  const [tenantId, setTenantId] = useState("");
  const [agentTenant, setAgentTenant] = useState("");
  const [agentId, setAgentId] = useState("");
  const [customerOwned, setCustomerOwned] = useState<number | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [carrierOpen, setCarrierOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const active = list.data?.activeProvider ?? null;

  useEffect(() => {
    if (refreshToken) void list.reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshToken]);

  const count = list.selectedCount;
  const selectedRows = useMemo(() => list.rows.filter((r) => list.selection.allMatching || list.selection.ids.has(r.numberId)), [list.rows, list.selection]);

  const columns: Column<AccountNumber>[] = [
    {
      id: "e164",
      label: "Number",
      sortKey: "e164",
      hideable: false,
      render: (n) => (
        <div>
          <button type="button" className="font-mono font-medium text-text hover:underline" onClick={() => onOpen("num", n.numberId)}>
            {n.e164}
          </button>
          {(n.carrierNumberId || (n.telnyxNumberId && n.telnyxNumberId !== "carrier_platform")) && (
            <p className="text-[10px] text-text-subtle">Line {n.carrierNumberId || n.telnyxNumberId}</p>
          )}
        </div>
      ),
    },
    {
      id: "workspace",
      label: "Workspace",
      sortKey: "workspace",
      render: (n) =>
        n.inInventory ? (
          <StatusBadge tone="info">Platform inventory</StatusBadge>
        ) : n.tenantId ? (
          <div>
            <button type="button" className="text-left text-xs font-medium text-accent-primary hover:underline" onClick={() => onOpen("ws", n.tenantId!)}>
              {n.tenantName}
            </button>
            {n.tenantStatus && n.tenantStatus !== "active" && <p className="text-[10px] text-status-warning">workspace {humanize(n.tenantStatus)}</p>}
          </div>
        ) : (
          <span className="text-xs text-text-muted">—</span>
        ),
    },
    {
      id: "agent",
      label: "Agent",
      sortKey: "agent",
      render: (n) => (n.inInventory ? <span className="text-xs text-text-subtle">—</span> : n.agentName ? <span className="text-xs">{n.agentName}</span> : <StatusBadge tone="warning">not pinned</StatusBadge>),
    },
    { id: "status", label: "Status", sortKey: "status", render: (n) => <StatusBadge tone={numberTone(n.status)}>{humanize(n.status)}</StatusBadge> },
    { id: "provider", label: "Carrier", render: (n) => <StatusBadge tone={n.provider === "vobiz" ? "warning" : "info"}>{n.provider}</StatusBadge> },
    {
      id: "ownership",
      label: "Ownership",
      render: (n) => <span className="text-xs text-text-muted">{n.customerOwned ? "Customer account" : "Platform"}</span>,
    },
    { id: "purchase", label: "Purchase", defaultHidden: true, render: (n) => <span className="text-xs">{n.purchaseStatus ?? "manual"}</span> },
    {
      id: "routing",
      label: "Routing",
      defaultHidden: true,
      render: (n) => (
        <span className="text-xs text-text-muted">
          {n.inboundEnabled ? "in" : "—"} / {n.outboundEnabled ? "out" : "—"}
        </span>
      ),
    },
    { id: "created", label: "Added", sortKey: "created", render: (n) => <span className="text-xs text-text-muted">{shortDate(n.createdAt)}</span> },
  ];

  async function exportCsv(onlySelected: boolean) {
    setExporting(true);
    setExportError(null);
    try {
      let rows = await fetchAllRows<AccountNumber>("numbers", list.effective);
      if (onlySelected && !list.selection.allMatching) rows = rows.filter((r) => list.selection.ids.has(r.numberId));
      downloadCsv(
        `phone-numbers-${new Date().toISOString().slice(0, 10)}.csv`,
        ["Number ID", "E.164", "Status", "Carrier", "Customer-owned", "Workspace", "Workspace ID", "Agent", "Purchase", "Carrier line", "Added"],
        rows.map((n) => [
          n.numberId,
          n.e164,
          n.status,
          n.provider,
          n.customerOwned,
          n.inInventory ? "Platform inventory" : n.tenantName,
          n.tenantId,
          n.agentName,
          n.purchaseStatus ?? "manual",
          n.carrierNumberId || n.telnyxNumberId,
          n.createdAt,
        ])
      );
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  async function start(a: NumberAction) {
    setTenantId("");
    setAgentId("");
    setCustomerOwned(null);
    const tenants = [...new Set(selectedRows.map((r) => r.tenantId).filter(Boolean) as string[])];
    setAgentTenant(scopeTenantId || (tenants.length === 1 ? tenants[0] : ""));
    setAction(a);
    if (a === "release") {
      try {
        const owned = await fetchMatchingIds("numbers", { ...list.effective, ownership: "customer" });
        setCustomerOwned(list.selection.allMatching ? owned.total : owned.ids.filter((id) => list.selection.ids.has(id)).length);
      } catch {
        setCustomerOwned(-1);
      }
    }
  }

  const labelFor = (id: string) => list.rows.find((r) => r.numberId === id)?.e164 ?? id.slice(0, 8);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3 rounded-skeuo-md border border-surface-border-subtle bg-surface-panel p-3">
        <Field label="Search" className="min-w-[220px] flex-1">
          <TextInput value={filters.q ?? ""} onChange={(e) => setFilter("q", e.target.value)} placeholder="Number, workspace, agent or carrier line" aria-label="Search numbers" />
        </Field>
        {!scopeTenantId && (
          <div className="w-40">
            <FilterSelect
              label="Where"
              value={filters.location ?? ""}
              onChange={(v) => setFilter("location", v)}
              anyLabel="Everywhere"
              options={[
                { value: "assigned", label: "In a workspace" },
                { value: "inventory", label: "Platform inventory" },
              ]}
            />
          </div>
        )}
        <div className="w-36">
          <FilterSelect label="Status" value={filters.status ?? ""} onChange={(v) => setFilter("status", v)} anyLabel="Any status" options={NUMBER_STATUSES.map((s) => ({ value: s, label: humanize(s) }))} />
        </div>
        <div className="w-36">
          <FilterSelect label="Agent" value={filters.pinned ?? ""} onChange={(v) => setFilter("pinned", v)} options={[{ value: "true", label: "Pinned to an agent" }, { value: "false", label: "Not pinned" }]} />
        </div>
        <div className="w-40">
          <FilterSelect label="Ownership" value={filters.ownership ?? ""} onChange={(v) => setFilter("ownership", v)} options={[{ value: "platform", label: "Platform" }, { value: "customer", label: "Customer account (Vobiz)" }]} />
        </div>
        <button type="button" className="pb-2 text-xs text-accent-primary hover:underline" onClick={() => setMoreFilters((v) => !v)} aria-expanded={moreFilters}>
          {moreFilters ? "Fewer filters" : "More filters"}
        </button>
        {list.activeFilterCount > 0 && (
          <button type="button" className="pb-2 text-xs text-text-muted underline hover:text-text" onClick={list.resetFilters}>
            Clear filters ({list.activeFilterCount})
          </button>
        )}
        {moreFilters && (
          <div className="flex w-full flex-wrap items-end gap-3 border-t border-surface-border-subtle pt-3">
            <div className="w-44">
              <FilterSelect label="Country" value={filters.dialCode ?? ""} onChange={(v) => setFilter("dialCode", v)} options={DIAL_CODES.map((d) => ({ value: d.code, label: d.label }))} />
            </div>
            <div className="w-32">
              <FilterSelect label="Carrier" value={filters.provider ?? ""} onChange={(v) => setFilter("provider", v)} options={[{ value: "vobiz", label: "Vobiz" }, { value: "telnyx", label: "Telnyx" }]} />
            </div>
            <div className="w-36">
              <FilterSelect
                label="Purchase"
                value={filters.purchaseStatus ?? ""}
                onChange={(v) => setFilter("purchaseStatus", v)}
                options={["manual", "active", "paid", "provisioned", "pending", "failed", "refunded"].map((s) => ({ value: s, label: s }))}
              />
            </div>
            <Field label="Added from" className="w-40">
              <TextInput type="date" value={filters.createdFrom ?? ""} onChange={(e) => setFilter("createdFrom", e.target.value)} />
            </Field>
            <Field label="Added to" className="w-40">
              <TextInput type="date" value={filters.createdTo ?? ""} onChange={(e) => setFilter("createdTo", e.target.value)} />
            </Field>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs text-text-muted">
          {active && (
            <>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-accent-primary/30 bg-accent-primary/10 px-2.5 py-1 font-mono text-[11px] font-semibold text-accent-primary">
                <span className="h-1.5 w-1.5 rounded-full bg-accent-primary" aria-hidden />
                Active carrier: {active.toUpperCase()}
              </span>
              <button type="button" className="underline hover:text-text" onClick={() => setCarrierOpen(true)}>
                Switch
              </button>
              <span aria-hidden>·</span>
              <Link href="/dev/test-studio" className="underline hover:text-text">
                Test a call
              </Link>
            </>
          )}
        </div>
        <div className="flex gap-2">
          <SkeuoButton size="sm" variant="secondary" loading={exporting} onClick={() => void exportCsv(false)}>
            Export CSV
          </SkeuoButton>
          <SkeuoButton size="sm" variant="primary" onClick={() => setAddOpen(true)}>
            + Add number
          </SkeuoButton>
        </div>
      </div>
      {exportError && <Notice tone="error">{exportError}</Notice>}

      <SelectionBar count={count} noun={count === 1 ? "number" : "numbers"} onClear={list.clearSelection}>
        <SkeuoButton size="sm" variant="secondary" onClick={() => void start("assign_workspace")}>
          Assign to workspace
        </SkeuoButton>
        <SkeuoButton size="sm" variant="secondary" onClick={() => void start("assign_agent")}>
          Pin to agent
        </SkeuoButton>
        <SkeuoButton size="sm" variant="secondary" onClick={() => void start("unassign_agent")}>
          Unpin
        </SkeuoButton>
        <SkeuoButton size="sm" variant="ghost" onClick={() => void exportCsv(true)}>
          Export selected
        </SkeuoButton>
        <SkeuoButton size="sm" variant="ghost" className="text-status-error hover:bg-status-error/10" onClick={() => void start("release")}>
          Release…
        </SkeuoButton>
      </SelectionBar>

      <DataTable
        columns={columns}
        rows={list.rows}
        rowKey={(n) => n.numberId}
        loading={list.loading}
        error={list.error}
        total={list.total}
        limit={list.limit}
        offset={list.offset}
        sort={list.sort}
        dir={list.dir}
        onSort={list.toggleSort}
        onPage={list.setOffset}
        onLimit={list.setLimit}
        selection={list.selection}
        onSelection={list.setSelection}
        onOpen={(n) => onOpen("num", n.numberId)}
        storageKey="numbers"
        noun="numbers"
        empty={
          list.activeFilterCount ? (
            <EmptyState title="No numbers match these filters" body="Clear a filter, or search by part of the number." action={<SkeuoButton size="sm" onClick={list.resetFilters}>Clear filters</SkeuoButton>} />
          ) : (
            <EmptyState
              title={scopeTenantId ? `${scopeName ?? "This workspace"} has no phone numbers` : "No phone numbers yet"}
              body="Assign one from the platform pool or order one from the active carrier."
              action={<SkeuoButton size="sm" variant="primary" onClick={() => setAddOpen(true)}>Add number</SkeuoButton>}
            />
          )
        }
      />

      {action && (
        <ActionDialog
          open
          title={`${COPY[action].verb} · ${count} number${count === 1 ? "" : "s"}`}
          description={COPY[action].description}
          action={action}
          count={count}
          destructive={COPY[action].destructive}
          confirmLabel={COPY[action].verb}
          labelFor={labelFor}
          canRun={(action !== "assign_workspace" || Boolean(tenantId)) && (action !== "assign_agent" || Boolean(agentId))}
          onClose={(changed) => {
            setAction(null);
            if (changed) {
              list.clearSelection();
              void list.reload();
              onChanged();
            }
          }}
          onRun={async (reason) => {
            const ids = await resolveSelection("numbers", list.selection, list.effective, count);
            return runBulk(
              "numbers",
              ids,
              { action, reason, tenantId: action === "assign_workspace" ? tenantId : undefined, agentId: action === "assign_agent" ? agentId : undefined },
              COPY[action].destructive
            );
          }}
        >
          {action === "assign_workspace" && <WorkspacePicker value={tenantId} onChange={(id) => setTenantId(id)} label="Target workspace" hint="Only active workspaces can receive numbers." />}
          {action === "assign_agent" && (
            <>
              {scopeTenantId ? null : <WorkspacePicker value={agentTenant} onChange={(id) => { setAgentTenant(id); setAgentId(""); }} label="Agent's workspace" />}
              <AgentPicker tenantId={agentTenant} value={agentId} onChange={setAgentId} />
            </>
          )}
          {action === "release" && (
            <Notice tone={customerOwned ? "warning" : "info"}>
              {customerOwned === null
                ? "Checking for customer-owned numbers…"
                : customerOwned === -1
                  ? "Could not check ownership. Customer-owned Vobiz numbers in the selection will be unrented at the carrier."
                  : customerOwned > 0
                    ? `${customerOwned} of these ${customerOwned === 1 ? "is a" : "are"} customer-owned Vobiz number${customerOwned === 1 ? "" : "s"}: releasing unrents ${customerOwned === 1 ? "it" : "them"} at the carrier, a release fee is charged, and after the 24-hour cool-off ${customerOwned === 1 ? "it" : "they"} cannot be recovered.`
                    : "All selected numbers are platform numbers; they go back to inventory with no carrier fee."}
            </Notice>
          )}
        </ActionDialog>
      )}

      <AddNumberDialog
        open={addOpen}
        tenantId={scopeTenantId}
        onClose={(changed) => {
          setAddOpen(false);
          if (changed) {
            void list.reload();
            onChanged();
          }
        }}
      />
      <CarrierSwitchDialog
        open={carrierOpen}
        active={active ?? "vobiz"}
        onClose={(changed) => {
          setCarrierOpen(false);
          if (changed) void list.reload();
        }}
      />
    </div>
  );
}
