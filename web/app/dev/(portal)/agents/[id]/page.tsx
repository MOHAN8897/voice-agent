import { redirect } from "next/navigation";

export default function DevAgentIndexPage({ params }: { params: { id: string } }) {
  redirect(`/dev/agents/${params.id}/summary`);
}
