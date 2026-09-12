"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { cn } from "@/lib/cn";
import { LogoutButton } from "@/components/auth/LogoutButton";
import { DevNav } from "@/components/dev/DevNav";
import { InstrumentSidebar, MobileShellHeader } from "@/components/shell/InstrumentSidebar";
import { ShellTopBar } from "@/components/shell/ShellTopBar";
import { DevShellEntityLabel } from "@/components/dev/DevShellEntityLabel";

export function DevShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const wideWorkspace = /\/test-studio\/[^/]+/.test(pathname);

  const footer = (
    <>
      <Link
        href="/app"
        className="block rounded-skeuo-sm px-3 py-2 text-text-muted transition-colors hover:bg-surface-panel-raised hover:text-text"
      >
        Business Console
      </Link>
      <LogoutButton kind="dev" redirectTo="/dev/login" variant="ghost" label="Sign out" />
    </>
  );

  return (
    <div className="flex min-h-screen bg-surface-chassis">
      <InstrumentSidebar subtitle="Developer Portal" nav={<DevNav />} footer={footer} />

      <div className="flex min-w-0 flex-1 flex-col">
        <MobileShellHeader open={open} onToggle={() => setOpen((v) => !v)} nav={<DevNav />} footer={footer} />

        <ShellTopBar
          productLabel="Voice Agent"
          entityLabel={<DevShellEntityLabel />}
          environment="development"
          connectionStatus="ok"
          tier="admin"
          profileLabel="Dev session"
        />

        <main className="flex min-h-0 flex-1 overflow-auto p-5 md:p-8">
          <div className={cn("mx-auto w-full", wideWorkspace ? "max-w-none" : "max-w-shell")}>{children}</div>
        </main>
      </div>
    </div>
  );
}
