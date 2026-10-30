"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { cn } from "@/lib/cn";
import { useAdminResource } from "@/lib/useAdminResource";
import type { AccountsTab, ListPage, Summary, Workspace } from "./model";
import { NumberDrawer, UserDrawer, WorkspaceDrawer } from "./Drawers";
import { NumbersView } from "./NumbersView";
import { UsersView } from "./UsersView";
import { WorkspacesView } from "./WorkspacesView";
import type { Filters } from "./useAccountList";

export type ViewProps = {
  scopeTenantId: string;
  scopeName?: string | null;
  initialFilters: Filters;
  onOpen: (kind: "ws" | "user" | "num", id: string) => void;
  onScope: (tab: AccountsTab, tenantId: string) => void;
  refreshToken: number;
  onChanged: () => void;
};

const TABS: Array<{ id: AccountsTab; label: string; help: string }> = [
  { id: "workspaces", label: "Workspaces", help: "Customer accounts: status, plan, wallet, KYC." },
  { id: "users", label: "Users", help: "People who sign in, and their role in each workspace." },
  { id: "numbers", label: "Phone numbers", help: "Every live number: which workspace and agent it belongs to." },
];

/** Filter keys each tab accepts from the URL (so old bookmarks land on the right view). */
const URL_FILTERS: Record<AccountsTab, string[]> = {
  workspaces: ["q", "status", "plan", "kyc", "hasNumbers", "dialCode", "includeDeleted", "includeInventory", "createdFrom", "createdTo"],
  users: ["q", "status", "role", "lastActive", "noWorkspace", "createdFrom", "createdTo"],
  numbers: ["q", "location", "status", "provider", "ownership", "pinned", "dialCode", "purchaseStatus", "createdFrom", "createdTo"],
};

/**
 * One page for workspaces → users → phone numbers. Tabs are three views over the
 * same data; scoping to a workspace narrows Users and Numbers to it; any row opens
 * a drawer with everything about it and every action.
 *
 * URL: ?tab=workspaces|users|numbers & tenantId=<scope> & open=ws:<id>|user:<id>|num:<id>
 */
export function AccountsWorkspace() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const tabParam = params.get("tab") as AccountsTab | null;
  const tab: AccountsTab = tabParam && TABS.some((t) => t.id === tabParam) ? tabParam : "workspaces";
  const scopeTenantId = tab === "workspaces" ? "" : params.get("tenantId") ?? "";
  const open = params.get("open") ?? "";
  const [refreshToken, setRefreshToken] = useState(0);

  const summary = useAdminResource<Summary>("/api/dev/admin/accounts/summary", [refreshToken]);
  const scope = useAdminResource<ListPage<Workspace>>(
    scopeTenantId ? `/api/dev/admin/accounts/workspaces?q=${encodeURIComponent(scopeTenantId)}&includeDeleted=true&includeInventory=true&limit=1` : null,
    [scopeTenantId]
  );
  const scopeName = scope.data?.items.find((w) => w.tenantId === scopeTenantId)?.name ?? null;

  const replace = useCallback(
    (mutate: (p: URLSearchParams) => void) => {
      const next = new URLSearchParams(params.toString());
      mutate(next);
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router]
  );

  const setTab = (id: AccountsTab) =>
    replace((p) => {
      // Filters belong to the tab they were set on.
      for (const key of new Set(Object.values(URL_FILTERS).flat())) p.delete(key);
      p.set("tab", id);
      if (id === "workspaces") p.delete("tenantId");
    });
  const onScope = (id: AccountsTab, tenantId: string) =>
    replace((p) => {
      for (const key of new Set(Object.values(URL_FILTERS).flat())) p.delete(key);
      p.set("tab", id);
      p.set("tenantId", tenantId);
      p.delete("open");
    });
  const clearScope = () => replace((p) => p.delete("tenantId"));
  const onOpen = (kind: "ws" | "user" | "num", id: string) => replace((p) => p.set("open", `${kind}:${id}`));
  const closeDrawer = () => replace((p) => p.delete("open"));
  const onChanged = useCallback(() => setRefreshToken((n) => n + 1), []);

  // Filters set through the URL (bookmarks, redirects, summary tiles). Typing in the
  // filter bar does not touch the URL, so this only changes on navigation.
  const urlFilterKey = URL_FILTERS[tab].map((k) => `${k}=${params.get(k) ?? ""}`).join("&");
  const initialFilters = useMemo(() => {
    const f: Filters = {};
    for (const key of URL_FILTERS[tab]) {
      const v = params.get(key);
      if (v) f[key] = v;
    }
    return f;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, scopeTenantId, urlFilterKey]);

  const [openKind, openId] = open.includes(":") ? (open.split(":", 2) as ["ws" | "user" | "num", string]) : [null, ""];
  const s = summary.data?.workspaces && summary.data.users && summary.data.numbers ? summary.data : null;
  const viewProps: ViewProps = { scopeTenantId, scopeName, initialFilters, onOpen, onScope, refreshToken, onChanged };
  const drawerProps = { id: openId, onClose: closeDrawer, onOpen, onScope, onChanged };

  return (
    <div className="space-y-5 p-6" data-testid="accounts-page">
      <header className="flex flex-col gap-1">
        <p className="label-caps text-accent-primary">Customer operations</p>
        <h1 className="text-2xl font-semibold tracking-tight text-text">Accounts</h1>
        <p className="max-w-3xl text-sm text-text-muted">
          Every workspace, the people in it and the phone numbers it owns — in one place. Click any row for full details and actions; tick rows to act on
          many at once. Every change asks for a reason and is written to the activity log.
        </p>
      </header>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Totals">
        <SummaryTile
          label="Workspaces"
          value={s?.workspaces.total}
          detail={s ? `${s.workspaces.active ?? 0} active · ${s.workspaces.suspended ?? 0} suspended · ${s.workspaces.deleted ?? 0} deleted` : undefined}
          onClick={() => setTab("workspaces")}
        />
        <SummaryTile
          label="Users"
          value={s?.users.total}
          detail={s ? `${s.users.active ?? 0} active · ${(s.users.invited ?? 0) + (s.users.pending_invite ?? 0)} invited · ${s.users.suspended ?? 0} suspended` : undefined}
          onClick={() => setTab("users")}
        />
        <SummaryTile
          label="Phone numbers"
          value={s?.numbers.total}
          detail={s ? `${s.numbers.assigned} in workspaces · ${s.numbers.inventory} in inventory` : undefined}
          onClick={() => setTab("numbers")}
        />
        <SummaryTile
          label="Needs attention"
          value={s ? s.numbers.unpinned + s.kycBlocked : undefined}
          tone={s && s.numbers.unpinned + s.kycBlocked > 0 ? "warn" : undefined}
          detail={s ? `${s.numbers.unpinned} numbers without an agent · ${s.kycBlocked} workspaces blocked by KYC` : undefined}
          onClick={() => replace((p) => {
            for (const key of new Set(Object.values(URL_FILTERS).flat())) p.delete(key);
            p.set("tab", "numbers");
            p.delete("tenantId");
            p.set("pinned", "false");
            p.set("location", "assigned");
          })}
        />
      </section>
      {summary.error && <p className="text-xs text-status-error">{summary.error}</p>}

      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-surface-border-subtle">
        <nav className="flex gap-1" role="tablist" aria-label="Accounts views">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition-colors",
                tab === t.id ? "border-accent-primary text-text" : "border-transparent text-text-muted hover:text-text"
              )}
              data-testid={`accounts-tab-${t.id}`}
            >
              {t.label}
            </button>
          ))}
        </nav>
        <p className="pb-2 text-xs text-text-muted">{TABS.find((t) => t.id === tab)?.help}</p>
      </div>

      {scopeTenantId && (
        <div className="flex flex-wrap items-center gap-2 rounded-skeuo-md border border-accent-primary/30 bg-accent-primary/5 px-3 py-2 text-sm" data-testid="accounts-scope">
          <span className="text-text-muted">Showing {tab === "users" ? "users" : "numbers"} in</span>
          <button type="button" className="font-semibold text-text hover:underline" onClick={() => onOpen("ws", scopeTenantId)}>
            {scopeName ?? (scope.loading ? "…" : scopeTenantId)}
          </button>
          <button type="button" className="ml-auto text-xs text-accent-primary underline" onClick={clearScope}>
            Show all workspaces
          </button>
        </div>
      )}

      <div key={`${tab}:${scopeTenantId}:${urlFilterKey}`}>
        {tab === "workspaces" && <WorkspacesView {...viewProps} />}
        {tab === "users" && <UsersView {...viewProps} />}
        {tab === "numbers" && <NumbersView {...viewProps} />}
      </div>

      {openKind === "ws" && openId && <WorkspaceDrawer key={open} {...drawerProps} />}
      {openKind === "user" && openId && <UserDrawer key={open} {...drawerProps} />}
      {openKind === "num" && openId && <NumberDrawer key={open} {...drawerProps} />}
    </div>
  );
}

function SummaryTile({
  label,
  value,
  detail,
  tone,
  onClick,
}: {
  label: string;
  value: number | undefined;
  detail?: string;
  tone?: "warn";
  onClick: () => void;
}) {
  return (
    <button type="button" onClick={onClick} className="card-surface p-4 text-left transition-colors hover:border-accent-primary/40">
      <p className="text-[11px] uppercase tracking-wider text-text-subtle">{label}</p>
      <p className={cn("mt-1 font-mono text-2xl", tone === "warn" ? "text-status-warning" : "text-text")}>{value ?? "—"}</p>
      {detail && <p className="mt-1 text-xs text-text-muted">{detail}</p>}
    </button>
  );
}
