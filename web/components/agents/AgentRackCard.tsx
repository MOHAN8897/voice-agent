import Link from "next/link";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import { SkeuoButton, SkeuoStatusLight } from "@/components/ui/skeuo";
import { cn } from "@/lib/cn";

export type AgentRackItem = {
  agent_id: string;
  name: string;
  status: string;
  default_tier?: string;
  languages?: string[];
  environment?: string;
  active_compiled_brain_version?: string | null;
};

function healthStatus(status: string): "ok" | "warn" | "idle" {
  if (status === "active") return "ok";
  if (status === "failed" || status === "deploying") return "warn";
  return "idle";
}

export function AgentRackCard({
  agent,
  portal = "app",
}: {
  agent: AgentRackItem;
  portal?: "app" | "dev";
}) {
  const base = portal === "dev" ? `/dev/agents/${agent.agent_id}` : `/app/agents/${agent.agent_id}`;
  const langs = (agent.languages || ["te-IN"]).join(", ");
  const version = agent.active_compiled_brain_version || "—";
  const env = agent.environment || "development";
  const health = healthStatus(agent.status);

  return (
    <li
      className={cn(
        "skeuo-rack-module group relative rounded-skeuo-lg border border-surface-border-subtle skeuo-panel overflow-hidden"
      )}
    >
      {/* Rack rail accents */}
      <div className="absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-border-highlight/20 via-transparent to-transparent" aria-hidden />
      <div className="absolute inset-y-0 right-0 w-1 bg-gradient-to-b from-transparent via-transparent to-border-inset/40" aria-hidden />

      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-subtle">Module</p>
            <h3 className="mt-1 truncate text-lg font-semibold tracking-tight text-text">{agent.name}</h3>
          </div>
          <SkeuoStatusLight
            status={health === "ok" ? "ok" : health === "warn" ? "warn" : "idle"}
            label={agent.status}
          />
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2">
          {[
            ["Language", langs],
            ["Tier", agent.default_tier || "medium"],
            ["Environment", env],
            ["Version", version],
            ["Last call", "—"],
            ["Health", health === "ok" ? "Healthy" : health === "warn" ? "Attention" : "Idle"],
          ].map(([label, value]) => (
            <div key={label} className="skeuo-inset rounded-skeuo-sm px-3 py-2">
              <p className="font-mono text-[9px] uppercase tracking-wider text-text-subtle">{label}</p>
              <p className="mt-0.5 truncate font-mono text-xs text-text">{value}</p>
            </div>
          ))}
        </div>

        <p className="mt-3 font-mono text-[10px] text-text-subtle truncate">{agent.agent_id}</p>

        <div className="mt-5 flex flex-wrap gap-2">
          <Link href={`${base}/summary`}>
            <SkeuoButton variant="primary" size="sm">Open agent</SkeuoButton>
          </Link>
          <Link href={`${base}/test`}>
            <SkeuoButton variant="metal" size="sm">Test</SkeuoButton>
          </Link>
          <SkeuoBadge tone={agent.status === "active" ? "success" : "muted"}>{agent.status}</SkeuoBadge>
        </div>
      </div>
    </li>
  );
}

export function AgentsRack({
  agents,
  portal = "app",
}: {
  agents: AgentRackItem[];
  portal?: "app" | "dev";
}) {
  return (
    <div className="relative mt-8">
      <div className="absolute left-0 top-0 bottom-0 w-px bg-gradient-to-b from-border-highlight/30 via-surface-border-subtle to-transparent" aria-hidden />
      <div className="absolute right-0 top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-surface-border-subtle to-border-inset/50" aria-hidden />
      <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3 pl-1 pr-1">
        {agents.map((a) => (
          <AgentRackCard key={a.agent_id} agent={a} portal={portal} />
        ))}
      </ul>
    </div>
  );
}
