import { Panel } from "@/components/console/Panel";

export default function DevAgentChannelsPage() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Panel title="Browser">
        <p className="text-sm text-text-muted">Test Studio microphone with barge-in. Same call lifecycle as PSTN.</p>
      </Panel>
      <Panel title="PSTN · Plivo">
        <p className="text-sm text-text-muted">Configure Plivo in Dev Environment. Numbers and campaigns in Business Integrations.</p>
      </Panel>
    </div>
  );
}
