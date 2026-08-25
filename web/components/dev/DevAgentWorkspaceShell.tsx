"use client";

import { useEffect, useState } from "react";
import { AgentWorkspaceNav } from "@/components/agents/AgentWorkspaceNav";
import { StatusBadge } from "@/components/console/StatusBadge";

export function DevAgentWorkspaceShell({
  agentId,
  children,
}: {
  agentId: string;
  children: React.ReactNode;
}) {
  const [agentName, setAgentName] = useState(agentId);
  const [status, setStatus] = useState("");

  useEffect(() => {
    fetch(`/api/agents/${agentId}`, { credentials: "include" })
      .then((r) => r.json())
      .then((j) => {
        setAgentName(j.agent?.name || agentId);
        setStatus(j.agent?.status || "");
      });
  }, [agentId]);

  return (
    <div>
      <p className="label-caps text-text-subtle">Agent studio (dev)</p>
      <div className="mt-1 flex flex-wrap items-center gap-3">
        <h1 className="text-3xl font-semibold tracking-tight text-text">{agentName}</h1>
        {status && <StatusBadge tone={status === "active" ? "success" : "muted"}>{status}</StatusBadge>}
      </div>
      <p className="mt-1 font-mono text-xs text-text-subtle">{agentId}</p>
      <div className="mt-6">
        <AgentWorkspaceNav agentId={agentId} portal="dev" />
      </div>
      {children}
    </div>
  );
}
