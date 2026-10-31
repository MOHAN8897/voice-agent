/**
 * Shared types, labels and helpers for the Accounts admin page
 * (workspaces → users → phone numbers over the same data).
 */
import { devFetch } from "@/lib/useAdminResource";

export type AccountsTab = "workspaces" | "users" | "numbers";

export type BadgeTone = "success" | "warning" | "error" | "info" | "muted" | "accent" | "live";

export type Workspace = {
  tenantId: string;
  name: string;
  status: string;
  plan?: string | null;
  billingSource?: string | null;
  createdAt: string | null;
  deletedAt?: string | null;
  scheduledPurgeAt?: string | null;
  walletBalanceUsd: number;
  walletBalanceInr: number;
  walletCurrency: string;
  numberCount: number;
  memberCount: number;
  agentCount: number;
  kyc: "approved" | "in_review" | "declined" | "not_started";
  kycStatus?: string | null;
  callsBlocked?: boolean | null;
  isInventory?: boolean;
};

export type Membership = { tenantId: string; tenantName: string; tenantStatus?: string | null; role: string };

export type AccountUser = {
  userId: string;
  email: string;
  fullName: string;
  status: string;
  emailVerified: boolean;
  createdAt: string | null;
  deletedAt?: string | null;
  lastLoginAt: string | null;
  role: string | null;
  tenantId: string | null;
  tenantName: string | null;
  memberships: Membership[];
};

export type AccountNumber = {
  numberId: string;
  e164: string;
  status: string;
  provider: string;
  customerOwned: boolean;
  inInventory: boolean;
  tenantId: string | null;
  tenantName: string | null;
  tenantStatus: string | null;
  agentId: string | null;
  agentName: string | null;
  purchaseStatus: string | null;
  billingSource: string | null;
  carrierNumberId: string | null;
  telnyxNumberId: string | null;
  inboundEnabled: boolean;
  outboundEnabled: boolean;
  createdAt: string | null;
};

export type ListPage<T> = { items: T[]; total: number; limit: number; offset: number; activeProvider?: string | null };

export type BulkResult = {
  ok: boolean;
  action: string;
  processed: string[];
  skipped: Array<{ id: string; reason: string }>;
  failed: Array<{ id: string; error: string }>;
  counts: { processed: number; skipped: number; failed: number };
  replayed?: boolean;
};

export type Summary = {
  workspaces: Record<string, number>;
  users: Record<string, number>;
  numbers: { total: number; assigned: number; inventory: number; releasePending: number; unpinned: number };
  kycBlocked: number;
};

export const WORKSPACE_STATUSES = ["active", "suspended", "past_due", "quarantined", "cancelled", "deleted"];
export const EDITABLE_WORKSPACE_STATUSES = ["active", "suspended", "past_due", "quarantined", "cancelled"];
export const PLANS = ["starter", "growth", "enterprise", "default", "dev", "platform"];
export const USER_ROLES = ["customer_admin", "voice_engineer", "customer_viewer", "platform_admin"];
export const USER_STATUSES = ["active", "invited", "suspended", "disabled"];
export const NUMBER_STATUSES = ["active", "available", "pending", "suspended", "release_pending"];

/** Country dial codes offered in filters. "+1" covers the US and Canada. */
export const DIAL_CODES: Array<{ code: string; label: string }> = [
  { code: "91", label: "India (+91)" },
  { code: "1", label: "US / Canada (+1)" },
  { code: "44", label: "United Kingdom (+44)" },
  { code: "971", label: "UAE (+971)" },
  { code: "65", label: "Singapore (+65)" },
  { code: "61", label: "Australia (+61)" },
];

export const ROLE_LABEL: Record<string, string> = {
  customer_admin: "Admin",
  voice_engineer: "Voice engineer",
  customer_viewer: "Viewer",
  platform_admin: "Platform admin",
};

export const KYC_LABEL: Record<Workspace["kyc"], string> = {
  approved: "KYC approved",
  in_review: "KYC in review",
  declined: "KYC declined",
  not_started: "No KYC",
};

export function workspaceTone(status: string): BadgeTone {
  if (status === "active") return "success";
  if (status === "past_due") return "warning";
  if (status === "suspended" || status === "quarantined") return "error";
  return "muted";
}

export function userTone(status: string): BadgeTone {
  if (status === "active") return "success";
  if (status === "invited" || status === "pending_invite") return "warning";
  if (status === "suspended" || status === "disabled") return "error";
  return "muted";
}

export function numberTone(status: string): BadgeTone {
  if (status === "active") return "success";
  if (status === "available") return "info";
  if (status === "release_pending" || status === "pending") return "warning";
  if (status === "suspended") return "error";
  return "muted";
}

export function kycTone(kyc: Workspace["kyc"]): BadgeTone {
  return kyc === "approved" ? "success" : kyc === "in_review" ? "warning" : kyc === "declined" ? "error" : "muted";
}

export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  return value.replace(/_/g, " ");
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "Never";
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return "—";
  const diff = Date.now() - then;
  const day = 86_400_000;
  if (diff < 60_000) return "Just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} min ago`;
  if (diff < day) return `${Math.floor(diff / 3_600_000)} h ago`;
  if (diff < 30 * day) return `${Math.floor(diff / day)} d ago`;
  return new Date(iso).toLocaleDateString();
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isFinite(d.getTime()) ? d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "—";
}

export function money(usd: number | null | undefined): string {
  return `$${Number(usd ?? 0).toFixed(2)}`;
}

/** Build a query string from a filter object, dropping empty values. */
export function toQuery(params: Record<string, string | number | boolean | null | undefined>): string {
  const p = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "" || value === false) continue;
    p.set(key, String(value));
  }
  return p.toString();
}

export const ENDPOINTS: Record<AccountsTab, string> = {
  workspaces: "/api/dev/admin/accounts/workspaces",
  users: "/api/dev/admin/accounts/users",
  numbers: "/api/dev/admin/accounts/numbers",
};

/** Every id matching the current filters ("select all matching"). */
export async function fetchMatchingIds(
  tab: AccountsTab,
  filters: Record<string, string | number | boolean | null | undefined>
): Promise<{ ids: string[]; total: number; truncated: boolean }> {
  const qs = toQuery({ ...filters, idsOnly: true, limit: undefined, offset: undefined });
  return (await devFetch(`${ENDPOINTS[tab]}?${qs}`)) as { ids: string[]; total: number; truncated: boolean };
}

/** Load every matching row, page by page, for CSV export. */
export async function fetchAllRows<T>(
  tab: AccountsTab,
  filters: Record<string, string | number | boolean | null | undefined>,
  cap = 10_000
): Promise<T[]> {
  const out: T[] = [];
  for (let offset = 0; offset < cap; offset += 200) {
    const qs = toQuery({ ...filters, limit: 200, offset });
    const page = (await devFetch(`${ENDPOINTS[tab]}?${qs}`)) as ListPage<T>;
    out.push(...page.items);
    if (page.items.length < 200 || out.length >= page.total) break;
  }
  return out;
}

/**
 * Run a bulk action in chunks of 500, merging the per-item results.
 *
 * The operator types one phrase for the whole selection; the server checks the
 * phrase per request, so each chunk carries the phrase for its own size.
 */
export async function runBulk(
  tab: AccountsTab,
  ids: string[],
  payload: Record<string, unknown>,
  destructive = false
): Promise<BulkResult> {
  const merged: BulkResult = {
    ok: true,
    action: String(payload.action ?? ""),
    processed: [],
    skipped: [],
    failed: [],
    counts: { processed: 0, skipped: 0, failed: 0 },
  };
  for (let i = 0; i < ids.length; i += 500) {
    const chunk = ids.slice(i, i + 500);
    const key = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${i}`;
    const res = (await devFetch(`${ENDPOINTS[tab]}/bulk`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...payload,
        ids: chunk,
        idempotencyKey: key,
        ...(destructive ? { confirm: confirmPhrase(String(payload.action ?? ""), chunk.length) } : {}),
      }),
    })) as BulkResult;
    merged.processed.push(...res.processed);
    merged.skipped.push(...res.skipped);
    merged.failed.push(...res.failed);
  }
  merged.counts = { processed: merged.processed.length, skipped: merged.skipped.length, failed: merged.failed.length };
  merged.ok = merged.failed.length === 0;
  return merged;
}

/** The phrase the server expects for a destructive bulk action. */
export function confirmPhrase(action: string, count: number): string {
  return `${action.toUpperCase().replace(/_/g, " ")} ${count}`;
}

export function downloadCsv(filename: string, header: string[], rows: Array<Array<string | number | boolean | null | undefined>>) {
  const escape = (v: string | number | boolean | null | undefined) => {
    const s = v === null || v === undefined ? "" : String(v);
    // Neutralise spreadsheet formula injection.
    const safe = /^[=+\-@]/.test(s) && !/^[+-]?\d/.test(s) ? `'${s}` : s;
    return /[",\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
  };
  const text = [header, ...rows].map((r) => r.map(escape).join(",")).join("\n");
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
