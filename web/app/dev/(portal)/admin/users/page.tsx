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
import { useState } from "react";

type UserRow = {
  userId: string;
  email: string;
  status: string;
  fullName?: string;
  role?: string;
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

export default function AdminUsersPage() {
  const users = useAdminResource<{ users: UserRow[] }>("/api/dev/admin/users");
  const tenants = useAdminResource<{ tenants: Array<{ tenantId: string; name: string }> }>(
    "/api/dev/admin/tenants"
  );
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<UserDetail | null>(null);
  const [events, setEvents] = useState<AuthEvent[]>([]);

  const [newEmail, setNewEmail] = useState("");
  const [newName, setNewName] = useState("");
  const [newTenant, setNewTenant] = useState("");
  const [newRole, setNewRole] = useState("customer_admin");
  const [created, setCreated] = useState<{ email: string; tempPassword: string } | null>(null);

  const rows = (users.data?.users ?? []).filter((u) =>
    query.trim()
      ? `${u.email} ${u.fullName ?? ""} ${u.role ?? ""}`.toLowerCase().includes(query.trim().toLowerCase())
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

  return (
    <div className="space-y-6 p-6">
      <AdminPageHeader
        title="Users"
        description="Every account on the platform. Suspending blocks sign-in immediately without deleting history."
      />

      <AdminError error={error} />
      <AdminError error={users.error} />
      <AdminError error={tenants.error} />

      <div className="grid gap-4 sm:grid-cols-3">
        <AdminStat label="Total users" value={users.data?.users.length ?? "—"} />
        <AdminStat
          label="Active"
          value={(users.data?.users ?? []).filter((u) => u.status === "active").length}
        />
        <AdminStat
          label="Suspended"
          value={(users.data?.users ?? []).filter((u) => u.status !== "active").length}
          tone={(users.data?.users ?? []).some((u) => u.status !== "active") ? "warn" : "good"}
        />
      </div>

      <DevCard title="Invite a user" description="Creates the account with a one-time password.">
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
            <option value="">Select tenant…</option>
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
              Created <span className="text-text">{created.email}</span> — temporary password:{" "}
              <code className="rounded bg-surface-panel-raised px-1.5 py-0.5 font-mono text-text">
                {created.tempPassword || "(returned by server)"}
              </code>
              . This is shown once.
            </p>
          )}
        </div>
      </DevCard>

      <DevCard title="All users">
        <div className="mb-3">
          <SkeuoInput
            placeholder="Filter by email, name, or role"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Filter users"
            className="max-w-sm"
          />
        </div>
        <AdminLoading loading={users.loading} />
        <SkeuoTable>
          <SkeuoTableHead>
            <SkeuoTh>Email</SkeuoTh>
            <SkeuoTh>Status</SkeuoTh>
            <SkeuoTh>Role</SkeuoTh>
            <SkeuoTh className="text-right">Actions</SkeuoTh>
          </SkeuoTableHead>
          <SkeuoTableBody>
            {rows.map((u) => (
              <SkeuoTableRow key={u.userId}>
                <SkeuoTd>
                  <button
                    type="button"
                    className="text-left hover:underline"
                    onClick={() => openDetail(u.userId)}
                  >
                    {u.email}
                  </button>
                  {u.fullName && <p className="text-xs text-text-subtle">{u.fullName}</p>}
                </SkeuoTd>
                <SkeuoTd>
                  <SkeuoBadge tone={STATUS_TONE[u.status] ?? "muted"}>{u.status}</SkeuoBadge>
                </SkeuoTd>
                <SkeuoTd className="text-xs text-text-muted">{u.role ?? "—"}</SkeuoTd>
                <SkeuoTd className="text-right">
                  {u.status === "active" ? (
                    <SkeuoButton
                      variant="ghost"
                      onClick={() => setStatus(u, "suspended")}
                      disabled={busy === `status:${u.userId}`}
                    >
                      Suspend
                    </SkeuoButton>
                  ) : (
                    <SkeuoButton
                      variant="ghost"
                      onClick={() => setStatus(u, "active")}
                      disabled={busy === `status:${u.userId}`}
                    >
                      Reactivate
                    </SkeuoButton>
                  )}
                </SkeuoTd>
              </SkeuoTableRow>
            ))}
            {rows.length === 0 && !users.loading && (
              <SkeuoTableRow>
                <SkeuoTd className="text-text-muted">
                  No users match.
                </SkeuoTd>
              </SkeuoTableRow>
            )}
          </SkeuoTableBody>
        </SkeuoTable>
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
              <h4 className="text-sm font-medium text-text">Tenant memberships</h4>
              {detail.memberships.length === 0 ? (
                <p className="mt-1 text-sm text-text-muted">None — this user cannot open a workspace.</p>
              ) : (
                <ul className="mt-1 space-y-1 text-sm text-text-muted">
                  {detail.memberships.map((m) => (
                    <li key={m.tenantId}>
                      <span className="font-mono text-xs">{m.tenantId.slice(0, 8)}</span> — {m.role}
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
