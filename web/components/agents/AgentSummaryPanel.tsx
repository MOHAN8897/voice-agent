"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { StatCard } from "@/components/console/StatCard";
import { Panel } from "@/components/console/Panel";
import { formatAgentLanguage } from "@/lib/agent-language";

export function AgentSummaryPanel({
  agentId,
  basePath,
}: {
  agentId: string;
  basePath: string;
}) {
  const [agent, setAgent] = useState<Record<string, unknown>>({});

  useEffect(() => {
    fetch(`/api/agents/${agentId}`, { credentials: "include" })
      .then((r) => r.json())
      .then((j) => setAgent(j.agent || {}));
  }, [agentId]);

  const langLabel = formatAgentLanguage(agent);

  return (
    <div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Status" value={String(agent.status ?? "—")} tone="ok" />
        <StatCard label="Default tier" value={String(agent.default_tier ?? "medium")} />
        <StatCard label="Language" value={langLabel} />
        <StatCard label="Agent ID" value={agentId.slice(0, 10) + "…"} hint="Locked at call start" />
      </div>
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Panel title="Setup checklist">
          <ol className="space-y-3 text-sm">
            {[
              ["Business Brain", `${basePath}/brain`],
              ["Voice & Models", `${basePath}/voice`],
              ["Test live", `${basePath}/test`],
              ["Versions", `${basePath}/versions`],
            ].map(([label, href], i) => (
              <li key={href} className="flex justify-between">
                <span className="text-text-muted">
                  <span className="mr-2 font-mono text-accent/70">0{i + 1}</span>
                  {label}
                </span>
                <Link href={href} className="text-accent hover:underline">Open</Link>
              </li>
            ))}
          </ol>
        </Panel>
        <Panel title="Deployment">
          <p className="text-sm text-text-muted">
            Drafts stay independent of the active production version. Promotion requires a valid brain, enabled stack,
            language support, and a smoke test.
          </p>
        </Panel>
      </div>
    </div>
  );
}
