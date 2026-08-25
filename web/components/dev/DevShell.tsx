"use client";

import Link from "next/link";
import { useState } from "react";
import { BrandMark } from "@/components/brand/BrandMark";
import { LogoutButton } from "@/components/auth/LogoutButton";
import { DevNav } from "@/components/dev/DevNav";

export function DevShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="flex min-h-screen bg-surface">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-surface-border-subtle bg-surface-elevated md:flex">
        <div className="border-b border-surface-border-subtle px-4 py-4">
          <BrandMark />
          <p className="mt-2 font-mono text-[10px] uppercase tracking-wider text-accent">Developer Portal</p>
        </div>
        <nav className="flex-1 p-3" aria-label="Developer">
          <DevNav />
        </nav>
        <div className="border-t border-surface-border-subtle p-3 space-y-1">
          <Link
            href="/app"
            className="block rounded-lg px-3 py-2 text-xs text-text-muted hover:bg-surface-raised hover:text-text"
          >
            Business Console
          </Link>
          <LogoutButton kind="dev" redirectTo="/dev/login" variant="ghost" label="Sign out" />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-surface-border-subtle px-4 py-3 md:hidden">
          <BrandMark compact />
          <button
            type="button"
            className="rounded-lg border border-surface-border px-3 py-1.5 text-sm"
            onClick={() => setOpen((v) => !v)}
          >
            Menu
          </button>
        </header>
        {open && (
          <nav className="border-b border-surface-border-subtle p-3 md:hidden">
            <DevNav />
            <div className="mt-3 border-t border-surface-border-subtle pt-3">
              <LogoutButton kind="dev" redirectTo="/dev/login" variant="secondary" />
            </div>
          </nav>
        )}
        <header className="hidden items-center justify-between border-b border-surface-border-subtle px-8 py-3 md:flex">
          <p className="font-mono text-[11px] uppercase tracking-wider text-text-subtle">
            dev → staging → production
          </p>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-accent/30 bg-accent-dim px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-accent">
            <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-dot" />
            platform admin
          </span>
        </header>
        <main className="flex-1 overflow-auto p-5 md:p-8">{children}</main>
      </div>
    </div>
  );
}
