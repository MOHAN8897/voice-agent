"use client";

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
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

type UserRow = {
  userId: string;
  email: string;
  status: string;
  fullName?: string;
  role?: string;
  tenantId?: string | null;
  tenantName?: string | null;
  createdAt?: string | null;
};

type UserDetail = {
  user: UserRow;
  memberships: Array<{ tenantId: string; role: string }>;
  lastLoginAt: string | null;
};

type AuthEvent = { eventType: string; createdAt: string; ip: string | null };

const STATUS_TONE: Record<string, "success" | "warning" | "danger" | "muted"> = {
  active: "success",
  invited: "warning",
  pending_invite: "warning",
  suspended: "danger",
  disabled: "danger",
};

const ROLE_TONE: Record<string, "info" | "warning" | "success" | "muted"> = {
  platform_admin: "warning",
  customer_admin: "info",
  voice_engineer: "success",
  customer_viewer: "muted",
};

export function AdminUsersPage() {
  const searchParams = useSearchParams();
  const initialTenant = searchParams.get("tenantId") || "";

  // Search & Filter State
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [roleFilter, setRoleFilter] = useState("all");
  const [selectedTenant, setSelectedTenant] = useState(initialTenant);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  // Sync initial tenant param from URL if it changes
  useEffect(() => {
    if (initialTenant) {
      setSelectedTenant(initialTenant);
    }
  }, [initialTenant]);

  // Reset page when filters change
  useEffect(() => {
    setPage(1);
  }, [searchQuery, statusFilter, roleFilter, selectedTenant, pageSize]);

  const usersUrl = useMemo(() => {
    const params = new URLSearchParams();
    if (selectedTenant.trim()) params.set("tenantId", selectedTenant.trim());
    if (searchQuery.trim()) params.set("q", searchQuery.trim());
    if (statusFilter && statusFilter !== "all") params.set("status", statusFilter);
    if (roleFilter && roleFilter !== "all") params.set("role", roleFilter);
    params.set("limit", String(pageSize));
    params.set("offset", String((page - 1) * pageSize));
    return `/api/dev/admin/users?${params.toString()}`;
  }, [selectedTenant, searchQuery, statusFilter, roleFilter, page, pageSize]);

  const users = useAdminResource<{ users: UserRow[]; total?: number; limit?: number; offset?: number }>(
    usersUrl,
    [usersUrl]
  );
  const tenants = useAdminResource<{ tenants: Array<{ tenantId: string; name: string }> }>(
    "/api/dev/admin/tenants"
  );

  const [busy, setBusy] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<UserDetail | null>(null);
  const [events, setEvents] = useState<AuthEvent[]>([]);

  // Create User Form State
  const [newEmail, setNewEmail] = useState("");
  const [newName, setNewName] = useState("");
  const [newTenant, setNewTenant] = useState("");
  const [newRole, setNewRole] = useState("customer_admin");
  const [created, setCreated] = useState<{ email: string; tempPassword: string } | null>(null);

  const userList = users.data?.users ?? [];
  const totalCount = users.data?.total ?? userList.length;
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  const hasActiveFilters = Boolean(
    searchQuery.trim() ||
      (statusFilter && statusFilter !== "all") ||
      (roleFilter && roleFilter !== "all") ||
      selectedTenant
  );

  function resetAllFilters() {
    setSearchQuery("");
    setStatusFilter("all");
    setRoleFilter("all");
    setSelectedTenant("");
    setPage(1);
  }

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

  async function openDetail(userId: string) {
    await run(`detail:${userId}`, async () => {
      const d = (await adminActionGet(`/api/dev/admin/users/${userId}`)) as UserDetail;
      setDetail(d);
      try {
        const ev = (await adminActionGet(`/api/dev/admin/users/${userId}/auth-events`)) as {
          events: AuthEvent[];
        };
        setEvents(ev.events ?? []);
      } catch {
        setEvents([]);
      }
    });
  }

  function setStatus(u: UserRow, status: string) {
    return run(`status:${u.userId}`, async () => {
      await adminAction(`/api/dev/admin/users/${u.userId}`, { method: "PATCH", body: { status } });
      await users.reload();
      if (detail?.user.userId === u.userId) await openDetail(u.userId);
    });
  }

  function createUser() {
    return run("create", async () => {
      const res = await adminAction<{ email?: string; tempPassword?: string }>(
        "/api/dev/admin/users",
        {
          method: "POST",
          body: {
            email: newEmail.trim(),
            fullName: newName.trim(),
            tenantId: newTenant,
            role: newRole,
          },
        }
      );
      setCreated({ email: res.email ?? newEmail.trim(), tempPassword: res.tempPassword ?? "" });
      setNewEmail("");
      setNewName("");
      await users.reload();
    });
  }

  const activeCount = userList.filter((u) => u.status === "active").length;
  const suspendedCount = userList.filter((u) => u.status !== "active").length;

  return (
    <div className="space-y-6 p-6">
      <AdminPageHeader
        title="Users & Memberships"
        description={
          selectedTenant
            ? `Managing user accounts scoped to workspace ${selectedTenant}.`
            : "Platform accounts, roles, workspace assignments, and security states."
        }
        actions={
          selectedTenant ? (
            <Link href={`/dev/admin/tenants/${selectedTenant}`}>
              <SkeuoButton variant="ghost">Open workspace cockpit</SkeuoButton>
            </Link>
          ) : undefined
        }
      />

      <AdminError error={error} />
      <AdminError error={users.error} />
      <AdminError error={tenants.error} />

      <div className="grid gap-4 sm:grid-cols-4">
        <AdminStat label="Total users" value={totalCount || "—"} />
        <AdminStat label="Active" value={activeCount} tone="good" />
        <AdminStat
          label="Suspended / Inactive"
          value={suspendedCount}
          tone={suspendedCount > 0 ? "warn" : "default"}
        />
        <AdminStat
          label="Workspaces"
          value={tenants.data?.tenants.length ?? "—"}
          hint="tenant accounts"
        />
      </div>

      <DevCard title="Invite user" description="Provisions a user account with assigned role and one-time password.">
        <div className="grid gap-3 md:grid-cols-4">
          <SkeuoInput
            placeholder="email@company.com"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            aria-label="Email"
          />
          <SkeuoInput
            placeholder="Full name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            aria-label="Full name"
          />
          <select
            value={newTenant}
            onChange={(e) => setNewTenant(e.target.value)}
            aria-label="Tenant"
            className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
          >
            <option value="">Select workspace…</option>
            {(tenants.data?.tenants ?? []).map((t) => (
              <option key={t.tenantId} value={t.tenantId}>
                {t.name}
              </option>
            ))}
          </select>
          <select
            value={newRole}
            onChange={(e) => setNewRole(e.target.value)}
            aria-label="Role"
            className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
          >
            <option value="customer_admin">customer_admin</option>
            <option value="customer_viewer">customer_viewer</option>
            <option value="voice_engineer">voice_engineer</option>
            <option value="platform_admin">platform_admin</option>
          </select>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <SkeuoButton
            onClick={createUser}
            disabled={!newEmail.trim() || !newTenant || busy === "create"}
          >
            {busy === "create" ? "Creating…" : "Create user"}
          </SkeuoButton>
          {created && (
            <p className="text-xs text-text-muted">
              Created <span className="text-text font-medium">{created.email}</span> — temporary password:{" "}
              <code className="rounded bg-surface-panel-raised px-1.5 py-0.5 font-mono text-text">
                {created.tempPassword || "(returned by server)"}
              </code>
              . This is shown once.
            </p>
          )}
        </div>
      </DevCard>

      <DevCard title="User directory">
        {/* Comprehensive Search & Filter Controls */}
        <div className="mb-4 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Search user</label>
              <SkeuoInput
                placeholder="Email, name, or UUID…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                aria-label="Search users"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Status</label>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                aria-label="Filter by status"
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
              >
                <option value="all">All statuses</option>
                <option value="active">Active</option>
                <option value="invited">Invited / Pending</option>
                <option value="suspended">Suspended</option>
                <option value="disabled">Disabled</option>
              </select>
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Role</label>
              <select
                value={roleFilter}
                onChange={(e) => setRoleFilter(e.target.value)}
                aria-label="Filter by role"
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
              >
                <option value="all">All roles</option>
                <option value="customer_admin">customer_admin</option>
                <option value="customer_viewer">customer_viewer</option>
                <option value="voice_engineer">voice_engineer</option>
                <option value="platform_admin">platform_admin</option>
              </select>
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-text-muted">Workspace</label>
              <select
                value={selectedTenant}
                onChange={(e) => setSelectedTenant(e.target.value)}
                aria-label="Filter by workspace"
                className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text"
              >
                <option value="">All workspaces</option>
                {(tenants.data?.tenants ?? []).map((t) => (
                  <option key={t.tenantId} value={t.tenantId}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-surface-border-subtle pt-3 text-xs text-text-muted">
            <div className="flex items-center gap-2">
              <span>
                Showing <strong className="text-text">{userList.length}</strong> of{" "}
                <strong className="text-text">{totalCount}</strong> users
              </span>
              {hasActiveFilters && (
                <button
                  type="button"
                  onClick={resetAllFilters}
                  className="rounded px-2 py-0.5 text-accent-primary hover:underline hover:bg-accent-primary/10 transition-colors"
                >
                  Clear filters
                </button>
              )}
            </div>

            <div className="flex items-center gap-2">
              <span className="text-text-muted">Rows per page:</span>
              <select
                value={pageSize}
                onChange={(e) => setPageSize(Number(e.target.value))}
                className="rounded border border-surface-border-subtle bg-surface-panel px-2 py-1 text-xs text-text"
              >
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </div>
          </div>
        </div>

        <AdminLoading loading={users.loading} />
        <SkeuoTable>
          <SkeuoTableHead>
            <SkeuoTh>User</SkeuoTh>
            <SkeuoTh>Status</SkeuoTh>
            <SkeuoTh>Role</SkeuoTh>
            <SkeuoTh>Workspace</SkeuoTh>
            <SkeuoTh>Joined</SkeuoTh>
            <SkeuoTh className="text-right">Actions</SkeuoTh>
          </SkeuoTableHead>
          <SkeuoTableBody>
            {userList.map((u) => (
              <SkeuoTableRow key={u.userId}>
                <SkeuoTd>
                  <button
                    type="button"
                    className="text-left font-medium text-text hover:underline"
                    onClick={() => openDetail(u.userId)}
                  >
                    {u.email}
                  </button>
                  {u.fullName && <p className="text-xs text-text-subtle">{u.fullName}</p>}
                  <p className="font-mono text-[10px] text-text-muted">{u.userId}</p>
                </SkeuoTd>
                <SkeuoTd>
                  <SkeuoBadge tone={STATUS_TONE[u.status] ?? "muted"}>{u.status}</SkeuoBadge>
                </SkeuoTd>
                <SkeuoTd>
                  <SkeuoBadge tone={ROLE_TONE[u.role ?? ""] ?? "muted"}>
                    {u.role ?? "—"}
                  </SkeuoBadge>
                </SkeuoTd>
                <SkeuoTd className="text-xs">
                  {u.tenantId ? (
                    <Link
                      href={`/dev/admin/tenants/${u.tenantId}`}
                      className="font-medium text-accent-primary hover:underline"
                    >
                      {u.tenantName || u.tenantId.slice(0, 8)}
                    </Link>
                  ) : (
                    <span className="text-text-muted">Unassigned</span>
                  )}
                </SkeuoTd>
                <SkeuoTd className="text-xs text-text-muted">{formatWhen(u.createdAt)}</SkeuoTd>
                <SkeuoTd className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    <SkeuoButton
                      variant="ghost"
                      size="sm"
                      onClick={() => openDetail(u.userId)}
                      disabled={busy === `detail:${u.userId}`}
                    >
                      View
                    </SkeuoButton>
                    {u.status === "active" ? (
                      <SkeuoButton
                        variant="ghost"
                        size="sm"
                        onClick={() => setStatus(u, "suspended")}
                        disabled={busy === `status:${u.userId}`}
                      >
                        Suspend
                      </SkeuoButton>
                    ) : (
                      <SkeuoButton
                        variant="ghost"
                        size="sm"
                        onClick={() => setStatus(u, "active")}
                        disabled={busy === `status:${u.userId}`}
                      >
                        Reactivate
                      </SkeuoButton>
                    )}
                  </div>
                </SkeuoTd>
              </SkeuoTableRow>
            ))}
            {userList.length === 0 && !users.loading && (
              <SkeuoTableRow>
                <SkeuoTd className="text-center py-6 text-text-muted" colSpan={6}>
                  No users found matching current filters.
                </SkeuoTd>
              </SkeuoTableRow>
            )}
          </SkeuoTableBody>
        </SkeuoTable>

        {/* Pagination Controls */}
        {totalPages > 1 && (
          <div className="mt-4 flex items-center justify-between border-t border-surface-border-subtle pt-3">
            <span className="text-xs text-text-muted">
              Page {page} of {totalPages}
            </span>
            <div className="flex items-center gap-2">
              <SkeuoButton
                variant="secondary"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
              >
                Previous
              </SkeuoButton>
              <SkeuoButton
                variant="secondary"
                size="sm"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
              >
                Next
              </SkeuoButton>
            </div>
          </div>
        )}
      </DevCard>

      {detail && (
        <DevCard
          title={detail.user.email}
          description={`Last login: ${formatWhen(detail.lastLoginAt)}`}
        >
          <button
            type="button"
            className="absolute right-4 top-4 text-xs text-text-muted hover:text-text"
            onClick={() => {
              setDetail(null);
              setEvents([]);
            }}
          >
            Close
          </button>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <h4 className="text-sm font-medium text-text">Workspace memberships</h4>
              {detail.memberships.length === 0 ? (
                <p className="mt-1 text-sm text-text-muted">None — this user cannot open a workspace.</p>
              ) : (
                <ul className="mt-1 space-y-1 text-sm text-text-muted">
                  {detail.memberships.map((m) => (
                    <li key={m.tenantId}>
                      <Link
                        href={`/dev/admin/tenants/${m.tenantId}`}
                        className="font-mono text-xs underline hover:text-text"
                      >
                        {m.tenantId.slice(0, 8)}…
                      </Link>{" "}
                      — {m.role}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <h4 className="text-sm font-medium text-text">Recent auth events</h4>
              {events.length === 0 ? (
                <p className="mt-1 text-sm text-text-muted">None recorded.</p>
              ) : (
                <ul className="mt-1 space-y-1 text-xs text-text-muted">
                  {events.slice(0, 8).map((e, i) => (
                    <li key={`${e.createdAt}-${i}`}>
                      {e.eventType} · {formatWhen(e.createdAt)} · {e.ip ?? "no ip"}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </DevCard>
      )}
    </div>
  );
}

/** Read-only admin call; `adminAction` is POST-shaped. */
async function adminActionGet(path: string): Promise<unknown> {
  const { devFetch } = await import("@/lib/useAdminResource");
  return devFetch(path);
}
