import { LiveVoiceSession } from "@/components/live/LiveVoiceSession";

export default function AgentTestPage({ params }: { params: { id: string } }) {
  return (
    <div>
      <p className="text-sm text-text-muted">
        Browser channel · configuration locks at start. PSTN tests use the same ledger.
      </p>
      <div className="mt-6 overflow-hidden rounded-2xl border border-surface-border-subtle bg-surface-card p-4 md:p-6">
        <LiveVoiceSession agentId={params.id} />
      </div>
    </div>
  );
}
