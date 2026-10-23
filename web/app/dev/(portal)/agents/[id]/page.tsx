import { redirect } from "next/navigation";

export default async function DevAgentIndexPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/dev/agents/${id}/summary`);
}
