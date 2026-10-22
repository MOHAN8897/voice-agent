import Link from "next/link";
import { ConsolePage } from "@/components/console/ConsolePage";
import { DevCard } from "@/components/dev/DevCard";

export default function DevAgentVoicePage({ params }: { params: { id: string } }) {
  return (
    <ConsolePage>
      <DevCard delayMs={0}>
        <h2 className="text-base font-semibold text-text">Phone voice stack is universal</h2>
        <p className="mt-2 text-sm text-text-muted">
          Live PSTN and web practice calls use the platform phone AI configured in the dev portal — not per-agent STT/LLM/TTS
          tiers. Subscribers pick speaking voice and language in the Voxly console; you tune the engine once for everyone.
        </p>
        <Link
          href="/dev/saas-phone-stack"
          className="mt-4 inline-block text-sm font-semibold text-accent underline-offset-2 hover:underline"
        >
          Open SaaS phone AI stack →
        </Link>
        <p className="mt-6 font-mono text-[10px] text-text-subtle">Agent id: {params.id}</p>
      </DevCard>
    </ConsolePage>
  );
}
