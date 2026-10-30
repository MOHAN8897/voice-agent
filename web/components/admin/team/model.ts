import type { BadgeTone } from "../accounts/model";

/** Shapes served by `/api/dev/admin/team*` (server/routes/dev_admin_team.py). */

export type AdminStatus = "invited" | "active" | "suspended";

export type PlatformAdmin = {
  id: string;
  username: string;
  email: string;
  fullName: string;
  role: string;
  roleLabel: string;
  status: AdminStatus;
  statusReason: string | null;
  hasPassword: boolean;
  link: { purpose: "invite" | "reset"; state: "pending" | "expired"; expiresAt: string | null; sentAt: string | null } | null;
  lastSignInAt: string | null;
  lastSignInIp: string | null;
  passwordChangedAt: string | null;
  createdAt: string | null;
  createdBy: string;
  updatedAt: string | null;
  updatedBy: string | null;
  isSelf: boolean;
  isLastSuperAdmin: boolean;
  mfa: null;
};

export type ConsoleAdmin = { email: string; exists: boolean; fullName: string; status: string | null; verified: boolean };

export type TeamResponse = {
  store: { ready: boolean; reason: string | null };
  admins: PlatformAdmin[];
  builtin: { configured: boolean; username: string | null; role: string; isSelf: boolean };
  consoleAdmins: ConsoleAdmin[];
  policy: { inviteTtlHours: number; resetTtlHours: number; minPasswordLength: number; minReasonLength: number; mfaSupported: boolean };
};

export type RolePermission = { name: string; label: string; detail: string };

export type RoleInfo = {
  key: string;
  label: string;
  summary: string;
  assignable: boolean;
  permissions: string[];
  groups: Array<{ area: string; label: string; permissions: RolePermission[] }>;
  cannot: string[];
};

export type RolesResponse = {
  roles: RoleInfo[];
  areas: Array<{ key: string; label: string }>;
  permissions: Array<{ name: string; area: string; label: string; detail: string; roles: string[] }>;
  customRolesSupported: boolean;
  me: { subject: string; role: string; roleLabel: string; builtin: boolean; permissions: string[]; canManageAdmins: boolean };
};

export type OneTimeLink = {
  path: string;
  expiresAt: string | null;
  purpose: "invite" | "reset";
  emailed: boolean;
  emailNote: string;
};

export type ActivityEntry = {
  id: string;
  actor: string;
  action: string;
  resourceId: string;
  payload: Record<string, unknown>;
  outcome: string;
  createdAt: string | null;
};

export const SUPER_ADMIN = "super_admin";

export function adminTone(admin: PlatformAdmin): BadgeTone {
  if (admin.status === "suspended") return "error";
  if (admin.status === "invited") return admin.link?.state === "expired" ? "muted" : "warning";
  if (admin.link?.purpose === "reset") return "warning";
  return "success";
}

export function adminStatusLabel(admin: PlatformAdmin): string {
  if (admin.status === "suspended") return "Suspended";
  if (admin.status === "invited") return admin.link?.state === "expired" ? "Invite expired" : "Invited";
  if (admin.link?.purpose === "reset") return admin.link.state === "expired" ? "Reset link expired" : "Password reset pending";
  return "Active";
}

export function roleTone(role: string): BadgeTone {
  return role === SUPER_ADMIN ? "accent" : "info";
}

const ACTION_TEXT: Record<string, string> = {
  "platform_admin.invite": "invited",
  "platform_admin.invite_resent": "re-sent the invite to",
  "platform_admin.invite_accepted": "accepted the invite as",
  "platform_admin.password_set": "set a new password as",
  "platform_admin.role_changed": "changed the role of",
  "platform_admin.suspended": "suspended",
  "platform_admin.reactivated": "reactivated",
  "platform_admin.removed": "removed",
  "platform_admin.signed_out": "signed out everywhere",
  "platform_admin.password_reset": "reset the password of",
};

export function describeActivity(e: ActivityEntry, roleLabel: (key: string) => string): string {
  const who = String(e.payload.username ?? e.resourceId.slice(0, 8));
  if (e.action === "platform_admin.sign_in_failed") return `Failed sign-in attempt for ${who}`;
  const verb = ACTION_TEXT[e.action] ?? e.action.replace("platform_admin.", "").replace(/_/g, " ");
  let tail = "";
  if (e.action === "platform_admin.role_changed") {
    tail = ` from ${roleLabel(String(e.payload.from ?? ""))} to ${roleLabel(String(e.payload.to ?? ""))}`;
  } else if (e.action === "platform_admin.invite" && e.payload.role) {
    tail = ` as ${roleLabel(String(e.payload.role))}`;
  }
  return `${e.actor} ${verb} ${who}${tail}`;
}

/** Activity rows worth a second look. */
export function isWarning(e: ActivityEntry): boolean {
  return e.outcome !== "ok" || e.action === "platform_admin.sign_in_failed";
}

/** Absolute link for a one-time invite/reset path. */
export function absoluteLink(path: string): string {
  if (typeof window === "undefined") return path;
  return `${window.location.origin}${path}`;
}
