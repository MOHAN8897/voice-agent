import { DevAgentWorkspaceShell } from "@/components/dev/DevAgentWorkspaceShell";

export default function DevAgentLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { id: string };
}) {
  return <DevAgentWorkspaceShell agentId={params.id}>{children}</DevAgentWorkspaceShell>;
}
