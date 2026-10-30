"use client";

import Link from "next/link";
import type { ComponentType } from "react";
import { AdminAnalyticsPage } from "@/components/admin/panels/AnalyticsPanel";
import { AdminOverviewPage } from "@/components/admin/panels/OverviewPanel";
import { AdminVerificationPage } from "@/components/admin/panels/VerificationPanel";

export type AdminView = "overview" | "analytics" | "verification";

// "accounts" is its own route (/dev/admin/accounts) — workspaces, users and numbers.
const GROUPS: Array<{ label: string; views: Array<{ id: AdminView | "accounts"; label: string; href: string }> }> = [
  { label: "Workspace", views: [{ id: "overview", label: "Overview", href: "/dev" }] },
  {
    label: "Customer operations",
    views: [{ id: "accounts", label: "Accounts", href: "/dev/admin/accounts" }],
  },
  { label: "Trust", views: [{ id: "verification", label: "Verification", href: "/dev/admin/verification" }] },
  { label: "Insights", views: [{ id: "analytics", label: "Web & analytics", href: "/dev/admin/analytics" }] },
];

const PANELS: Record<AdminView, ComponentType> = {
  overview: AdminOverviewPage,
  analytics: AdminAnalyticsPage,
  verification: AdminVerificationPage,
};

export function AdminWorkspace({ view }: { view: AdminView }) {
  const Panel = PANELS[view] ?? AdminOverviewPage;

  return (
    <div className="space-y-3" data-testid="admin-workspace">
      <header className="px-6 pt-5">
        <h1 className="text-lg font-semibold text-text">Admin workspace</h1>
        <p className="mt-1 text-sm text-text-muted">Manage customers, trust checks, and product activity from one place.</p>
      </header>

      <nav aria-label="Admin sections" className="px-6">
        <div className="flex flex-wrap gap-x-6 gap-y-3 rounded-skeuo-md border border-surface-border-subtle bg-surface-panel p-3">
          {GROUPS.map((group) => (
            <div key={group.label} className="min-w-fit">
              <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-wider text-text-subtle">{group.label}</p>
              <ul className="flex flex-wrap gap-1">
                {group.views.map((item) => {
                  const active = view === item.id;
                  return (
                    <li key={item.id}>
                      <Link
                        href={item.href}
                        aria-current={active ? "page" : undefined}
                        className={`inline-flex min-h-9 items-center rounded-skeuo-sm px-3 text-sm transition-colors ${
                          active
                            ? "bg-accent-primary text-white"
                            : "text-text-muted hover:bg-surface-panel-raised hover:text-text"
                        }`}
                      >
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </nav>
      <Panel />
    </div>
  );
}
