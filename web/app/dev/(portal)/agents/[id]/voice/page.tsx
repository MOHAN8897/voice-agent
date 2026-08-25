import { Panel } from "@/components/console/Panel";

export default function DevAgentVoicePage() {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {["LOW", "MEDIUM", "PREMIUM"].map((tier) => (
        <Panel key={tier} title={`${tier} tier`}>
          <p className="text-sm text-text-muted">
            Configure stacks in Dev → Stack & tiers. Runtime fine-tune in Dev → Runtime tuning.
          </p>
        </Panel>
      ))}
    </div>
  );
}
