import { AgentWorkspaceNav } from "@/components/agents/AgentWorkspaceNav";
import { apiGet } from "@/lib/api";
import { StatusBadge } from "@/components/console/StatusBadge";

export default async function AgentLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { id: string };
}) {
  let agentName = params.id;
  let status = "";
  try {
    const data = await apiGet<{ agent?: { name?: string; status?: string } }>(`/api/agents/${params.id}`);
    agentName = data.agent?.name || params.id;
    status = data.agent?.status || "";
  } catch {
    /* use id */
  }

  return (
    <div>
      <p className="label-caps text-text-subtle">Agent workspace</p>
      <div className="mt-1 flex flex-wrap items-center gap-3">
        <h1 className="text-3xl font-semibold tracking-tight text-text">{agentName}</h1>
        {status && <StatusBadge tone={status === "active" ? "success" : "muted"}>{status}</StatusBadge>}
      </div>
      <p className="mt-1 font-mono text-xs text-text-subtle">{params.id}</p>
      <div className="mt-6">
        <AgentWorkspaceNav agentId={params.id} />
      </div>
      {children}
    </div>
  );
}
