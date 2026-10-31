import { redirect } from "next/navigation";
import { legacyAccountsUrl } from "@/lib/adminAccountsRedirect";

/** Moved to the combined Accounts page; kept so bookmarks still work. */
export default async function LegacyTenantsRoute({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  redirect(legacyAccountsUrl("tenants", await searchParams));
}
