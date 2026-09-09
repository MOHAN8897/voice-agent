import { apiGet } from "@/lib/api";
import { formatAgentLanguage } from "@/lib/agent-language";
import { StatCard } from "@/components/console/StatCard";
import { Panel } from "@/components/console/Panel";
import Link from "next/link";

export default async function AgentSummaryPage({ params }: { params: { id: string } }) {
  let agent: Record<string, unknown> = {};
  try {
    const data = await apiGet<{ agent?: Record<string, unknown> }>(`/api/agents/${params.id}`);
    agent = data.agent || {};
  } catch {
    agent = {};
  }

  const langLabel = formatAgentLanguage(agent);

  return (
    <div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Status" value={String(agent.status ?? "—")} tone="ok" />
        <StatCard label="Default tier" value={String(agent.default_tier ?? "medium")} />
        <StatCard label="Language" value={langLabel} />
        <StatCard label="Agent ID" value={params.id.slice(0, 10) + "…"} hint="Locked at call start" />
      </div>
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Panel title="Setup checklist">
          <ol className="space-y-3 text-sm">
            {[
              ["Business Brain", `/app/agents/${params.id}/brain`],
              ["Voice & Models", `/app/agents/${params.id}/voice`],
              ["Test live", `/app/agents/${params.id}/test`],
              ["Versions", `/app/agents/${params.id}/versions`],
            ].map(([label, href], i) => (
              <li key={href} className="flex justify-between">
                <span className="text-text-muted">
                  <span className="mr-2 font-mono text-accent-primary/80">0{i + 1}</span>
                  {label}
                </span>
                <Link href={href} className="text-accent-primary hover:underline">
                  Open
                </Link>
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
