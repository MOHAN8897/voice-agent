import { DevAgentWorkspaceShell } from "@/components/dev/DevAgentWorkspaceShell";

export default async function DevAgentLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const resolvedParams = await params;
  return <DevAgentWorkspaceShell agentId={resolvedParams.id}>{children}</DevAgentWorkspaceShell>;
}
