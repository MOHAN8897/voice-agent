"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { SkeuoNavItem } from "@/components/ui/skeuo";
import {
  IconAgents,
  IconBenchmark,
  IconCalls,
  IconChart,
  IconMic,
  IconOverview,
  IconRack,
  IconSettings,
} from "@/components/ui/skeuo/icons";

/**
 * Admin navigation, grouped by what an operator is doing.
 *
 * The previous flat list mixed product work with SaaS operations, so "maintain the
 * product" meant scanning seven unrelated rows. Groups keep each job's pages together.
 */
const ADMIN_GROUPS: Array<{
  label: string;
  items: Array<{ href: string; label: string; icon: ReactNode; live?: boolean }>;
}> = [
  {
    label: "Product",
    items: [
      { href: "/dev/agents", label: "Agents & brain", icon: <IconAgents className="h-4 w-4" /> },
      {
        href: "/dev/saas-phone-stack",
        label: "SaaS phone AI",
        icon: <IconRack className="h-4 w-4" />,
      },
      { href: "/dev/stack", label: "Stack & tiers", icon: <IconChart className="h-4 w-4" /> },
    ],
  },
  {
    label: "Operations",
    items: [
      {
        href: "/dev/test-studio",
        label: "Test Studio",
        icon: <IconMic className="h-4 w-4" />,
        live: true,
      },
      { href: "/dev/benchmarks", label: "Benchmarks", icon: <IconBenchmark className="h-4 w-4" /> },
    ],
  },
  {
    label: "SaaS admin",
    items: [
      {
        href: "/dev/admin",
        label: "Overview",
        icon: <IconOverview className="h-4 w-4" />,
      },
      {
        href: "/dev/admin/users",
        label: "Users",
        icon: <IconAgents className="h-4 w-4" />,
      },
      {
        href: "/dev/admin/tenants",
        label: "Tenants",
        icon: <IconRack className="h-4 w-4" />,
      },
      {
        href: "/dev/admin/numbers",
        label: "Phone numbers",
        icon: <IconCalls className="h-4 w-4" />,
      },
      {
        href: "/dev/admin/billing",
        label: "Wallet & rates",
        icon: <IconChart className="h-4 w-4" />,
      },
      {
        href: "/dev/admin/access",
        label: "Roles & access",
        icon: <IconSettings className="h-4 w-4" />,
      },
    ],
  },
  {
    label: "Platform",
    items: [
      {
        href: "/dev/environment",
        label: "Environment",
        icon: <IconSettings className="h-4 w-4" />,
      },
    ],
  },
];

export function AdminNav() {
  const pathname = usePathname();
  return (
    <div className="space-y-5">
      {ADMIN_GROUPS.map((group) => (
        <div key={group.label}>
          <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-text-subtle">
            {group.label}
          </p>
          <ul className="space-y-1">
            {group.items.map((item) => {
              // "/dev/admin" is a prefix of every admin page, so it must not
              // highlight while a child page is open.
              const active =
                item.href === "/dev/admin"
                  ? pathname === "/dev/admin"
                  : pathname.startsWith(item.href);
              return (
                <SkeuoNavItem
                  key={item.href}
                  href={item.href}
                  label={item.label}
                  active={active}
                  icon={item.icon}
                  status={item.live && active ? "live" : undefined}
                />
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

export function AdminPageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold text-text">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function AdminStat({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "warn" | "good";
}) {
  const toneClass =
    tone === "warn" ? "text-status-warning" : tone === "good" ? "text-status-success" : "text-text";
  return (
    <article className="card-surface p-4">
      <p className="text-[11px] uppercase tracking-wider text-text-subtle">{label}</p>
      <p className={`mt-1 font-mono text-2xl ${toneClass}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-text-muted">{hint}</p>}
    </article>
  );
}

export function AdminError({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div
      role="alert"
      className="rounded-skeuo-md border border-status-error/30 bg-status-error/10 p-4 text-sm text-status-error"
    >
      {error}
    </div>
  );
}

export function AdminLoading({ loading }: { loading: boolean }) {
  if (!loading) return null;
  return (
    <p className="py-8 text-center text-sm text-text-muted" role="status">
      Loading…
    </p>
  );
}

export function AdminBackLink({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className="text-xs text-text-muted underline hover:text-text">
      {label}
    </Link>
  );
}
