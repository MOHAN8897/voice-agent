"use client";

import { useEffect, useState } from "react";
import { SkeuoButton } from "@/components/ui/skeuo";
import {
  DIAL_CODES,
  KYC_LABEL,
  PLANS,
  WORKSPACE_STATUSES,
  downloadCsv,
  fetchAllRows,
  humanize,
  kycTone,
  money,
  runBulk,
  shortDate,
  workspaceTone,
  type Workspace,
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
  selectClass,
  type Column,
} from "./ui";
import { resolveSelection, useAccountList, type Filters } from "./useAccountList";
import { CreateWorkspaceDialog } from "./dialogs";
import type { ViewProps } from "./AccountsWorkspace";

type WsAction = "activate" | "suspend" | "change_plan" | "restore" | "delete";

export function WorkspacesView({ initialFilters, onOpen, onScope, refreshToken, onChanged }: ViewProps) {
  const list = useAccountList<Workspace>("workspaces", initialFilters, "created", "");
  const { filters, setFilter } = list;
  const [moreFilters, setMoreFilters] = useState(Boolean(filters.createdFrom || filters.createdTo || filters.dialCode || filters.balance));
  const [action, setAction] = useState<WsAction | null>(null);
  const [plan, setPlan] = useState("growth");
  const [releaseNumbers, setReleaseNumbers] = useState(true);
  const [revokeSessions, setRevokeSessions] = useState(true);
  const [force, setForce] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  useEffect(() => {
    if (refreshToken) void list.reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshToken]);

  const effective: Record<string, string> = list.effective;

  /** Balance band is a UI shortcut over the server's min/max balance filters. */
  function setBalance(band: string) {
    list.setFilters((prev) => ({
      ...prev,
      balance: band,
      minBalanceUsd: band === "funded" ? "5" : "",
      maxBalanceUsd: band === "zero" ? "0" : band === "low" ? "5" : "",
    }));
  }

  const columns: Column<Workspace>[] = [
    {
      id: "name",
      label: "Workspace",
      sortKey: "name",
      hideable: false,
      render: (w) => (
        <div className="min-w-[180px]">
          <button type="button" onClick={() => onOpen("ws", w.tenantId)} className="text-left font-medium text-text hover:underline">
            {w.name}
          </button>
          <p className="font-mono text-[10px] text-text-subtle">{w.tenantId}</p>
          {w.isInventory && <p className="text-[10px] text-text-muted">Platform inventory pool</p>}
        </div>
      ),
    },
    {
      id: "status",
      label: "Status",
      sortKey: "status",
      render: (w) => (
        <div className="space-y-1">
          <StatusBadge tone={workspaceTone(w.status)}>{humanize(w.status)}</StatusBadge>
          {w.deletedAt && <p className="text-[10px] text-text-muted">deleted {shortDate(w.deletedAt)}</p>}
        </div>
      ),
    },
    { id: "plan", label: "Plan", sortKey: "plan", render: (w) => <span className="text-xs capitalize">{w.plan || "—"}</span> },
    {
      id: "kyc",
      label: "Voice KYC",
      render: (w) => (
        <div className="space-y-0.5">
          <StatusBadge tone={kycTone(w.kyc)}>{KYC_LABEL[w.kyc]}</StatusBadge>
          {w.callsBlocked && <p className="text-[10px] text-status-error">calls blocked</p>}
        </div>
      ),
    },
    {
      id: "members",
      label: "Users",
      sortKey: "members",
      render: (w) => (
        <button type="button" className="font-mono text-xs text-accent-primary hover:underline" onClick={() => onScope("users", w.tenantId)} title="Show this workspace's users">
          {w.memberCount}
        </button>
      ),
    },
    {
      id: "numbers",
      label: "Numbers",
      sortKey: "numbers",
      render: (w) => (
        <button type="button" className="font-mono text-xs text-accent-primary hover:underline" onClick={() => onScope("numbers", w.tenantId)} title="Show this workspace's numbers">
          {w.numberCount}
        </button>
      ),
    },
    { id: "agents", label: "Agents", sortKey: "agents", render: (w) => <span className="font-mono text-xs">{w.agentCount}</span> },
    {
      id: "wallet",
      label: "Wallet",
      sortKey: "balance",
      render: (w) => (
        <span className={`font-mono text-xs ${w.walletBalanceUsd <= 0 ? "text-status-warning" : "text-text"}`}>{money(w.walletBalanceUsd)}</span>
      ),
    },
    { id: "billing", label: "Billing", defaultHidden: true, render: (w) => <span className="text-xs">{humanize(w.billingSource)}</span> },
    { id: "created", label: "Created", sortKey: "created", render: (w) => <span className="text-xs text-text-muted">{shortDate(w.createdAt)}</span> },
  ];

  const labelFor = (id: string) => list.rows.find((r) => r.tenantId === id)?.name ?? id.slice(0, 8);

  async function exportCsv(onlySelected: boolean) {
    setExporting(true);
    setExportError(null);
    try {
      let rows = await fetchAllRows<Workspace>("workspaces", effective);
      if (onlySelected && !list.selection.allMatching) rows = rows.filter((r) => list.selection.ids.has(r.tenantId));
      downloadCsv(
        `workspaces-${new Date().toISOString().slice(0, 10)}.csv`,
        ["Workspace ID", "Name", "Status", "Plan", "Voice KYC", "Users", "Numbers", "Agents", "Wallet USD", "Billing", "Created", "Deleted"],
        rows.map((w) => [w.tenantId, w.name, w.status, w.plan, w.kyc, w.memberCount, w.numberCount, w.agentCount, w.walletBalanceUsd, w.billingSource, w.createdAt, w.deletedAt])
      );
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  const count = list.selectedCount;
  const ACTION_COPY: Record<WsAction, { title: string; label: string; destructive: boolean; description: string }> = {
    activate: {
      title: `Activate ${count} workspace${count === 1 ? "" : "s"}`,
      label: "Activate",
      destructive: false,
      description: "Sets the workspaces to active so members can sign in and calls can run. Deleted workspaces are restored first.",
    },
    suspend: {
      title: `Suspend ${count} workspace${count === 1 ? "" : "s"}`,
      label: "Suspend",
      destructive: true,
      description: "Members are blocked from the console and calls stop. The wallet is kept. You can activate again at any time.",
    },
    change_plan: {
      title: `Change plan for ${count} workspace${count === 1 ? "" : "s"}`,
      label: "Change plan",
      destructive: false,
      description: "Moves the selected workspaces to a new plan. Custom limits on each workspace are kept.",
    },
    restore: {
      title: `Restore ${count} workspace${count === 1 ? "" : "s"}`,
      label: "Restore",
      destructive: false,
      description: "Brings deleted workspaces back as active. Numbers released at deletion are not returned automatically.",
    },
    delete: {
      title: `Delete ${count} workspace${count === 1 ? "" : "s"}`,
      label: "Delete",
      destructive: true,
      description:
        "Archives the workspaces (soft delete): members lose access immediately, data is kept and the workspace can be restored from the Deleted filter. Permanent purge only happens through the customer's own deletion request and its grace period.",
    },
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3 rounded-skeuo-md border border-surface-border-subtle bg-surface-panel p-3">
        <Field label="Search" className="min-w-[220px] flex-1">
          <TextInput value={filters.q ?? ""} onChange={(e) => setFilter("q", e.target.value)} placeholder="Workspace name or ID" aria-label="Search workspaces" />
        </Field>
        <div className="w-36">
          <FilterSelect label="Status" value={filters.status ?? ""} onChange={(v) => setFilter("status", v)} anyLabel="Any status" options={WORKSPACE_STATUSES.map((s) => ({ value: s, label: humanize(s) }))} />
        </div>
        <div className="w-32">
          <FilterSelect label="Plan" value={filters.plan ?? ""} onChange={(v) => setFilter("plan", v)} anyLabel="Any plan" options={PLANS.map((p) => ({ value: p, label: p }))} />
        </div>
        <div className="w-36">
          <FilterSelect
            label="Voice KYC"
            value={filters.kyc ?? ""}
            onChange={(v) => setFilter("kyc", v)}
            options={(Object.keys(KYC_LABEL) as Workspace["kyc"][]).map((k) => ({ value: k, label: KYC_LABEL[k] }))}
          />
        </div>
        <div className="w-36">
          <FilterSelect label="Numbers" value={filters.hasNumbers ?? ""} onChange={(v) => setFilter("hasNumbers", v)} options={[{ value: "true", label: "Has numbers" }, { value: "false", label: "No numbers" }]} />
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
              <FilterSelect label="Country (has a number in)" value={filters.dialCode ?? ""} onChange={(v) => setFilter("dialCode", v)} options={DIAL_CODES.map((d) => ({ value: d.code, label: d.label }))} />
            </div>
            <div className="w-36">
              <FilterSelect
                label="Wallet"
                value={filters.balance ?? ""}
                onChange={setBalance}
                anyLabel="Any balance"
                options={[{ value: "zero", label: "$0 or less" }, { value: "low", label: "Under $5" }, { value: "funded", label: "$5 or more" }]}
              />
            </div>
            <Field label="Created from" className="w-40">
              <TextInput type="date" value={filters.createdFrom ?? ""} onChange={(e) => setFilter("createdFrom", e.target.value)} />
            </Field>
            <Field label="Created to" className="w-40">
              <TextInput type="date" value={filters.createdTo ?? ""} onChange={(e) => setFilter("createdTo", e.target.value)} />
            </Field>
            <label className="flex items-center gap-2 pb-2 text-xs text-text">
              <input type="checkbox" checked={filters.includeDeleted === "true"} onChange={(e) => setFilter("includeDeleted", e.target.checked ? "true" : "")} />
              Include deleted
            </label>
            <label className="flex items-center gap-2 pb-2 text-xs text-text">
              <input type="checkbox" checked={filters.includeInventory === "true"} onChange={(e) => setFilter("includeInventory", e.target.checked ? "true" : "")} />
              Show platform inventory
            </label>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2">
        <SkeuoButton size="sm" variant="secondary" loading={exporting} onClick={() => void exportCsv(false)}>
          Export CSV
        </SkeuoButton>
        <SkeuoButton size="sm" variant="primary" onClick={() => setCreateOpen(true)}>
          + New workspace
        </SkeuoButton>
      </div>
      {exportError && <Notice tone="error">{exportError}</Notice>}

      <SelectionBar count={count} noun={count === 1 ? "workspace" : "workspaces"} onClear={list.clearSelection}>
        <SkeuoButton size="sm" variant="secondary" onClick={() => setAction("activate")}>
          Activate
        </SkeuoButton>
        <SkeuoButton size="sm" variant="secondary" onClick={() => { setReleaseNumbers(false); setRevokeSessions(true); setAction("suspend"); }}>
          Suspend
        </SkeuoButton>
        <SkeuoButton size="sm" variant="secondary" onClick={() => setAction("change_plan")}>
          Change plan
        </SkeuoButton>
        <SkeuoButton size="sm" variant="secondary" onClick={() => setAction("restore")}>
          Restore
        </SkeuoButton>
        <SkeuoButton size="sm" variant="ghost" onClick={() => void exportCsv(true)}>
          Export selected
        </SkeuoButton>
        <SkeuoButton
          size="sm"
          variant="ghost"
          className="text-status-error hover:bg-status-error/10"
          onClick={() => { setReleaseNumbers(true); setRevokeSessions(true); setForce(false); setAction("delete"); }}
        >
          Delete…
        </SkeuoButton>
      </SelectionBar>

      <DataTable
        columns={columns}
        rows={list.rows}
        rowKey={(w) => w.tenantId}
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
        onOpen={(w) => onOpen("ws", w.tenantId)}
        isRowSelectable={(w) => !w.isInventory}
        storageKey="workspaces"
        noun="workspaces"
        empty={
          list.activeFilterCount ? (
            <EmptyState title="No workspaces match these filters" body="Try a broader search, or clear the filters to see every workspace." action={<SkeuoButton size="sm" onClick={list.resetFilters}>Clear filters</SkeuoButton>} />
          ) : (
            <EmptyState title="No workspaces yet" body="Workspaces appear here when customers sign up, or when you create one for them." action={<SkeuoButton size="sm" variant="primary" onClick={() => setCreateOpen(true)}>New workspace</SkeuoButton>} />
          )
        }
      />

      {action && (
        <ActionDialog
          open
          title={ACTION_COPY[action].title}
          description={ACTION_COPY[action].description}
          action={action}
          count={count}
          destructive={ACTION_COPY[action].destructive}
          confirmLabel={ACTION_COPY[action].label}
          labelFor={labelFor}
          onClose={(changed) => {
            setAction(null);
            if (changed) {
              list.clearSelection();
              void list.reload();
              onChanged();
            }
          }}
          onRun={async (reason) => {
            const ids = await resolveSelection("workspaces", list.selection, effective, count);
            return runBulk(
              "workspaces",
              ids,
              { action, reason, plan: action === "change_plan" ? plan : undefined, releaseNumbers, revokeSessions, force },
              ACTION_COPY[action].destructive
            );
          }}
        >
          {action === "change_plan" && (
            <Field label="New plan">
              <select value={plan} onChange={(e) => setPlan(e.target.value)} className={selectClass}>
                {PLANS.filter((p) => p !== "platform").map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </Field>
          )}
          {(action === "suspend" || action === "delete") && (
            <div className="space-y-2 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset p-3 text-xs text-text">
              <label className="flex items-start gap-2">
                <input type="checkbox" checked={revokeSessions} onChange={(e) => setRevokeSessions(e.target.checked)} />
                <span>Sign every member out now (revoke sessions)</span>
              </label>
              <label className="flex items-start gap-2">
                <input type="checkbox" checked={releaseNumbers} onChange={(e) => setReleaseNumbers(e.target.checked)} />
                <span>
                  Release the workspaces&apos; phone numbers
                  <span className="block text-[11px] text-text-muted">
                    Platform numbers return to inventory. Customer-owned Vobiz numbers are unrented at the carrier: a release fee applies and the
                    number cannot be recovered after the cool-off.
                  </span>
                </span>
              </label>
              {action === "delete" && (
                <label className="flex items-start gap-2 text-text-muted">
                  <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
                  <span>Delete even if some numbers could not be released</span>
                </label>
              )}
            </div>
          )}
        </ActionDialog>
      )}

      <CreateWorkspaceDialog
        open={createOpen}
        onClose={(id) => {
          setCreateOpen(false);
          if (id) {
            void list.reload();
            onChanged();
            onOpen("ws", id);
          }
        }}
      />
    </div>
  );
}

export type { Filters };
