import { redirect } from "next/navigation";

export default function DevAgentTestPage({ params }: { params: { id: string } }) {
  redirect(`/dev/test-studio?agent=${params.id}`);
}
