"use client";

import { useEffect, useState } from "react";
import { AgentsRack, type AgentRackItem } from "@/components/agents/AgentRackCard";

export function DevAgentsGrid() {
  const [agents, setAgents] = useState<AgentRackItem[]>([]);

  useEffect(() => {
    fetch("/api/agents", { credentials: "include" })
      .then((r) => r.json())
      .then((j) => setAgents(j.agents || []));
  }, []);

  if (agents.length === 0) {
    return <p className="text-sm text-text-muted">No agents loaded.</p>;
  }

  return <AgentsRack agents={agents} portal="dev" />;
}
