"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { adminAction, useAdminResource } from "@/lib/useAdminResource";
import { SkeuoBadge, SkeuoButton } from "@/components/ui/skeuo";
import { relativeTime, shortDate } from "../accounts/model";
import {
  Drawer,
  DrawerSection,
  EmptyState,
  Field,
  FilterSelect,
  KeyValues,
  Modal,
  Notice,
  TextInput,
  selectClass,
} from "../accounts/ui";
import {
  SUPER_ADMIN,
  absoluteLink,
  adminStatusLabel,
  adminTone,
  describeActivity,
  isWarning,
  roleTone,
  type ActivityEntry,
  type OneTimeLink,
  type PlatformAdmin,
  type RoleInfo,
  type RolesResponse,
  type TeamResponse,
} from "./model";

type Tab = "admins" | "roles" | "activity";

const TABS: Array<{ id: Tab; label: string; help: string; managersOnly: boolean }> = [
  { id: "admins", label: "Admins", help: "People who can sign in to this admin portal.", managersOnly: true },
  { id: "roles", label: "Roles & permissions", help: "What each role can see and do, in plain language.", managersOnly: false },
  { id: "activity", label: "Activity", help: "Every change to the admin team, newest first.", managersOnly: true },
];

/**
 * Roles & access: manage platform admins, see what each role can do, and audit
 * every change. Everything here is enforced by the API (`dev.admin.admins`); the
 * controls are hidden for other roles only so they don't click into a 403.
 *
 * URL: /dev/admin/access ? tab=admins|roles|activity & open=<admin id>
 */
export function TeamWorkspace() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [refresh, setRefresh] = useState(0);
  const roles = useAdminResource<RolesResponse>("/api/dev/admin/team/roles");
  const canManage = Boolean(roles.data?.me.canManageAdmins);
  const team = useAdminResource<TeamResponse>(canManage ? "/api/dev/admin/team" : null, [refresh]);

  const requested = params.get("tab") as Tab | null;
  const available = TABS.filter((t) => canManage || !t.managersOnly);
  const tab: Tab = requested && available.some((t) => t.id === requested) ? requested : available[0]?.id ?? "roles";
  const openId = params.get("open") ?? "";

  const replace = useCallback(
    (mutate: (p: URLSearchParams) => void) => {
      const next = new URLSearchParams(params.toString());
      mutate(next);
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router]
  );
  const onChanged = useCallback(() => setRefresh((n) => n + 1), []);
  const roleLabel = useCallback(
    (key: string) => roles.data?.roles.find((r) => r.key === key)?.label ?? key.replace(/_/g, " "),
    [roles.data]
  );
  const opened = team.data?.admins.find((a) => a.id === openId) ?? null;

  return (
    <div className="space-y-5 p-6" data-testid="team-page">
      <header className="flex flex-col gap-1">
        <p className="label-caps text-accent-primary">Platform access</p>
        <h1 className="text-2xl font-semibold tracking-tight text-text">Roles & access</h1>
        <p className="max-w-3xl text-sm text-text-muted">
          Who can sign in to this admin portal, what each role lets them do, and a record of every change. Every change asks for a reason and is written
          to the activity log; the server enforces all of it, not just this screen.
        </p>
      </header>

      {roles.error && <Notice tone="error">{roles.error}</Notice>}
      {roles.loading && !roles.data && <p className="py-8 text-center text-sm text-text-muted">Loading…</p>}

      {roles.data && (
        <>
          <YourAccess me={roles.data.me} />

          <div className="flex flex-wrap items-end justify-between gap-3 border-b border-surface-border-subtle">
            <nav className="flex gap-1" role="tablist" aria-label="Roles & access views">
              {available.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={tab === t.id}
                  onClick={() => replace((p) => { p.set("tab", t.id); p.delete("open"); })}
                  className={cn(
                    "-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition-colors",
                    tab === t.id ? "border-accent-primary text-text" : "border-transparent text-text-muted hover:text-text"
                  )}
                  data-testid={`team-tab-${t.id}`}
                >
                  {t.label}
                </button>
              ))}
            </nav>
            <p className="pb-2 text-xs text-text-muted">{TABS.find((t) => t.id === tab)?.help}</p>
          </div>

          {tab === "admins" && canManage && (
            <AdminsView
              team={team.data}
              loading={team.loading}
              error={team.error}
              roles={roles.data.roles}
              onOpen={(id) => replace((p) => p.set("open", id))}
              onChanged={onChanged}
            />
          )}
          {tab === "roles" && <RolesView data={roles.data} />}
          {tab === "activity" && canManage && <ActivityView roleLabel={roleLabel} refresh={refresh} />}

          {tab === "admins" && opened && team.data && (
            <AdminDrawer
              key={opened.id}
              admin={opened}
              team={team.data}
              roles={roles.data.roles}
              onClose={() => replace((p) => p.delete("open"))}
              onChanged={onChanged}
            />
          )}
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ your access */

function YourAccess({ me }: { me: RolesResponse["me"] }) {
  return (
    <section className="card-surface flex flex-wrap items-center gap-x-4 gap-y-2 p-4 text-sm" aria-label="Your access" data-testid="team-me">
      <div className="flex items-center gap-2">
        <span className="text-text-muted">Signed in as</span>
        <span className="font-semibold text-text">{me.subject}</span>
        <SkeuoBadge tone={roleTone(me.role)}>{me.roleLabel}</SkeuoBadge>
        {me.builtin && <SkeuoBadge tone="muted">Built-in login</SkeuoBadge>}
      </div>
      <p className="text-xs text-text-muted">
        {me.canManageAdmins
          ? "You can invite, change and remove admins. You can't change your own account."
          : "You can see what each role allows. Only super admins can manage the admin team."}
      </p>
    </section>
  );
}

/* ------------------------------------------------------------------ admins list */

function AdminsView({
  team,
  loading,
  error,
  roles,
  onOpen,
  onChanged,
}: {
  team: TeamResponse | null;
  loading: boolean;
  error: string | null;
  roles: RoleInfo[];
  onOpen: (id: string) => void;
  onChanged: () => void;
}) {
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [inviting, setInviting] = useState(false);
  const admins = useMemo(() => team?.admins ?? [], [team]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return admins.filter((a) => {
      if (role && a.role !== role) return false;
      if (status === "reset" ? a.link?.purpose !== "reset" : status && a.status !== status) return false;
      if (!needle) return true;
      return [a.fullName, a.email, a.username].some((v) => v.toLowerCase().includes(needle));
    });
  }, [admins, q, role, status]);

  const counts = useMemo(
    () => ({
      active: admins.filter((a) => a.status === "active").length,
      invited: admins.filter((a) => a.status === "invited").length,
      suspended: admins.filter((a) => a.status === "suspended").length,
      supers: admins.filter((a) => a.role === SUPER_ADMIN && a.status === "active").length,
    }),
    [admins]
  );
  const hasFilters = Boolean(q || role || status);
  const storeReady = team?.store.ready ?? true;

  return (
    <div className="space-y-4">
      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Totals">
        <Tile label="Active admins" value={team ? counts.active : undefined} onClick={() => setStatus("active")} />
        <Tile label="Invited" value={team ? counts.invited : undefined} tone={counts.invited ? "warn" : undefined} onClick={() => setStatus("invited")} />
        <Tile label="Suspended" value={team ? counts.suspended : undefined} onClick={() => setStatus("suspended")} />
        <Tile
          label="Super admins"
          value={team ? counts.supers + (team.builtin.configured ? 1 : 0) : undefined}
          detail={team?.builtin.configured ? "Includes the built-in login" : undefined}
          onClick={() => setRole(SUPER_ADMIN)}
        />
      </section>

      {error && <Notice tone="error">{error}</Notice>}
      {team && !storeReady && <Notice tone="warning">{team.store.reason}</Notice>}

      <div className="flex flex-wrap items-end gap-3">
        <Field label="Search" className="min-w-[220px] flex-1">
          <TextInput value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name, email or username" aria-label="Search admins" />
        </Field>
        <div className="w-44">
          <FilterSelect
            label="Role"
            value={role}
            onChange={setRole}
            anyLabel="All roles"
            options={roles.filter((r) => r.assignable).map((r) => ({ value: r.key, label: r.label }))}
          />
        </div>
        <div className="w-48">
          <FilterSelect
            label="Status"
            value={status}
            onChange={setStatus}
            anyLabel="All statuses"
            options={[
              { value: "active", label: "Active" },
              { value: "invited", label: "Invited" },
              { value: "suspended", label: "Suspended" },
              { value: "reset", label: "Password reset pending" },
            ]}
          />
        </div>
        {hasFilters && (
          <button type="button" className="pb-2 text-xs text-accent-primary underline" onClick={() => { setQ(""); setRole(""); setStatus(""); }}>
            Clear filters
          </button>
        )}
        <SkeuoButton variant="primary" className="ml-auto" disabled={!storeReady} onClick={() => setInviting(true)} data-testid="team-invite">
          Invite admin
        </SkeuoButton>
      </div>

      <div className="overflow-x-auto rounded-skeuo-md border border-surface-border-subtle">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="border-b border-surface-border-subtle bg-surface-panel-inset text-text-subtle">
            <tr>
              {["Admin", "Role", "Status", "Last sign-in", "Added"].map((h) => (
                <th key={h} className="whitespace-nowrap px-3 py-3 font-mono text-[10px] font-medium uppercase tracking-wider">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border-subtle">
            {team?.builtin.configured && !hasFilters && (
              <tr className="bg-surface-panel" data-testid="team-builtin-row">
                <td className="px-3 py-2.5">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-text">{team.builtin.username}</span>
                    <SkeuoBadge tone="muted">Built-in</SkeuoBadge>
                    {team.builtin.isSelf && <SkeuoBadge tone="accent">You</SkeuoBadge>}
                  </div>
                  <p className="text-xs text-text-muted">Break-glass login from server configuration (DEV_PORTAL_USERNAME). Change it there, not here.</p>
                </td>
                <td className="px-3 py-2.5"><SkeuoBadge tone="accent">Super admin</SkeuoBadge></td>
                <td className="px-3 py-2.5"><SkeuoBadge tone="success">Active</SkeuoBadge></td>
                <td className="px-3 py-2.5 text-xs text-text-muted">Not tracked</td>
                <td className="px-3 py-2.5 text-xs text-text-muted">Server config</td>
              </tr>
            )}
            {filtered.map((a) => (
              <tr
                key={a.id}
                className="cursor-pointer bg-surface-panel transition-colors hover:bg-surface-panel-raised/60"
                onClick={() => onOpen(a.id)}
                data-testid="team-row"
              >
                <td className="px-3 py-2.5">
                  <button type="button" className="text-left" onClick={() => onOpen(a.id)}>
                    <span className="flex items-center gap-2">
                      <span className="font-medium text-text">{a.fullName || a.username}</span>
                      {a.isSelf && <SkeuoBadge tone="accent">You</SkeuoBadge>}
                    </span>
                    <span className="block text-xs text-text-muted">
                      {a.email} · <span className="font-mono">@{a.username}</span>
                    </span>
                  </button>
                </td>
                <td className="px-3 py-2.5">
                  <SkeuoBadge tone={roleTone(a.role)}>{a.roleLabel}</SkeuoBadge>
                  {a.isLastSuperAdmin && <p className="mt-1 text-[11px] text-text-subtle">Last super admin</p>}
                </td>
                <td className="px-3 py-2.5">
                  <SkeuoBadge tone={adminTone(a)}>{adminStatusLabel(a)}</SkeuoBadge>
                  {a.link?.state === "pending" && a.link.expiresAt && (
                    <p className="mt-1 text-[11px] text-text-subtle">Link expires {shortDate(a.link.expiresAt)}</p>
                  )}
                </td>
                <td className="whitespace-nowrap px-3 py-2.5 text-xs text-text-muted" title={a.lastSignInAt ?? undefined}>
                  {a.lastSignInAt ? relativeTime(a.lastSignInAt) : "Never"}
                </td>
                <td className="whitespace-nowrap px-3 py-2.5 text-xs text-text-muted">
                  {shortDate(a.createdAt)}
                  <span className="block text-[11px] text-text-subtle">by {a.createdBy || "—"}</span>
                </td>
              </tr>
            ))}
            {!loading && filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-10">
                  {hasFilters ? (
                    <EmptyState title="No admins match these filters" body="Try a different search, role or status." />
                  ) : (
                    <EmptyState
                      title="No invited admins yet"
                      body={
                        storeReady
                          ? "Only the built-in login can sign in. Invite your team so each person has their own account, role and audit trail."
                          : "Admin accounts can't be stored until the database migration has run."
                      }
                      action={
                        storeReady ? (
                          <SkeuoButton variant="primary" size="sm" onClick={() => setInviting(true)}>
                            Invite the first admin
                          </SkeuoButton>
                        ) : undefined
                      }
                    />
                  )}
                </td>
              </tr>
            )}
            {loading && !team && (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-sm text-text-muted">Loading admins…</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-text-subtle">
        Two-factor sign-in isn&apos;t available for the admin portal yet. Sessions end within seconds when an admin is suspended, removed, signed out or has
        their password reset.
      </p>

      {team && team.consoleAdmins.length > 0 && <ConsoleAdmins admins={team.consoleAdmins} />}

      <InviteDialog
        open={inviting}
        roles={roles.filter((r) => r.assignable)}
        policy={team?.policy}
        onClose={(changed) => {
          setInviting(false);
          if (changed) onChanged();
        }}
      />
    </div>
  );
}

function Tile({ label, value, detail, tone, onClick }: { label: string; value: number | undefined; detail?: string; tone?: "warn"; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="card-surface p-4 text-left transition-colors hover:border-accent-primary/40">
      <p className="text-[11px] uppercase tracking-wider text-text-subtle">{label}</p>
      <p className={cn("mt-1 font-mono text-2xl", tone === "warn" ? "text-status-warning" : "text-text")}>{value ?? "—"}</p>
      {detail && <p className="mt-1 text-xs text-text-muted">{detail}</p>}
    </button>
  );
}

function ConsoleAdmins({ admins }: { admins: TeamResponse["consoleAdmins"] }) {
  return (
    <details className="card-surface p-4 text-sm" data-testid="team-console-admins">
      <summary className="cursor-pointer font-medium text-text">
        Business-console platform admins ({admins.length}) <span className="font-normal text-text-muted">— read-only</span>
      </summary>
      <p className="mt-2 text-xs text-text-muted">
        These customer-console accounts get platform-admin rights from the server setting SAAS_PLATFORM_ADMIN_EMAILS, re-checked on every request.
        They don&apos;t sign in to this portal. Change the setting to add or remove one.
      </p>
      <ul className="mt-3 divide-y divide-surface-border-subtle rounded-skeuo-sm border border-surface-border-subtle">
        {admins.map((a) => (
          <li key={a.email} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
            <span>
              <span className="text-text">{a.fullName || a.email}</span>
              {a.fullName && <span className="ml-2 text-xs text-text-muted">{a.email}</span>}
            </span>
            <SkeuoBadge tone={a.exists ? (a.status === "active" ? "success" : "warning") : "muted"}>
              {a.exists ? (a.status ?? "unknown").replace(/_/g, " ") : "No account yet"}
            </SkeuoBadge>
          </li>
        ))}
      </ul>
    </details>
  );
}

/* ------------------------------------------------------------------ invite */

function InviteDialog({
  open,
  roles,
  policy,
  onClose,
}: {
  open: boolean;
  roles: RoleInfo[];
  policy?: TeamResponse["policy"];
  onClose: (changed: boolean) => void;
}) {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [role, setRole] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [link, setLink] = useState<OneTimeLink | null>(null);
  const minReason = policy?.minReasonLength ?? 5;

  useEffect(() => {
    if (open) {
      setEmail("");
      setFullName("");
      setUsername("");
      setRole("");
      setReason("");
      setError(null);
      setLink(null);
      setBusy(false);
    }
  }, [open]);

  const chosen = roles.find((r) => r.key === role);
  const ready = /\S+@\S+\.\S+/.test(email) && Boolean(role) && reason.trim().length >= minReason;

  async function submit() {
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      const res = await adminAction<{ link: OneTimeLink }>("/api/dev/admin/team/invite", {
        body: {
          email: email.trim(),
          fullName: fullName.trim() || null,
          username: username.trim() || null,
          role,
          reason: reason.trim(),
          portalOrigin: window.location.origin,
        },
      });
      setLink(res.link);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invite failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} title={link ? "Invite created" : "Invite an admin"} onClose={() => !busy && onClose(Boolean(link))} wide>
      {link ? (
        <LinkReveal link={link} onDone={() => onClose(true)} />
      ) : (
        <>
          <p className="text-sm text-text-muted">
            They get a one-time link to choose their own password. It expires in {policy?.inviteTtlHours ?? 72} hours. You never see or set their password.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Work email">
              <TextInput type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com" autoComplete="off" data-testid="invite-email" />
            </Field>
            <Field label="Full name (optional)">
              <TextInput value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="off" />
            </Field>
            <Field label="Username (optional)" hint="Used to sign in. Defaults to the part of the email before @.">
              <TextInput value={username} onChange={(e) => setUsername(e.target.value.toLowerCase())} placeholder="e.g. priya" autoComplete="off" />
            </Field>
            <Field label="Role">
              <select value={role} onChange={(e) => setRole(e.target.value)} className={selectClass} data-testid="invite-role">
                <option value="">Choose a role…</option>
                {roles.map((r) => (
                  <option key={r.key} value={r.key}>
                    {r.label}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          {chosen && <RoleSummary role={chosen} compact />}
          {chosen?.key === SUPER_ADMIN && (
            <Notice tone="warning">Super admins can do everything, including removing other admins. Give this role to as few people as possible.</Notice>
          )}
          <ReasonField value={reason} onChange={setReason} min={minReason} />
          {error && <Notice tone="error">{error}</Notice>}
          <div className="flex justify-end gap-2 pt-1">
            <SkeuoButton variant="ghost" disabled={busy} onClick={() => onClose(false)}>
              Cancel
            </SkeuoButton>
            <SkeuoButton variant="primary" disabled={!ready || busy} loading={busy} onClick={() => void submit()} data-testid="invite-submit">
              Create invite
            </SkeuoButton>
          </div>
        </>
      )}
    </Modal>
  );
}

function ReasonField({ value, onChange, min }: { value: string; onChange: (v: string) => void; min: number }) {
  return (
    <Field label="Reason (saved to the audit log)" hint={`At least ${min} characters. Stored with your admin identity.`}>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={2}
        className={selectClass}
        placeholder="Why are you doing this?"
        data-testid="action-reason"
      />
    </Field>
  );
}

/** Shows a one-time invite/reset link exactly once. It is never retrievable again. */
function LinkReveal({ link, onDone }: { link: OneTimeLink; onDone: () => void }) {
  const url = absoluteLink(link.path);
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }
  return (
    <div className="space-y-3" data-testid="link-reveal">
      <Notice tone={link.emailed ? "success" : "info"}>{link.emailNote}</Notice>
      <Field label={link.purpose === "invite" ? "One-time invite link" : "One-time password reset link"}>
        <div className="flex gap-2">
          <TextInput readOnly value={url} onFocus={(e) => e.currentTarget.select()} className="font-mono text-xs" aria-label="One-time link" />
          <SkeuoButton variant="secondary" onClick={() => void copy()}>
            {copied ? "Copied" : "Copy"}
          </SkeuoButton>
        </div>
      </Field>
      <Notice tone="warning">
        This link is shown once and works once. Send it to the admin through a channel you trust. It expires{" "}
        {link.expiresAt ? new Date(link.expiresAt).toLocaleString() : "soon"}. If it&apos;s lost, issue a new one — the old one stops working.
      </Notice>
      <div className="flex justify-end">
        <SkeuoButton variant="primary" onClick={onDone}>
          Done
        </SkeuoButton>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ drawer & actions */

type ActionKind = "role" | "resend" | "reset" | "signout" | "suspend" | "reactivate" | "remove";

type ActionSpec = {
  title: string;
  confirmLabel: string;
  endpoint: string;
  description: ReactNode;
  typed: boolean;
  danger: boolean;
};

function actionSpec(kind: ActionKind, admin: PlatformAdmin, newRole: string, roleLabel: (k: string) => string, policy: TeamResponse["policy"]): ActionSpec {
  const name = admin.fullName || admin.username;
  switch (kind) {
    case "role":
      return {
        title: `Change ${name}'s role`,
        confirmLabel: "Change role",
        endpoint: "role",
        description: `From ${admin.roleLabel} to ${roleLabel(newRole)}. Takes effect on their open sessions within seconds.`,
        typed: admin.role === SUPER_ADMIN || newRole === SUPER_ADMIN,
        danger: false,
      };
    case "resend":
      return {
        title: `Re-send invite to ${name}`,
        confirmLabel: "Create new link",
        endpoint: "resend-invite",
        description: `Creates a new one-time link (valid ${policy.inviteTtlHours} hours). Any earlier link stops working.`,
        typed: false,
        danger: false,
      };
    case "reset":
      return {
        title: `Reset ${name}'s password`,
        confirmLabel: "Reset password",
        endpoint: "reset-password",
        description: `Their current password stops working and they are signed out everywhere now. They choose a new one with a one-time link (valid ${policy.resetTtlHours} hours).`,
        typed: true,
        danger: true,
      };
    case "signout":
      return {
        title: `Sign ${name} out everywhere`,
        confirmLabel: "Sign out everywhere",
        endpoint: "sign-out",
        description: admin.isSelf
          ? "This ends every session you hold, including this one. You'll need to sign in again."
          : "Ends every session they hold on every device. Their password keeps working.",
        typed: false,
        danger: false,
      };
    case "suspend":
      return {
        title: `Suspend ${name}`,
        confirmLabel: "Suspend",
        endpoint: "suspend",
        description: "They are signed out everywhere and can't sign in until reactivated. Nothing else changes.",
        typed: true,
        danger: true,
      };
    case "reactivate":
      return {
        title: `Reactivate ${name}`,
        confirmLabel: "Reactivate",
        endpoint: "reactivate",
        description: admin.hasPassword ? "They can sign in again with their existing password." : "They go back to invited; re-send the invite so they can set a password.",
        typed: false,
        danger: false,
      };
    case "remove":
      return {
        title: `Remove ${name}`,
        confirmLabel: "Remove admin",
        endpoint: "remove",
        description: "Their account is closed, every session ends, and their email and username become free to reuse. The audit trail keeps who they were.",
        typed: true,
        danger: true,
      };
  }
}

function AdminDrawer({
  admin,
  team,
  roles,
  onClose,
  onChanged,
}: {
  admin: PlatformAdmin;
  team: TeamResponse;
  roles: RoleInfo[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const [action, setAction] = useState<ActionKind | null>(null);
  const [newRole, setNewRole] = useState(admin.role);
  const assignable = roles.filter((r) => r.assignable);
  const roleInfo = roles.find((r) => r.key === admin.role);
  const roleLabel = (k: string) => roles.find((r) => r.key === k)?.label ?? k;
  const self = admin.isSelf;
  const lastSuper = admin.isLastSuperAdmin;
  const blockedSelf = "You can't change your own account. Ask another super admin.";
  const blockedLast = "This is the last active super admin. Make someone else a super admin first.";

  return (
    <Drawer
      open
      title={admin.fullName || admin.username}
      subtitle={
        <>
          {admin.email} · <span className="font-mono">@{admin.username}</span>
        </>
      }
      badges={
        <>
          <SkeuoBadge tone={roleTone(admin.role)}>{admin.roleLabel}</SkeuoBadge>
          <SkeuoBadge tone={adminTone(admin)}>{adminStatusLabel(admin)}</SkeuoBadge>
          {self && <SkeuoBadge tone="accent">You</SkeuoBadge>}
        </>
      }
      onClose={onClose}
    >
      {self && <Notice>{blockedSelf} You can still sign yourself out everywhere.</Notice>}
      {lastSuper && !self && <Notice tone="warning">{blockedLast} Until then they can't be demoted, suspended or removed.</Notice>}
      {admin.status === "suspended" && admin.statusReason && <Notice tone="warning">Suspended: {admin.statusReason}</Notice>}

      <DrawerSection title="Details">
        <KeyValues
          items={[
            ["Last sign-in", admin.lastSignInAt ? `${relativeTime(admin.lastSignInAt)}${admin.lastSignInIp ? ` · ${admin.lastSignInIp}` : ""}` : "Never"],
            ["Two-factor", "Not available"],
            ["Password", admin.hasPassword ? `Set ${admin.passwordChangedAt ? shortDate(admin.passwordChangedAt) : ""}` : "Not set"],
            [
              "One-time link",
              admin.link ? `${admin.link.purpose === "invite" ? "Invite" : "Reset"} · ${admin.link.state === "expired" ? "expired" : `expires ${shortDate(admin.link.expiresAt)}`}` : "None",
            ],
            ["Added", `${shortDate(admin.createdAt)} by ${admin.createdBy || "—"}`],
            ["Last changed", `${shortDate(admin.updatedAt)}${admin.updatedBy ? ` by ${admin.updatedBy}` : ""}`],
          ]}
        />
      </DrawerSection>

      <DrawerSection title="Role" hint="What they can see and do in this portal.">
        <div className="space-y-2">
          {roleInfo && <RoleSummary role={roleInfo} compact />}
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Change to" className="min-w-[200px] flex-1">
              <select value={newRole} onChange={(e) => setNewRole(e.target.value)} className={selectClass} disabled={self} data-testid="drawer-role">
                {assignable.map((r) => (
                  <option key={r.key} value={r.key}>
                    {r.label}
                  </option>
                ))}
              </select>
            </Field>
            <SkeuoButton
              variant="secondary"
              disabled={self || newRole === admin.role || (lastSuper && newRole !== SUPER_ADMIN)}
              title={self ? blockedSelf : lastSuper ? blockedLast : undefined}
              onClick={() => setAction("role")}
            >
              Change role
            </SkeuoButton>
          </div>
        </div>
      </DrawerSection>

      <DrawerSection title="Sign-in & sessions">
        <div className="flex flex-wrap gap-2">
          {admin.status === "invited" && (
            <SkeuoButton variant="secondary" size="sm" onClick={() => setAction("resend")}>
              {admin.link?.state === "expired" ? "Send a new invite link" : "Re-send invite"}
            </SkeuoButton>
          )}
          {admin.status === "active" && (
            <SkeuoButton variant="secondary" size="sm" disabled={self} title={self ? blockedSelf : undefined} onClick={() => setAction("reset")}>
              Reset password
            </SkeuoButton>
          )}
          <SkeuoButton variant="secondary" size="sm" onClick={() => setAction("signout")}>
            Sign out everywhere
          </SkeuoButton>
        </div>
      </DrawerSection>

      <DrawerSection title="Access" hint="Suspension can be undone. Removal can't.">
        <div className="flex flex-wrap gap-2">
          {admin.status === "suspended" ? (
            <SkeuoButton variant="secondary" size="sm" disabled={self} onClick={() => setAction("reactivate")}>
              Reactivate
            </SkeuoButton>
          ) : (
            <SkeuoButton
              variant="secondary"
              size="sm"
              disabled={self || lastSuper}
              title={self ? blockedSelf : lastSuper ? blockedLast : undefined}
              onClick={() => setAction("suspend")}
            >
              Suspend
            </SkeuoButton>
          )}
          <SkeuoButton
            variant="secondary"
            size="sm"
            className="text-status-error"
            disabled={self || lastSuper}
            title={self ? blockedSelf : lastSuper ? blockedLast : undefined}
            onClick={() => setAction("remove")}
            data-testid="drawer-remove"
          >
            Remove admin
          </SkeuoButton>
        </div>
      </DrawerSection>

      {action && (
        <AdminActionDialog
          admin={admin}
          spec={actionSpec(action, admin, newRole, roleLabel, team.policy)}
          extra={action === "role" ? { role: newRole } : undefined}
          minReason={team.policy.minReasonLength}
          onClose={(changed) => {
            setAction(null);
            if (changed) onChanged();
          }}
        />
      )}
    </Drawer>
  );
}

function AdminActionDialog({
  admin,
  spec,
  extra,
  minReason,
  onClose,
}: {
  admin: PlatformAdmin;
  spec: ActionSpec;
  extra?: Record<string, string>;
  minReason: number;
  onClose: (changed: boolean) => void;
}) {
  const [reason, setReason] = useState("");
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [link, setLink] = useState<OneTimeLink | null>(null);
  const ready = reason.trim().length >= minReason && (!spec.typed || typed.trim().toLowerCase() === admin.username.toLowerCase());

  async function submit() {
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      const res = await adminAction<{ link?: OneTimeLink }>(`/api/dev/admin/team/${admin.id}/${spec.endpoint}`, {
        body: { reason: reason.trim(), confirm: typed.trim(), portalOrigin: window.location.origin, ...extra },
      });
      if (res?.link) setLink(res.link);
      else onClose(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open title={link ? "Link created" : spec.title} onClose={() => !busy && onClose(Boolean(link))} wide={Boolean(link)} labelledBy="team-action-title">
      {link ? (
        <LinkReveal link={link} onDone={() => onClose(true)} />
      ) : (
        <>
          <p className="text-sm text-text-muted">{spec.description}</p>
          <ReasonField value={reason} onChange={setReason} min={minReason} />
          {spec.typed && (
            <Field label={`Type ${admin.username} to confirm`}>
              <TextInput value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={admin.username} autoComplete="off" data-testid="action-confirm" />
            </Field>
          )}
          {error && <Notice tone="error">{error}</Notice>}
          <div className="flex justify-end gap-2 pt-1">
            <SkeuoButton variant="ghost" disabled={busy} onClick={() => onClose(false)}>
              Cancel
            </SkeuoButton>
            <SkeuoButton
              variant="primary"
              disabled={!ready || busy}
              loading={busy}
              onClick={() => void submit()}
              className={spec.danger ? "!bg-status-error !bg-none" : undefined}
              data-testid="action-submit"
            >
              {spec.confirmLabel}
            </SkeuoButton>
          </div>
        </>
      )}
    </Modal>
  );
}

/* ------------------------------------------------------------------ roles */

function RoleSummary({ role, compact }: { role: RoleInfo; compact?: boolean }) {
  return (
    <div className={cn("rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset p-3 text-xs", compact && "py-2")}>
      <p className="text-text">{role.summary}</p>
      {role.cannot.length > 0 && <p className="mt-1 text-text-muted">No access to: {role.cannot.join(", ")}.</p>}
    </div>
  );
}

function RolesView({ data }: { data: RolesResponse }) {
  const [showLegacy, setShowLegacy] = useState(false);
  const shown = data.roles.filter((r) => r.assignable || showLegacy);
  const portalAreas = data.areas.filter((a) => a.key !== "console");
  return (
    <div className="space-y-4" data-testid="team-roles">
      <Notice>
        {data.customRolesSupported
          ? "Roles can be customised."
          : "These roles are built in and read-only: the server has no storage for custom roles yet. Every tick below is what the API enforces — a missing one is a refusal, not a hidden button."}
      </Notice>

      <div className="grid gap-3 lg:grid-cols-2">
        {shown.map((role) => (
          <article
            key={role.key}
            className={cn("card-surface p-4", role.key === data.me.role && "border-accent-primary/50")}
            data-testid={`role-card-${role.key}`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-base font-semibold text-text">{role.label}</h3>
              {role.key === data.me.role && <SkeuoBadge tone="accent">Your role</SkeuoBadge>}
              {!role.assignable && <SkeuoBadge tone="muted">Legacy</SkeuoBadge>}
            </div>
            <p className="mt-1 text-sm text-text-muted">{role.summary}</p>
            <div className="mt-3 space-y-3">
              {role.groups
                .filter((g) => g.area !== "console")
                .map((g) => (
                  <div key={g.area}>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-text-subtle">{g.label}</p>
                    <ul className="mt-1 space-y-1">
                      {g.permissions.map((p) => (
                        <li key={p.name} className="flex gap-2 text-xs">
                          <span aria-hidden className="text-status-success">✓</span>
                          <span>
                            <span className="text-text">{p.label}</span>
                            <span className="text-text-muted"> — {p.detail}</span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              {role.cannot.length > 0 && (
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-text-subtle">No access</p>
                  <p className="mt-1 text-xs text-text-muted">{role.cannot.join(" · ")}</p>
                </div>
              )}
            </div>
          </article>
        ))}
      </div>
      <button type="button" className="text-xs text-accent-primary underline" onClick={() => setShowLegacy((v) => !v)}>
        {showLegacy ? "Hide legacy roles" : "Show legacy roles (older sessions and integrations)"}
      </button>

      <details className="card-surface p-4">
        <summary className="cursor-pointer text-sm font-medium text-text">Compare roles by area</summary>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-xs">
            <thead className="text-text-subtle">
              <tr>
                <th className="px-2 py-2 font-mono text-[10px] uppercase tracking-wider">Permission</th>
                {shown.map((r) => (
                  <th key={r.key} className="px-2 py-2 text-center font-mono text-[10px] uppercase tracking-wider">
                    {r.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border-subtle">
              {portalAreas.map((area) =>
                data.permissions
                  .filter((p) => p.area === area.key)
                  .map((p, i) => (
                    <tr key={p.name}>
                      <td className="px-2 py-1.5">
                        {i === 0 && <span className="mb-0.5 block text-[10px] uppercase tracking-wider text-text-subtle">{area.label}</span>}
                        <span className="text-text">{p.label}</span>
                        <span className="ml-1 font-mono text-[10px] text-text-subtle">{p.name}</span>
                      </td>
                      {shown.map((r) => {
                        const has = r.permissions.includes(p.name);
                        return (
                          <td key={r.key} className="px-2 py-1.5 text-center">
                            <span aria-label={`${p.label} for ${r.label}: ${has ? "allowed" : "not allowed"}`} className={has ? "text-status-success" : "text-text-subtle"}>
                              {has ? "✓" : "—"}
                            </span>
                          </td>
                        );
                      })}
                    </tr>
                  ))
              )}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

/* ------------------------------------------------------------------ activity */

function ActivityView({ roleLabel, refresh }: { roleLabel: (k: string) => string; refresh: number }) {
  const [limit, setLimit] = useState(30);
  const { data, error, loading } = useAdminResource<{ entries: ActivityEntry[]; total: number }>(
    `/api/dev/admin/team/activity?limit=${limit}`,
    [refresh]
  );
  const entries = data?.entries ?? [];
  return (
    <div className="space-y-3" data-testid="team-activity">
      {error && <Notice tone="error">{error}</Notice>}
      {loading && !data && <p className="py-8 text-center text-sm text-text-muted">Loading activity…</p>}
      {data && entries.length === 0 && (
        <div className="card-surface p-8">
          <EmptyState title="No admin-team changes yet" body="Invites, role changes, suspensions and removals will appear here with who made them and why." />
        </div>
      )}
      {entries.length > 0 && (
        <ol className="divide-y divide-surface-border-subtle rounded-skeuo-md border border-surface-border-subtle bg-surface-panel">
          {entries.map((e) => (
            <li key={e.id} className="flex flex-wrap items-start justify-between gap-2 px-4 py-3 text-sm">
              <div className="min-w-0">
                <p className="text-text">{describeActivity(e, roleLabel)}</p>
                {typeof e.payload.reason === "string" && e.payload.reason && (
                  <p className="mt-0.5 text-xs text-text-muted">“{e.payload.reason}”</p>
                )}
              </div>
              <div className="flex items-center gap-2 text-xs text-text-muted">
                {isWarning(e) && <SkeuoBadge tone="warning">Check</SkeuoBadge>}
                <time dateTime={e.createdAt ?? undefined} title={e.createdAt ?? undefined}>
                  {relativeTime(e.createdAt)}
                </time>
              </div>
            </li>
          ))}
        </ol>
      )}
      {data && data.total > entries.length && (
        <div className="flex justify-center">
          <SkeuoButton variant="secondary" size="sm" onClick={() => setLimit((n) => Math.min(200, n + 30))} disabled={limit >= 200}>
            Show more
          </SkeuoButton>
        </div>
      )}
      <p className="text-xs text-text-subtle">The full platform history, with filters, is on the Activity log page.</p>
    </div>
  );
}
