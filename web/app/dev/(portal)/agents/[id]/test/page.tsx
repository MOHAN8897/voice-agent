import { redirect } from "next/navigation";

export default async function DevAgentTestRedirectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/dev/test-studio/${id}`);
}
