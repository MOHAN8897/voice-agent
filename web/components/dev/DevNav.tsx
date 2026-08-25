"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const DEV_NAV = [
  { href: "/dev", label: "Overview" },
  { href: "/dev/environment", label: "Environment" },
  { href: "/dev/stack", label: "Stack & tiers" },
  { href: "/dev/runtime", label: "Runtime tuning" },
  { href: "/dev/platform-brain", label: "Platform Brain" },
  { href: "/dev/compiled", label: "Compiled preview" },
  { href: "/dev/providers", label: "Providers" },
  { href: "/dev/agents", label: "Agent studio" },
  { href: "/dev/test-studio", label: "Test Studio" },
  { href: "/dev/benchmarks", label: "Benchmarks" },
  { href: "/dev/promotion", label: "Promotion" },
] as const;

export function DevNav() {
  const pathname = usePathname();
  return (
    <ul className="space-y-0.5">
      {DEV_NAV.map((item) => {
        const active = item.href === "/dev" ? pathname === "/dev" : pathname.startsWith(item.href);
        return (
          <li key={item.href}>
            <Link
              href={item.href}
              className={`block rounded-lg px-3 py-2 text-sm transition-colors ${
                active
                  ? "bg-accent-dim text-accent font-medium"
                  : "text-text-muted hover:bg-surface-raised hover:text-text"
              }`}
            >
              {item.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
