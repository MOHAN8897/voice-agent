"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { SkeuoButton } from "@/components/ui/skeuo";
import { adminAction, formatWhen, useAdminResource } from "@/lib/useAdminResource";
import {
  EDITABLE_WORKSPACE_STATUSES,
  KYC_LABEL,
  PLANS,
  ROLE_LABEL,
  humanize,
  kycTone,
  money,
  numberTone,
  relativeTime,
  runBulk,
  shortDate,
  userTone,
  workspaceTone,
  type AccountNumber,
  type AccountUser,
  type AccountsTab,
  type BulkResult,
  type ListPage,
  type Workspace,
} from "./model";
import { ActionDialog, Drawer, DrawerSection, Field, KeyValues, Modal, Notice, StatusBadge, selectClass } from "./ui";
import { AddNumberDialog, AgentPicker, ImpersonateDialog, InviteUserDialog, RolePicker, WalletDialog, WorkspacePicker } from "./dialogs";

type OpenFn = (kind: "ws" | "user" | "num", id: string) => void;

type DrawerProps = {
  id: string;
  onClose: () => void;
  onOpen: OpenFn;
  onScope: (tab: AccountsTab, tenantId: string) => void;
  onChanged: () => void;
};

/** Throw if a single-item bulk call failed, so the dialog shows the reason. */
function single(res: BulkResult): BulkResult | void {
  if (res.failed.length) throw new Error(res.failed[0].error);
  if (res.skipped.length) throw new Error(`Nothing to do: ${res.skipped[0].reason}.`);
}

/* =================================================================== workspace */

type TenantDetail = {
  tenant: { tenantId: string; name: string; status: string; plan?: string | null; billingSource?: string | null; createdAt?: string | null };
  wallet?: { balanceUsd?: number; balanceInr?: number } | null;
  voiceKyc?: {
    status?: string;
    approved?: boolean;
    callsBlocked?: boolean;
    legalName?: string | null;
    businessType?: string | null;
    verifications?: Record<string, string>;
  } | null;
  counts?: { agents?: number; numbers?: number; members?: number; calls?: number };
  agents: Array<{ agentId?: string; name: string; status?: string }>;
  numbers: Array<{ id?: string; e164: string; agentId?: string | null; status?: string }>;
  users?: Array<{ userId: string; email?: string; role: string; fullName?: string }>;
  recentCalls?: Array<{ callId: string; startedAt?: string | null; status?: string | null }>;
};

type Channels = { channels?: { cap: number; included: number; paid: number; activeNow: number } };

type WsPending =
  | { kind: "status"; status: string }
  | { kind: "plan" }
  | { kind: "delete" }
  | { kind: "restore" }
  | null;

export function WorkspaceDrawer({ id, onClose, onOpen, onScope, onChanged }: DrawerProps) {
  const row = useAdminResource<ListPage<Workspace>>(
    `/api/dev/admin/accounts/workspaces?q=${encodeURIComponent(id)}&includeDeleted=true&includeInventory=true&limit=1`,
    [id]
  );
  const ws = row.data?.items.find((w) => w.tenantId === id) ?? null;
  const deleted = Boolean(ws?.deletedAt) || ws?.status === "deleted";
  const detail = useAdminResource<TenantDetail>(ws && !deleted ? `/api/dev/admin/tenants/${id}` : null, [id, ws?.status]);
  const channels = useAdminResource<Channels>(ws && !deleted ? `/api/dev/admin/tenants/${id}/channels` : null, [id]);
  const [pending, setPending] = useState<WsPending>(null);
  const [plan, setPlan] = useState("growth");
  const [releaseNumbers, setReleaseNumbers] = useState(false);
  const [revokeSessions, setRevokeSessions] = useState(true);
  const [walletOpen, setWalletOpen] = useState(false);
  const [impersonateOpen, setImpersonateOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [addNumberOpen, setAddNumberOpen] = useState(false);

  async function refresh() {
    await Promise.all([row.reload(), detail.reload()]);
    onChanged();
  }

  const d = detail.data;
  const agentName = (agentId?: string | null) => d?.agents.find((a) => a.agentId === agentId)?.name;
  const statusChoices = EDITABLE_WORKSPACE_STATUSES.filter((s) => s !== ws?.status);

  return (
    <Drawer
      open
      onClose={onClose}
      title={ws?.name ?? (row.loading ? "Loading…" : "Workspace")}
      subtitle={<span className="font-mono">{id}</span>}
      badges={
        ws && (
          <>
            <StatusBadge tone={workspaceTone(ws.status)}>{humanize(ws.status)}</StatusBadge>
            <StatusBadge tone="muted">{ws.plan || "no plan"}</StatusBadge>
            <StatusBadge tone={kycTone(ws.kyc)}>{KYC_LABEL[ws.kyc]}</StatusBadge>
            {ws.isInventory && <StatusBadge tone="info">Platform inventory</StatusBadge>}
          </>
        )
      }
      footer={
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Link href={`/dev/admin/tenants/${id}`} className="text-xs text-accent-primary underline">
            Open full workspace page (limits, ledger, usage, audit)
          </Link>
          <Link href={`/dev/admin/activity?tenantId=${id}`} className="text-xs text-text-muted underline hover:text-text">
            Activity log
          </Link>
        </div>
      }
    >
      {row.error && <Notice tone="error">{row.error}</Notice>}
      {!row.loading && !ws && !row.error && <Notice tone="warning">This workspace no longer exists.</Notice>}
      {ws && (
        <>
          <div className="flex flex-wrap gap-2">
            {deleted ? (
              <SkeuoButton size="sm" variant="primary" onClick={() => setPending({ kind: "restore" })}>
                Restore workspace
              </SkeuoButton>
            ) : (
              <>
                <SkeuoButton size="sm" variant="primary" disabled={!ws.memberCount} title={ws.memberCount ? undefined : "No members to sign in as"} onClick={() => setImpersonateOpen(true)}>
                  Open as customer
                </SkeuoButton>
                <SkeuoButton size="sm" variant="secondary" onClick={() => setWalletOpen(true)}>
                  Adjust wallet
                </SkeuoButton>
                <SkeuoButton size="sm" variant="secondary" onClick={() => { setPlan(ws.plan && ws.plan !== "platform" ? ws.plan : "growth"); setPending({ kind: "plan" }); }}>
                  Change plan
                </SkeuoButton>
                <select
                  aria-label="Change status"
                  className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-2 py-1 text-xs text-text"
                  value=""
                  onChange={(e) => {
                    const s = e.target.value;
                    if (!s) return;
                    setReleaseNumbers(false);
                    setRevokeSessions(s === "suspended" || s === "cancelled");
                    setPending({ kind: "status", status: s });
                  }}
                >
                  <option value="">Change status…</option>
                  {statusChoices.map((s) => (
                    <option key={s} value={s}>
                      Set {humanize(s)}
                    </option>
                  ))}
                </select>
                <SkeuoButton size="sm" variant="ghost" className="text-status-error hover:bg-status-error/10" onClick={() => { setReleaseNumbers(true); setRevokeSessions(true); setPending({ kind: "delete" }); }}>
                  Delete…
                </SkeuoButton>
              </>
            )}
          </div>

          <KeyValues
            items={[
              ["Wallet", <span key="w" className="font-mono">{money(ws.walletBalanceUsd)}{ws.walletBalanceInr ? ` · ₹${ws.walletBalanceInr.toFixed(2)}` : ""}</span>],
              ["Billing", humanize(ws.billingSource)],
              ["Created", shortDate(ws.createdAt)],
              ["Lifetime calls", d?.counts?.calls ?? "—"],
              [
                "Channels",
                channels.data?.channels
                  ? `${channels.data.channels.activeNow} live / ${channels.data.channels.cap} cap (${channels.data.channels.paid} paid)`
                  : channels.error
                    ? "—"
                    : "…",
              ],
              ["Deleted", ws.deletedAt ? shortDate(ws.deletedAt) : "—"],
            ]}
          />
          {deleted && (
            <Notice tone="warning">
              Deleted {formatWhen(ws.deletedAt ?? null)}. Members cannot sign in. Restoring makes it active again; numbers released at deletion stay in
              inventory.
            </Notice>
          )}
          {detail.error && !deleted && <Notice tone="error">{detail.error}</Notice>}

          {!deleted && (
            <DrawerSection title="Voice KYC" hint="Carrier verification required before numbers can call.">
              {d?.voiceKyc ? (
                <div className="space-y-2 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel p-3 text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge tone={d.voiceKyc.approved ? "success" : d.voiceKyc.status === "failed" ? "error" : "warning"}>
                      {humanize(d.voiceKyc.status || "not_started")}
                    </StatusBadge>
                    {d.voiceKyc.callsBlocked ? <span className="text-status-error">Calls blocked until approved</span> : <span className="text-status-success">Calls allowed</span>}
                  </div>
                  <p className="text-text-muted">
                    {d.voiceKyc.legalName || "No legal name yet"} · {humanize(d.voiceKyc.businessType)}
                  </p>
                  {d.voiceKyc.verifications && Object.keys(d.voiceKyc.verifications).length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(d.voiceKyc.verifications).map(([doc, st]) => (
                        <span key={doc} className="rounded border border-surface-border-subtle px-1.5 py-0.5 font-mono text-[10px] uppercase">
                          {doc}: {st}
                        </span>
                      ))}
                    </div>
                  )}
                  <Link href="/dev/admin/verification" className="text-accent-primary underline">
                    Open verification queue
                  </Link>
                </div>
              ) : (
                <p className="text-xs text-text-muted">{detail.loading ? "Loading…" : "Not started. It begins when the customer starts verification or buys a number."}</p>
              )}
            </DrawerSection>
          )}

          <DrawerSection
            title={`Users (${ws.memberCount})`}
            action={
              <div className="flex gap-2 text-xs">
                {!deleted && (
                  <button type="button" className="text-accent-primary underline" onClick={() => setInviteOpen(true)}>
                    Invite
                  </button>
                )}
                <button type="button" className="text-accent-primary underline" onClick={() => onScope("users", id)}>
                  Manage all
                </button>
              </div>
            }
          >
            {(d?.users ?? []).length ? (
              <ul className="divide-y divide-surface-border-subtle rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel">
                {(d?.users ?? []).slice(0, 8).map((u) => (
                  <li key={u.userId}>
                    <button type="button" className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs hover:bg-surface-panel-raised" onClick={() => onOpen("user", u.userId)}>
                      <span className="truncate text-text">{u.email || u.userId}</span>
                      <span className="shrink-0 text-text-muted">{ROLE_LABEL[u.role] ?? u.role}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-text-muted">{detail.loading ? "Loading…" : "No members — nobody can sign in to this workspace."}</p>
            )}
          </DrawerSection>

          <DrawerSection
            title={`Phone numbers (${ws.numberCount})`}
            action={
              <div className="flex gap-2 text-xs">
                {!deleted && (
                  <button type="button" className="text-accent-primary underline" onClick={() => setAddNumberOpen(true)}>
                    Add number
                  </button>
                )}
                <button type="button" className="text-accent-primary underline" onClick={() => onScope("numbers", id)}>
                  Manage all
                </button>
              </div>
            }
          >
            {(d?.numbers ?? []).length ? (
              <ul className="divide-y divide-surface-border-subtle rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel">
                {(d?.numbers ?? []).slice(0, 8).map((n) => (
                  <li key={n.id || n.e164}>
                    <button
                      type="button"
                      disabled={!n.id}
                      className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs hover:bg-surface-panel-raised"
                      onClick={() => n.id && onOpen("num", n.id)}
                    >
                      <span className="font-mono text-text">{n.e164}</span>
                      <span className="flex items-center gap-2 text-text-muted">
                        {agentName(n.agentId) ?? <span className="text-status-warning">not pinned</span>}
                        <StatusBadge tone={numberTone(n.status ?? "")}>{humanize(n.status)}</StatusBadge>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-text-muted">{detail.loading ? "Loading…" : "No numbers assigned."}</p>
            )}
          </DrawerSection>

          {!deleted && (
            <DrawerSection title={`Agents (${ws.agentCount})`}>
              {(d?.agents ?? []).length ? (
                <ul className="flex flex-wrap gap-1.5">
                  {(d?.agents ?? []).map((a) => (
                    <li key={a.agentId} className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel px-2 py-1 text-xs text-text">
                      {a.name}
                      {a.status && a.status !== "active" ? <span className="ml-1 text-text-muted">· {a.status}</span> : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-text-muted">{detail.loading ? "Loading…" : "No agents yet."}</p>
              )}
            </DrawerSection>
          )}
        </>
      )}

      {pending?.kind === "status" && ws && (
        <ActionDialog
          open
          title={`Set ${ws.name} to ${humanize(pending.status)}`}
          description={
            pending.status === "suspended" || pending.status === "cancelled"
              ? "Members lose console access and calls stop. The wallet is kept."
              : "Changes the workspace lifecycle status."
          }
          action={pending.status}
          count={1}
          destructive={pending.status === "suspended" || pending.status === "cancelled"}
          confirmLabel={`Set ${humanize(pending.status)}`}
          onClose={(changed) => {
            setPending(null);
            if (changed) void refresh();
          }}
          onRun={async (reason) => {
            await adminAction(`/api/dev/admin/tenants/${id}`, {
              method: "PATCH",
              body: { status: pending.status, note: reason, releaseNumbers, revokeSessions },
            });
          }}
        >
          {(pending.status === "suspended" || pending.status === "cancelled") && (
            <ReleaseRevokeOptions release={releaseNumbers} setRelease={setReleaseNumbers} revoke={revokeSessions} setRevoke={setRevokeSessions} />
          )}
        </ActionDialog>
      )}
      {pending?.kind === "plan" && ws && (
        <ActionDialog
          open
          title={`Change plan for ${ws.name}`}
          description="Edit custom limits and features on the full workspace page."
          action="change_plan"
          count={1}
          confirmLabel="Change plan"
          onClose={(changed) => {
            setPending(null);
            if (changed) void refresh();
          }}
          onRun={async (reason) => single(await runBulk("workspaces", [id], { action: "change_plan", plan, reason }))}
        >
          <Field label="Plan">
            <select value={plan} onChange={(e) => setPlan(e.target.value)} className={selectClass}>
              {PLANS.filter((p) => p !== "platform").map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </Field>
        </ActionDialog>
      )}
      {(pending?.kind === "delete" || pending?.kind === "restore") && ws && (
        <ActionDialog
          open
          title={pending.kind === "delete" ? `Delete ${ws.name}` : `Restore ${ws.name}`}
          description={
            pending.kind === "delete"
              ? "Archives the workspace (soft delete). Members lose access now; it can be restored later from the Deleted filter."
              : "Brings the workspace back as active."
          }
          action={pending.kind}
          count={1}
          destructive={pending.kind === "delete"}
          confirmLabel={pending.kind === "delete" ? "Delete workspace" : "Restore"}
          onClose={(changed) => {
            setPending(null);
            if (changed) void refresh();
          }}
          onRun={async (reason) =>
            single(await runBulk("workspaces", [id], { action: pending.kind, reason, releaseNumbers, revokeSessions, force: false }, pending.kind === "delete"))
          }
        >
          {pending.kind === "delete" && (
            <ReleaseRevokeOptions release={releaseNumbers} setRelease={setReleaseNumbers} revoke={revokeSessions} setRevoke={setRevokeSessions} />
          )}
        </ActionDialog>
      )}

      <WalletDialog open={walletOpen} workspace={ws} onClose={(changed) => { setWalletOpen(false); if (changed) void refresh(); }} />
      <ImpersonateDialog open={impersonateOpen} workspace={ws} onClose={() => setImpersonateOpen(false)} />
      <InviteUserDialog open={inviteOpen} tenantId={id} onClose={(changed) => { setInviteOpen(false); if (changed) void refresh(); }} />
      <AddNumberDialog open={addNumberOpen} tenantId={id} onClose={(changed) => { setAddNumberOpen(false); if (changed) void refresh(); }} />
    </Drawer>
  );
}

function ReleaseRevokeOptions({
  release,
  setRelease,
  revoke,
  setRevoke,
}: {
  release: boolean;
  setRelease: (v: boolean) => void;
  revoke: boolean;
  setRevoke: (v: boolean) => void;
}) {
  return (
    <div className="space-y-2 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset p-3 text-xs text-text">
      <label className="flex items-start gap-2">
        <input type="checkbox" checked={revoke} onChange={(e) => setRevoke(e.target.checked)} />
        Sign every member out now
      </label>
      <label className="flex items-start gap-2">
        <input type="checkbox" checked={release} onChange={(e) => setRelease(e.target.checked)} />
        <span>
          Release its phone numbers
          <span className="block text-[11px] text-text-muted">Customer-owned Vobiz numbers incur a carrier release fee and cannot be recovered after the cool-off.</span>
        </span>
      </label>
    </div>
  );
}

/* =================================================================== user */

type UserPending =
  | { kind: "activate" | "suspend" | "revoke_sessions" | "delete" }
  | { kind: "set_role"; tenantId: string; tenantName: string; role: string }
  | { kind: "remove_from_workspace"; tenantId: string; tenantName: string }
  | { kind: "add_to_workspace" }
  | null;

export function UserDrawer({ id, onClose, onOpen, onChanged }: DrawerProps) {
  const row = useAdminResource<ListPage<AccountUser>>(`/api/dev/admin/accounts/users?q=${encodeURIComponent(id)}&includeDeleted=true&limit=1`, [id]);
  const events = useAdminResource<{ events: Array<{ eventType: string; createdAt: string; ip: string | null }> }>(`/api/dev/admin/users/${id}/auth-events`, [id]);
  const user = row.data?.items.find((u) => u.userId === id) ?? null;
  const [pending, setPending] = useState<UserPending>(null);
  const [tenantId, setTenantId] = useState("");
  const [role, setRole] = useState("customer_viewer");
  const [resetOpen, setResetOpen] = useState(false);

  async function refresh() {
    await Promise.all([row.reload(), events.reload()]);
    onChanged();
  }

  const deleted = Boolean(user?.deletedAt);

  return (
    <Drawer
      open
      onClose={onClose}
      title={user?.email ?? (row.loading ? "Loading…" : "User")}
      subtitle={user?.fullName || <span className="font-mono">{id}</span>}
      badges={
        user && (
          <>
            <StatusBadge tone={userTone(user.status)}>{humanize(user.status)}</StatusBadge>
            <StatusBadge tone={user.emailVerified ? "success" : "muted"}>{user.emailVerified ? "email verified" : "email unverified"}</StatusBadge>
          </>
        )
      }
    >
      {row.error && <Notice tone="error">{row.error}</Notice>}
      {!row.loading && !user && !row.error && <Notice tone="warning">This user no longer exists.</Notice>}
      {user && (
        <>
          {!deleted && (
            <div className="flex flex-wrap gap-2">
              {user.status === "active" ? (
                <SkeuoButton size="sm" variant="secondary" onClick={() => setPending({ kind: "suspend" })}>
                  Suspend
                </SkeuoButton>
              ) : (
                <SkeuoButton size="sm" variant="primary" onClick={() => setPending({ kind: "activate" })}>
                  Activate
                </SkeuoButton>
              )}
              <SkeuoButton size="sm" variant="secondary" onClick={() => setResetOpen(true)}>
                Reset password
              </SkeuoButton>
              <SkeuoButton size="sm" variant="secondary" onClick={() => setPending({ kind: "revoke_sessions" })}>
                Sign out everywhere
              </SkeuoButton>
              <SkeuoButton size="sm" variant="ghost" className="text-status-error hover:bg-status-error/10" onClick={() => setPending({ kind: "delete" })}>
                Delete…
              </SkeuoButton>
            </div>
          )}

          <KeyValues
            items={[
              ["Last sign-in", relativeTime(user.lastLoginAt)],
              ["Joined", shortDate(user.createdAt)],
              ["User ID", <span key="id" className="font-mono text-[10px]">{user.userId}</span>],
              ["Workspaces", user.memberships.length],
            ]}
          />
          {deleted && <Notice tone="warning">This account was deleted {formatWhen(user.deletedAt ?? null)}.</Notice>}

          <DrawerSection
            title="Workspaces & roles"
            hint="Each membership has its own role."
            action={
              !deleted && (
                <button type="button" className="text-xs text-accent-primary underline" onClick={() => { setTenantId(""); setRole("customer_viewer"); setPending({ kind: "add_to_workspace" }); }}>
                  Add to workspace
                </button>
              )
            }
          >
            {user.memberships.length ? (
              <ul className="divide-y divide-surface-border-subtle rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel">
                {user.memberships.map((m) => (
                  <li key={m.tenantId} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-xs">
                    <button type="button" className="truncate text-left font-medium text-accent-primary hover:underline" onClick={() => onOpen("ws", m.tenantId)}>
                      {m.tenantName}
                    </button>
                    <div className="flex items-center gap-2">
                      <select
                        aria-label={`Role in ${m.tenantName}`}
                        value={m.role}
                        disabled={deleted}
                        onChange={(e) => setPending({ kind: "set_role", tenantId: m.tenantId, tenantName: m.tenantName, role: e.target.value })}
                        className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-1.5 py-1 text-xs text-text"
                      >
                        {[m.role, ...["customer_admin", "voice_engineer", "customer_viewer", "platform_admin"].filter((r) => r !== m.role)].map((r) => (
                          <option key={r} value={r}>
                            {ROLE_LABEL[r] ?? r}
                          </option>
                        ))}
                      </select>
                      {!deleted && (
                        <button
                          type="button"
                          className="text-status-error hover:underline"
                          onClick={() => setPending({ kind: "remove_from_workspace", tenantId: m.tenantId, tenantName: m.tenantName })}
                        >
                          Remove
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-status-warning">No workspace — this user cannot open the console.</p>
            )}
          </DrawerSection>

          <DrawerSection title="Recent sign-in activity">
            {(events.data?.events ?? []).length ? (
              <ul className="space-y-1 text-xs text-text-muted">
                {(events.data?.events ?? []).slice(0, 10).map((e, i) => (
                  <li key={`${e.createdAt}-${i}`} className="flex justify-between gap-2">
                    <span className="text-text">{humanize(e.eventType)}</span>
                    <span>
                      {formatWhen(e.createdAt)} · {e.ip ?? "no IP"}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-text-muted">{events.loading ? "Loading…" : "No sign-in events recorded."}</p>
            )}
          </DrawerSection>
        </>
      )}

      {pending && user && (
        <ActionDialog
          open
          title={
            pending.kind === "set_role"
              ? `Make ${user.email} ${ROLE_LABEL[pending.role] ?? pending.role} in ${pending.tenantName}`
              : pending.kind === "remove_from_workspace"
                ? `Remove ${user.email} from ${pending.tenantName}`
                : pending.kind === "add_to_workspace"
                  ? `Add ${user.email} to a workspace`
                  : `${humanize(pending.kind)} · ${user.email}`
          }
          description={
            pending.kind === "delete"
              ? "Disables the account, removes all memberships, anonymises the email and signs them out."
              : pending.kind === "suspend"
                ? "Blocks sign-in and ends every session. Memberships are kept."
                : undefined
          }
          action={pending.kind}
          count={1}
          destructive={pending.kind === "delete" || pending.kind === "suspend" || pending.kind === "remove_from_workspace"}
          confirmLabel={pending.kind === "set_role" ? "Change role" : humanize(pending.kind)}
          canRun={pending.kind !== "add_to_workspace" || Boolean(tenantId)}
          onClose={(changed) => {
            setPending(null);
            if (changed) void refresh();
          }}
          onRun={async (reason) => {
            const destructive = pending.kind === "delete" || pending.kind === "suspend" || pending.kind === "remove_from_workspace";
            const payload: Record<string, unknown> = { action: pending.kind, reason, revokeSessions: true };
            if (pending.kind === "set_role") Object.assign(payload, { tenantId: pending.tenantId, role: pending.role });
            if (pending.kind === "remove_from_workspace") Object.assign(payload, { tenantId: pending.tenantId });
            if (pending.kind === "add_to_workspace") Object.assign(payload, { tenantId, role });
            return single(await runBulk("users", [id], payload, destructive));
          }}
        >
          {pending.kind === "add_to_workspace" && (
            <>
              <WorkspacePicker value={tenantId} onChange={(t) => setTenantId(t)} />
              <RolePicker value={role} onChange={setRole} />
            </>
          )}
        </ActionDialog>
      )}

      <ResetPasswordDialog open={resetOpen} user={user} onClose={() => setResetOpen(false)} />
    </Drawer>
  );
}

function ResetPasswordDialog({ open, user, onClose }: { open: boolean; user: AccountUser | null; onClose: () => void }) {
  const [busy, setBusy] = useState(false);
  const [temp, setTemp] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (open) {
      setTemp(null);
      setError(null);
    }
  }, [open]);
  return (
    <Modal open={open} title={`Reset password · ${user?.email ?? ""}`} onClose={onClose}>
      {temp ? (
        <>
          <Field label="New one-time password (shown once — share it securely)">
            <code className="block break-all rounded-skeuo-sm bg-surface-panel-inset px-3 py-2 font-mono text-sm text-text">{temp}</code>
          </Field>
          <div className="flex justify-end">
            <SkeuoButton variant="primary" onClick={onClose}>
              Done
            </SkeuoButton>
          </div>
        </>
      ) : (
        <>
          <p className="text-sm text-text-muted">Replaces the current password with a one-time password. Existing sessions are not ended — use “Sign out everywhere” for that.</p>
          {error && <Notice tone="error">{error}</Notice>}
          <div className="flex justify-end gap-2">
            <SkeuoButton variant="ghost" onClick={onClose}>
              Cancel
            </SkeuoButton>
            <SkeuoButton
              variant="primary"
              loading={busy}
              onClick={async () => {
                if (!user) return;
                setBusy(true);
                setError(null);
                try {
                  const res = await adminAction<{ devTempPassword?: string }>(`/api/dev/admin/users/${user.userId}/reset-password`, { method: "POST" });
                  setTemp(res.devTempPassword ?? "(set — no password returned)");
                } catch (e) {
                  setError(e instanceof Error ? e.message : "Reset failed");
                } finally {
                  setBusy(false);
                }
              }}
            >
              Reset password
            </SkeuoButton>
          </div>
        </>
      )}
    </Modal>
  );
}

/* =================================================================== number */

type NumPending = "assign_workspace" | "assign_agent" | "unassign_agent" | "release" | null;

export function NumberDrawer({ id, onClose, onOpen, onChanged }: DrawerProps) {
  const row = useAdminResource<ListPage<AccountNumber>>(`/api/dev/admin/accounts/numbers?q=${encodeURIComponent(id)}&limit=1`, [id]);
  const n = row.data?.items.find((x) => x.numberId === id) ?? null;
  const [pending, setPending] = useState<NumPending>(null);
  const [tenantId, setTenantId] = useState("");
  const [agentId, setAgentId] = useState("");

  async function refresh() {
    await row.reload();
    onChanged();
  }

  const releasing = n?.status === "release_pending";

  return (
    <Drawer
      open
      onClose={onClose}
      title={<span className="font-mono">{n?.e164 ?? (row.loading ? "Loading…" : "Number")}</span>}
      subtitle={n ? (n.inInventory ? "Platform inventory" : n.tenantName ?? "—") : undefined}
      badges={
        n && (
          <>
            <StatusBadge tone={numberTone(n.status)}>{humanize(n.status)}</StatusBadge>
            <StatusBadge tone={n.provider === "vobiz" ? "warning" : "info"}>{n.provider}</StatusBadge>
            {n.customerOwned && <StatusBadge tone="accent">customer-owned</StatusBadge>}
          </>
        )
      }
    >
      {row.error && <Notice tone="error">{row.error}</Notice>}
      {!row.loading && !n && !row.error && <Notice tone="warning">This number has been released and is no longer listed.</Notice>}
      {n && (
        <>
          {releasing && <Notice tone="warning">The carrier is releasing this number (24-hour cool-off). No further changes are possible.</Notice>}
          {!releasing && (
            <div className="flex flex-wrap gap-2">
              <SkeuoButton size="sm" variant="primary" onClick={() => { setTenantId(""); setPending("assign_workspace"); }}>
                {n.inInventory ? "Assign to workspace" : "Move to workspace"}
              </SkeuoButton>
              {!n.inInventory && (
                <SkeuoButton size="sm" variant="secondary" onClick={() => { setAgentId(n.agentId ?? ""); setPending("assign_agent"); }}>
                  {n.agentId ? "Change agent" : "Pin to agent"}
                </SkeuoButton>
              )}
              {n.agentId && (
                <SkeuoButton size="sm" variant="secondary" onClick={() => setPending("unassign_agent")}>
                  Unpin agent
                </SkeuoButton>
              )}
              {!n.inInventory && (
                <SkeuoButton size="sm" variant="ghost" className="text-status-error hover:bg-status-error/10" onClick={() => setPending("release")}>
                  Release…
                </SkeuoButton>
              )}
            </div>
          )}

          <KeyValues
            items={[
              [
                "Workspace",
                n.inInventory ? (
                  "Platform inventory"
                ) : n.tenantId ? (
                  <button key="ws" type="button" className="text-accent-primary underline" onClick={() => onOpen("ws", n.tenantId!)}>
                    {n.tenantName}
                  </button>
                ) : (
                  "—"
                ),
              ],
              ["Agent", n.agentName ?? (n.inInventory ? "—" : "Not pinned")],
              ["Ownership", n.customerOwned ? "Customer's Vobiz account" : "Platform"],
              ["Purchase", n.purchaseStatus ?? "manual"],
              ["Routing", `${n.inboundEnabled ? "Inbound on" : "Inbound off"} · ${n.outboundEnabled ? "outbound on" : "outbound off"}`],
              ["Carrier line", <span key="line" className="font-mono text-[10px]">{n.carrierNumberId || n.telnyxNumberId || "—"}</span>],
              ["Billing", humanize(n.billingSource)],
              ["Added", shortDate(n.createdAt)],
            ]}
          />
          {n.customerOwned && (
            <Notice>
              This number lives in the customer&apos;s own Vobiz account. It cannot be moved to another workspace without carrier reconciliation, and releasing it
              unrents it at Vobiz (release fee, 24-hour cool-off, then unrecoverable).
            </Notice>
          )}
        </>
      )}

      {pending && n && (
        <ActionDialog
          open
          title={
            pending === "assign_workspace"
              ? `${n.inInventory ? "Assign" : "Move"} ${n.e164}`
              : pending === "assign_agent"
                ? `Pin ${n.e164} to an agent`
                : pending === "unassign_agent"
                  ? `Unpin ${n.e164}`
                  : `Release ${n.e164}`
          }
          description={
            pending === "release"
              ? n.customerOwned
                ? "Unrents this number at Vobiz. A release fee is charged and after the 24-hour cool-off it cannot be recovered."
                : "Routing stops now and the number returns to platform inventory. Rental already charged is not refunded."
              : pending === "assign_workspace" && !n.inInventory
                ? "The number is unpinned from its current agent when it moves."
                : undefined
          }
          action={pending}
          count={1}
          destructive={pending === "release"}
          confirmLabel={pending === "release" ? "Release number" : pending === "unassign_agent" ? "Unpin" : "Save"}
          canRun={(pending !== "assign_workspace" || Boolean(tenantId)) && (pending !== "assign_agent" || Boolean(agentId))}
          onClose={(changed) => {
            setPending(null);
            if (changed) void refresh();
          }}
          onRun={async (reason) =>
            single(
              await runBulk(
                "numbers",
                [id],
                {
                  action: pending,
                  reason,
                  tenantId: pending === "assign_workspace" ? tenantId : undefined,
                  agentId: pending === "assign_agent" ? agentId : undefined,
                },
                pending === "release"
              )
            )
          }
        >
          {pending === "assign_workspace" && <WorkspacePicker value={tenantId} onChange={(t) => setTenantId(t)} excludeId={n.tenantId} label="Target workspace" />}
          {pending === "assign_agent" && n.tenantId && <AgentPicker tenantId={n.tenantId} value={agentId} onChange={setAgentId} />}
        </ActionDialog>
      )}
    </Drawer>
  );
}
