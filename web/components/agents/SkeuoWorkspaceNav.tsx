"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AGENT_WORKSPACE_TABS } from "@/lib/constants";
import { SkeuoButton } from "@/components/ui/skeuo";
import { cn } from "@/lib/cn";

const SETUP_STAGES = [
  { slug: "brain", label: "Brain" },
  { slug: "voice", label: "Voice" },
  { slug: "memory-schema", label: "Memory" },
  { slug: "tools", label: "Tools" },
  { slug: "channels", label: "Channels" },
  { slug: "test", label: "Test", externalTestStudio: true },
  { slug: "versions", label: "Deploy" },
] as const;

export function SetupProgressStrip({
  agentId,
  portal = "app",
}: {
  agentId: string;
  portal?: "app" | "dev";
}) {
  const pathname = usePathname();
  const base = portal === "dev" ? `/dev/agents/${agentId}` : `/app/agents/${agentId}`;

  return (
    <div className="mt-4 flex flex-wrap gap-1 rounded-skeuo-md border border-surface-border-subtle skeuo-inset p-1">
      {SETUP_STAGES.map((stage) => {
        const href =
          "externalTestStudio" in stage && stage.externalTestStudio && portal === "dev"
            ? `/dev/test-studio?agent=${agentId}`
            : `${base}/${stage.slug}`;
        const active =
          "externalTestStudio" in stage && stage.externalTestStudio && portal === "dev"
            ? pathname.startsWith("/dev/test-studio")
            : pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link
            key={stage.slug}
            href={href}
            className={cn(
              "rounded-skeuo-sm px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-wider transition-all",
              active
                ? "skeuo-nav-active text-accent-primary border border-accent-primary/20"
                : "text-text-subtle hover:text-text-muted"
            )}
          >
            {stage.label}
          </Link>
        );
      })}
    </div>
  );
}

export function SkeuoWorkspaceNav({
  agentId,
  portal = "app",
}: {
  agentId: string;
  portal?: "app" | "dev";
}) {
  const pathname = usePathname();
  const base = portal === "dev" ? `/dev/agents/${agentId}` : `/app/agents/${agentId}`;

  return (
    <nav className="mb-6 border-b border-surface-border-subtle pb-2" aria-label="Agent workspace">
      <div className="flex flex-wrap gap-1">
        {AGENT_WORKSPACE_TABS.map((tab) => {
          const href = `${base}/${tab.slug}`;
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={tab.slug}
              href={href}
              className={cn(
                "rounded-skeuo-sm px-3 py-2 text-sm font-medium transition-all",
                active
                  ? "skeuo-nav-active text-text border border-surface-border-subtle"
                  : "text-text-muted hover:text-text hover:bg-surface-panel-raised/40"
              )}
            >
              {tab.label}
            </Link>
          );
        })}
        <Link href={`${portal === "dev" ? `/dev/test-studio?agent=${agentId}` : `${base}/test`}`} className="ml-auto">
          <SkeuoButton
            variant={
              (portal === "dev" ? pathname.startsWith("/dev/test-studio") : pathname.endsWith("/test"))
                ? "primary"
                : "metal"
            }
            size="sm"
          >
            Test Studio
          </SkeuoButton>
        </Link>
      </div>
    </nav>
  );
}
