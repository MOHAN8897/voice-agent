import { Suspense } from "react";
import { AccountsWorkspace } from "@/components/admin/accounts/AccountsWorkspace";

export default function AdminAccountsRoute() {
  return (
    <Suspense fallback={<p className="p-6 text-sm text-text-muted">Loading accounts…</p>}>
      <AccountsWorkspace />
    </Suspense>
  );
}
