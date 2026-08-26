"use client";

import Link from "next/link";
import { useState } from "react";
import { LogoutButton } from "@/components/auth/LogoutButton";
import { ConsoleNav } from "@/components/console/ConsoleNav";
import { InstrumentSidebar, MobileShellHeader } from "@/components/shell/InstrumentSidebar";
import { ShellTopBar } from "@/components/shell/ShellTopBar";

export function ConsoleShell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  const footer = (
    <>
      <Link
        href="/app/profile"
        className="block rounded-skeuo-sm px-3 py-2 text-text-muted transition-colors hover:bg-surface-panel-raised hover:text-text"
      >
        Profile
      </Link>
      <LogoutButton kind="app" redirectTo="/app/login" variant="ghost" label="Sign out" />
    </>
  );

  return (
    <div className="flex min-h-screen bg-surface-chassis">
      <InstrumentSidebar subtitle="Business Console" nav={<ConsoleNav />} footer={footer} />

      <div className="flex min-w-0 flex-1 flex-col">
        <MobileShellHeader
          open={open}
          onToggle={() => setOpen((v) => !v)}
          nav={<ConsoleNav />}
          footer={footer}
        />

        <ShellTopBar
          productLabel="Voice Agent"
          entityLabel="Business Console"
          environment="development"
          connectionStatus="ok"
          profileHref="/app/profile"
          profileLabel="Account"
        />

        <main className="flex-1 overflow-auto p-5 md:p-8">
          <div className="mx-auto max-w-shell">{children}</div>
        </main>
      </div>
    </div>
  );
}
