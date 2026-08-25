"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AGENT_WORKSPACE_TABS } from "@/lib/constants";

export function AgentWorkspaceNav({
  agentId,
  portal = "app",
}: {
  agentId: string;
  portal?: "app" | "dev";
}) {
  const pathname = usePathname();
  const base = portal === "dev" ? `/dev/agents/${agentId}` : `/app/agents/${agentId}`;

  return (
    <nav className="mb-6 flex flex-wrap gap-1 border-b border-surface-border-subtle pb-2" aria-label="Agent workspace">
      {AGENT_WORKSPACE_TABS.map((tab) => {
        const href = `${base}/${tab.slug}`;
        const active = pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link
            key={tab.slug}
            href={href}
            className={`rounded-lg px-3 py-1.5 text-sm ${
              active ? "bg-accent-dim text-accent" : "text-text-muted hover:text-text"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
      <Link
        href={`${base}/test`}
        className={`ml-auto rounded-lg px-3 py-1.5 text-sm font-medium ${
          pathname.endsWith("/test") ? "bg-accent text-white" : "text-accent hover:bg-accent-dim"
        }`}
      >
        Test Studio
      </Link>
    </nav>
  );
}
