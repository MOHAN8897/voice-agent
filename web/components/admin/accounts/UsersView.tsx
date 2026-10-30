"use client";

import { useEffect, useState } from "react";
import { SkeuoButton } from "@/components/ui/skeuo";
import {
  ROLE_LABEL,
  USER_ROLES,
  USER_STATUSES,
  downloadCsv,
  fetchAllRows,
  humanize,
  relativeTime,
  runBulk,
  shortDate,
  userTone,
  type AccountUser,
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
import { InviteUserDialog, RolePicker, WorkspacePicker } from "./dialogs";
import type { ViewProps } from "./AccountsWorkspace";

type UserAction = "activate" | "suspend" | "add_to_workspace" | "set_role" | "remove_from_workspace" | "revoke_sessions" | "delete";

const COPY: Record<UserAction, { verb: string; destructive: boolean; description: string; needsWorkspace?: boolean; needsRole?: boolean }> = {
  activate: { verb: "Activate", destructive: false, description: "Lets these users sign in again." },
  suspend: { verb: "Suspend", destructive: true, description: "Blocks sign-in for these users and signs them out everywhere. Memberships are kept." },
  add_to_workspace: {
    verb: "Add to workspace",
    destructive: false,
    needsWorkspace: true,
    needsRole: true,
    description: "Gives these users access to another workspace. Users who are already members are skipped.",
  },
  set_role: {
    verb: "Change role",
    destructive: false,
    needsWorkspace: true,
    needsRole: true,
    description: "Changes the users' role inside one workspace. The last admin of a workspace cannot be demoted.",
  },
  remove_from_workspace: {
    verb: "Remove from workspace",
    destructive: true,
    needsWorkspace: true,
    description: "Removes access to one workspace. Their account and other memberships stay. The last admin cannot be removed.",
  },
  revoke_sessions: { verb: "Sign out everywhere", destructive: false, description: "Ends every active session; users must sign in again." },
  delete: {
    verb: "Delete",
    destructive: true,
    description: "Disables the accounts, removes all memberships, anonymises the email and signs them out. This cannot be undone from here.",
  },
};

export function UsersView({ scopeTenantId, scopeName, initialFilters, onOpen, refreshToken, onChanged }: ViewProps) {
  const list = useAccountList<AccountUser>("users", initialFilters, "created", scopeTenantId);
  const { filters, setFilter } = list;
  const [moreFilters, setMoreFilters] = useState(Boolean(filters.createdFrom || filters.createdTo || filters.noWorkspace));
  const [action, setAction] = useState<UserAction | null>(null);
  const [tenantId, setTenantId] = useState(scopeTenantId);
  const [role, setRole] = useState("customer_viewer");
  const [inviteOpen, setInviteOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  useEffect(() => {
    if (refreshToken) void list.reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshToken]);

  const columns: Column<AccountUser>[] = [
    {
      id: "email",
      label: "User",
      sortKey: "email",
      hideable: false,
      render: (u) => (
        <div className="min-w-[200px]">
          <button type="button" className="text-left font-medium text-text hover:underline" onClick={() => onOpen("user", u.userId)}>
            {u.email}
          </button>
          {u.fullName && <p className="text-xs text-text-muted">{u.fullName}</p>}
        </div>
      ),
    },
    { id: "status", label: "Status", sortKey: "status", render: (u) => <StatusBadge tone={userTone(u.status)}>{humanize(u.status)}</StatusBadge> },
    {
      id: "workspaces",
      label: scopeTenantId ? "Role here" : "Workspaces & roles",
      render: (u) =>
        u.memberships.length === 0 ? (
          <span className="text-xs text-status-warning">No workspace</span>
        ) : (
          <ul className="space-y-0.5 text-xs">
            {(scopeTenantId ? u.memberships.filter((m) => m.tenantId === scopeTenantId) : u.memberships.slice(0, 3)).map((m) => (
              <li key={m.tenantId} className="flex items-center gap-1.5">
                {!scopeTenantId && (
                  <button type="button" className="max-w-[160px] truncate text-accent-primary hover:underline" onClick={() => onOpen("ws", m.tenantId)}>
                    {m.tenantName}
                  </button>
                )}
                <span className="text-text-muted">{ROLE_LABEL[m.role] ?? m.role}</span>
              </li>
            ))}
            {!scopeTenantId && u.memberships.length > 3 && <li className="text-text-subtle">+{u.memberships.length - 3} more</li>}
          </ul>
        ),
    },
    { id: "lastLogin", label: "Last sign-in", sortKey: "lastLogin", render: (u) => <span className="text-xs text-text-muted">{relativeTime(u.lastLoginAt)}</span> },
    {
      id: "verified",
      label: "Email",
      defaultHidden: true,
      render: (u) => <StatusBadge tone={u.emailVerified ? "success" : "muted"}>{u.emailVerified ? "verified" : "unverified"}</StatusBadge>,
    },
    { id: "created", label: "Joined", sortKey: "created", render: (u) => <span className="text-xs text-text-muted">{shortDate(u.createdAt)}</span> },
    { id: "id", label: "User ID", defaultHidden: true, render: (u) => <span className="font-mono text-[10px] text-text-subtle">{u.userId}</span> },
  ];

  const labelFor = (id: string) => list.rows.find((r) => r.userId === id)?.email ?? id.slice(0, 8);
  const count = list.selectedCount;

  async function exportCsv(onlySelected: boolean) {
    setExporting(true);
    setExportError(null);
    try {
      let rows = await fetchAllRows<AccountUser>("users", list.effective);
      if (onlySelected && !list.selection.allMatching) rows = rows.filter((r) => list.selection.ids.has(r.userId));
      downloadCsv(
        `users-${new Date().toISOString().slice(0, 10)}.csv`,
        ["User ID", "Email", "Name", "Status", "Email verified", "Workspaces (role)", "Last sign-in", "Joined"],
        rows.map((u) => [
          u.userId,
          u.email,
          u.fullName,
          u.status,
          u.emailVerified,
          u.memberships.map((m) => `${m.tenantName} (${m.role})`).join("; "),
          u.lastLoginAt,
          u.createdAt,
        ])
      );
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  function start(a: UserAction) {
    setTenantId(scopeTenantId);
    setRole(a === "add_to_workspace" ? "customer_viewer" : "customer_admin");
    setAction(a);
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3 rounded-skeuo-md border border-surface-border-subtle bg-surface-panel p-3">
        <Field label="Search" className="min-w-[220px] flex-1">
          <TextInput value={filters.q ?? ""} onChange={(e) => setFilter("q", e.target.value)} placeholder="Email, name or user ID" aria-label="Search users" />
        </Field>
        <div className="w-36">
          <FilterSelect label="Status" value={filters.status ?? ""} onChange={(v) => setFilter("status", v)} anyLabel="Any status" options={USER_STATUSES.map((s) => ({ value: s, label: humanize(s) }))} />
        </div>
        <div className="w-40">
          <FilterSelect
            label={scopeTenantId ? "Role in this workspace" : "Role (any workspace)"}
            value={filters.role ?? ""}
            onChange={(v) => setFilter("role", v)}
            anyLabel="Any role"
            options={USER_ROLES.map((r) => ({ value: r, label: ROLE_LABEL[r] ?? r }))}
          />
        </div>
        <div className="w-44">
          <FilterSelect
            label="Last sign-in"
            value={filters.lastActive ?? ""}
            onChange={(v) => setFilter("lastActive", v)}
            anyLabel="Any time"
            options={[
              { value: "7d", label: "In the last 7 days" },
              { value: "30d", label: "In the last 30 days" },
              { value: "inactive30", label: "Not in 30+ days" },
              { value: "inactive90", label: "Not in 90+ days" },
              { value: "never", label: "Never signed in" },
            ]}
          />
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
            <Field label="Joined from" className="w-40">
              <TextInput type="date" value={filters.createdFrom ?? ""} onChange={(e) => setFilter("createdFrom", e.target.value)} />
            </Field>
            <Field label="Joined to" className="w-40">
              <TextInput type="date" value={filters.createdTo ?? ""} onChange={(e) => setFilter("createdTo", e.target.value)} />
            </Field>
            {!scopeTenantId && (
              <label className="flex items-center gap-2 pb-2 text-xs text-text">
                <input type="checkbox" checked={filters.noWorkspace === "true"} onChange={(e) => setFilter("noWorkspace", e.target.checked ? "true" : "")} />
                Only users without a workspace
              </label>
            )}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2">
        <SkeuoButton size="sm" variant="secondary" loading={exporting} onClick={() => void exportCsv(false)}>
          Export CSV
        </SkeuoButton>
        <SkeuoButton size="sm" variant="primary" onClick={() => setInviteOpen(true)}>
          + Invite user
        </SkeuoButton>
      </div>
      {exportError && <Notice tone="error">{exportError}</Notice>}

      <SelectionBar count={count} noun={count === 1 ? "user" : "users"} onClear={list.clearSelection}>
        <SkeuoButton size="sm" variant="secondary" onClick={() => start("activate")}>
          Activate
        </SkeuoButton>
        <SkeuoButton size="sm" variant="secondary" onClick={() => start("suspend")}>
          Suspend
        </SkeuoButton>
        <SkeuoButton size="sm" variant="secondary" onClick={() => start("add_to_workspace")}>
          Add to workspace
        </SkeuoButton>
        <SkeuoButton size="sm" variant="secondary" onClick={() => start("set_role")}>
          Change role
        </SkeuoButton>
        <SkeuoButton size="sm" variant="secondary" onClick={() => start("revoke_sessions")}>
          Sign out everywhere
        </SkeuoButton>
        <SkeuoButton size="sm" variant="ghost" onClick={() => void exportCsv(true)}>
          Export selected
        </SkeuoButton>
        <SkeuoButton size="sm" variant="ghost" className="text-status-error hover:bg-status-error/10" onClick={() => start("remove_from_workspace")}>
          Remove from workspace…
        </SkeuoButton>
        <SkeuoButton size="sm" variant="ghost" className="text-status-error hover:bg-status-error/10" onClick={() => start("delete")}>
          Delete…
        </SkeuoButton>
      </SelectionBar>

      <DataTable
        columns={columns}
        rows={list.rows}
        rowKey={(u) => u.userId}
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
        onOpen={(u) => onOpen("user", u.userId)}
        storageKey={scopeTenantId ? "users-scoped" : "users"}
        noun="users"
        empty={
          list.activeFilterCount ? (
            <EmptyState title="No users match these filters" body="Clear a filter or search for part of an email address." action={<SkeuoButton size="sm" onClick={list.resetFilters}>Clear filters</SkeuoButton>} />
          ) : (
            <EmptyState
              title={scopeTenantId ? `${scopeName ?? "This workspace"} has no members` : "No users yet"}
              body={scopeTenantId ? "Without a member nobody can sign in to this workspace. Invite its first admin." : "Users appear here when they sign up or are invited."}
              action={<SkeuoButton size="sm" variant="primary" onClick={() => setInviteOpen(true)}>Invite user</SkeuoButton>}
            />
          )
        }
      />

      {action && (
        <ActionDialog
          open
          title={`${COPY[action].verb} · ${count} user${count === 1 ? "" : "s"}`}
          description={COPY[action].description}
          action={action}
          count={count}
          destructive={COPY[action].destructive}
          confirmLabel={COPY[action].verb}
          labelFor={labelFor}
          canRun={(!COPY[action].needsWorkspace || Boolean(tenantId)) && (!COPY[action].needsRole || Boolean(role))}
          onClose={(changed) => {
            setAction(null);
            if (changed) {
              list.clearSelection();
              void list.reload();
              onChanged();
            }
          }}
          onRun={async (reason) => {
            const ids = await resolveSelection("users", list.selection, list.effective, count);
            return runBulk(
              "users",
              ids,
              {
                action,
                reason,
                tenantId: COPY[action].needsWorkspace ? tenantId : undefined,
                role: COPY[action].needsRole ? role : undefined,
                revokeSessions: true,
              },
              COPY[action].destructive
            );
          }}
        >
          {COPY[action].needsWorkspace &&
            (scopeTenantId && action !== "add_to_workspace" ? (
              <Notice>Applies to <strong>{scopeName ?? "the selected workspace"}</strong>.</Notice>
            ) : (
              <WorkspacePicker value={tenantId} onChange={(id) => setTenantId(id)} excludeId={action === "add_to_workspace" ? null : undefined} />
            ))}
          {COPY[action].needsRole && <RolePicker value={role} onChange={setRole} />}
          {action === "suspend" && <Notice tone="warning">Your own account is never suspended by a bulk action.</Notice>}
        </ActionDialog>
      )}

      <InviteUserDialog
        open={inviteOpen}
        tenantId={scopeTenantId}
        onClose={(changed) => {
          setInviteOpen(false);
          if (changed) {
            void list.reload();
            onChanged();
          }
        }}
      />
    </div>
  );
}
