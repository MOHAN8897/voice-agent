import Link from "next/link";
import { Panel } from "@/components/console/Panel";

export default function DevAgentChannelsPage({ params }: { params: { id: string } }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <Panel title="Browser">
          <p className="text-sm text-text-muted">
            Live mic test with barge-in, STT partials, brain stream, and TTS playback. Same call ledger as PSTN.
          </p>
          <Link
            href={`/dev/agents/${params.id}/test`}
            className="mt-3 inline-block text-sm font-medium text-accent hover:underline"
          >
            Open Test Studio →
          </Link>
        </Panel>
        <Panel title="PSTN · Exotel">
          <p className="text-sm text-text-muted">
            Configure credentials in Environment. Register ExoPhone, assign inbound routing, and place outbound test calls
            from Test Studio.
          </p>
          <Link
            href={`/dev/agents/${params.id}/test`}
            className="mt-3 inline-block text-sm font-medium text-accent hover:underline"
          >
            PSTN tab in Test Studio →
          </Link>
        </Panel>
      </div>
    </div>
  );
}
