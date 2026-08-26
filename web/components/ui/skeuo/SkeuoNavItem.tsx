"use client";

import Link from "next/link";
import { cn } from "@/lib/cn";

export function SkeuoNavItem({
  href,
  label,
  active,
  icon,
  status,
}: {
  href: string;
  label: string;
  active: boolean;
  icon: React.ReactNode;
  status?: "ok" | "warn" | "error" | "live";
}) {
  return (
    <li>
      <Link
        href={href}
        className={cn(
          "group flex items-center gap-3 rounded-skeuo-sm px-3 py-2.5 text-sm transition-all duration-150",
          active ? "skeuo-nav-active text-text" : "text-text-muted hover:text-text skeuo-nav-idle"
        )}
        aria-current={active ? "page" : undefined}
      >
        <span
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-skeuo-sm border transition-colors",
            active
              ? "border-accent-primary/25 bg-surface-panel-raised text-accent-primary skeuo-inset"
              : "border-transparent bg-transparent text-text-subtle group-hover:border-surface-border-subtle group-hover:bg-surface-panel/50"
          )}
        >
          {icon}
        </span>
        <span className="flex-1 font-medium tracking-tight">{label}</span>
        {status && (
          <span
            className={cn(
              "skeuo-led shrink-0",
              status === "ok" && "skeuo-led-ok",
              status === "warn" && "skeuo-led-warn",
              status === "error" && "skeuo-led-error",
              status === "live" && "skeuo-led-live animate-pulse-soft"
            )}
            aria-hidden
          />
        )}
        {active && (
          <span className="h-4 w-0.5 rounded-full bg-accent-primary/70 shrink-0" aria-hidden />
        )}
      </Link>
    </li>
  );
}
