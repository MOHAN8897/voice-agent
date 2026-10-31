/**
 * Old admin URLs (/dev/admin/tenants, /dev/admin/users, /dev/admin/numbers) now live
 * on the combined Accounts page. Map their query strings so bookmarks keep working.
 */
export type LegacyAccountsSource = "tenants" | "users" | "numbers";

const PASS_THROUGH = ["q", "status", "plan", "role", "kyc", "location", "pinned", "provider", "ownership", "dialCode"];

export function legacyAccountsUrl(
  source: LegacyAccountsSource,
  searchParams: Record<string, string | string[] | undefined>
): string {
  const first = (key: string) => {
    const v = searchParams[key];
    return Array.isArray(v) ? v[0] : v;
  };
  const out = new URLSearchParams();
  const tenantId = first("tenantId");
  const tab = source === "numbers" ? "numbers" : source === "users" || first("section") === "users" ? "users" : "workspaces";
  out.set("tab", tab);
  if (tenantId) {
    if (tab === "workspaces") out.set("open", `ws:${tenantId}`);
    else out.set("tenantId", tenantId);
  }
  for (const key of PASS_THROUGH) {
    const v = first(key);
    if (v) out.set(key, v);
  }
  return `/dev/admin/accounts?${out.toString()}`;
}
