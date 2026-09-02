import { Panel } from "@/components/console/Panel";

export default function AgentChannelsPage() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Panel title="Browser">
        <p className="text-sm text-text-muted">Test Studio microphone with barge-in. Same call lifecycle as PSTN.</p>
      </Panel>
      <Panel title="PSTN · Exotel">
        <p className="text-sm text-text-muted">Inbound and outbound share ledger, memory, and post-call intelligence. Numbers live under Integrations.</p>
      </Panel>
    </div>
  );
}
