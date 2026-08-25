import { Panel } from "@/components/console/Panel";

export default function AgentVoicePage() {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {["LOW", "MEDIUM", "PREMIUM"].map((tier) => (
        <Panel key={tier} title={`${tier} tier`}>
          <p className="text-sm text-text-muted">
            STT, LLM, and TTS are resolved on the server for this tier. Business users cannot override the provider
            matrix from the console.
          </p>
        </Panel>
      ))}
      <div className="lg:col-span-3">
        <p className="text-sm text-text-muted">
          Voice tier assignment is managed by your platform administrator. Contact support if you need a tier change.
        </p>
      </div>
    </div>
  );
}
