import { redirect } from "next/navigation";

export default function DevAgentTestRedirectPage({ params }: { params: { id: string } }) {
  redirect(`/dev/test-studio/${params.id}`);
}
