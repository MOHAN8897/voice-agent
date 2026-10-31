import { redirect } from "next/navigation";

export default async function AgentTestRedirectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/app/test-studio/${id}`);
}
