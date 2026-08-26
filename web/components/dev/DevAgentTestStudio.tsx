"use client";

import { AgentTestStudio } from "@/components/test-studio/AgentTestStudio";

export function DevAgentTestStudio({ agentId }: { agentId: string }) {
  return <AgentTestStudio agentId={agentId} portal="dev" />;
}
