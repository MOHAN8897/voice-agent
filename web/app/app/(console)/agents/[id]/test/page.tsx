import { redirect } from "next/navigation";

export default function AgentTestRedirectPage({ params }: { params: { id: string } }) {
  redirect(`/app/test-studio/${params.id}`);
}
