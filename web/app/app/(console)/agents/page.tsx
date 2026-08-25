import { apiGet } from "@/lib/api";
import Link from "next/link";
import { PageHeader } from "@/components/console/PageHeader";
import { EmptyState } from "@/components/console/EmptyState";
import { StatusBadge } from "@/components/console/StatusBadge";

export default async function AgentsPage() {
  let agents: Array<{ agent_id: string; name: string; status: string; default_tier?: string }> = [];
  try {
    const data = await apiGet<{ agents?: Array<{ agent_id: string; name: string; status: string; default_tier?: string }> }>(
      "/api/agents"
    );
    agents = data.agents || [];
  } catch {
    agents = [];
  }

  return (
    <div>
      <PageHeader
        eyebrow="Workspace"
        title="Agents"
        description="Each agent has a Business Brain, voice tier, channels, and a version you can promote."
        actions={
          <Link href="/app/test-studio" className="rounded-xl border border-surface-border px-4 py-2.5 text-sm text-text">
            Test Studio
          </Link>
        }
      />

      {agents.length === 0 ? (
        <div className="mt-8">
          <EmptyState
            title="No agents yet"
            body="Seed the default agent from API startup, then open the workspace to edit the Business Brain."
          />
        </div>
      ) : (
        <ul className="mt-8 grid gap-4 md:grid-cols-2">
          {agents.map((a) => (
            <li key={a.agent_id} className="rounded-2xl border border-surface-border-subtle bg-surface-card p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium text-text">{a.name}</p>
                  <p className="mt-1 font-mono text-xs text-text-subtle">{a.agent_id}</p>
                </div>
                <StatusBadge tone={a.status === "active" ? "success" : "muted"}>{a.status}</StatusBadge>
              </div>
              <p className="mt-4 text-xs text-text-muted">Tier {a.default_tier || "medium"}</p>
              <div className="mt-5 flex gap-3">
                <Link href={`/app/agents/${a.agent_id}/summary`} className="text-sm font-medium text-accent hover:underline">
                  Workspace
                </Link>
                <Link href={`/app/agents/${a.agent_id}/test`} className="text-sm text-text-muted hover:text-text">
                  Test
                </Link>
                <Link href={`/app/agents/${a.agent_id}/brain`} className="text-sm text-text-muted hover:text-text">
                  Brain
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
