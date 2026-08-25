import { DevRuntimePanel } from "@/components/dev/DevRuntimePanel";

export default function DevRuntimePage() {
  return (
    <div>
      <p className="mb-6 text-sm text-text-muted">
        Runtime overlays apply to the <span className="font-mono text-accent">dev-studio</span> session — integrate with
        Stack & tiers for full agent configuration.
      </p>
      <DevRuntimePanel />
    </div>
  );
}
