import { CallDetailView } from "@/components/calls/CallDetailView";
import Link from "next/link";

export default function CallDetailPage({ params }: { params: { id: string } }) {
  return (
    <div>
      <Link href="/app/calls" className="text-sm text-text-muted hover:text-accent">
        ← Calls
      </Link>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight text-text">Call detail</h1>
      <p className="mt-1 font-mono text-xs text-text-subtle">{params.id}</p>
      <div className="mt-6">
        <CallDetailView callId={params.id} />
      </div>
    </div>
  );
}
