"use client";

import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";

export function TestStudioHome({ portal = "app" }: { portal?: "app" | "dev" }) {
  return (
    <div data-testid="test-studio-home">
    <SkeuoPanel
      title="Select an agent lab"
      description="Use the agent list on the left. Each agent has its own brief, language, stack, voice, and runtime — they do not share settings."
      padding="md"
    >
      <ol className="list-decimal space-y-2 pl-5 text-sm text-text-muted">
        <li>Pick an agent from the sidebar (for example Priya).</li>
        <li>Fine-tune the agent brief and stack in that agent&apos;s lab only.</li>
        <li>Use <span className="font-medium text-text">+ Create another agent</span> for a new isolated lab.</li>
      </ol>
      <p className="mt-4 text-xs text-text-subtle">
        Portal: {portal === "dev" ? "Developer" : "Business"} · Settings are stored per agent session on disk.
      </p>
    </SkeuoPanel>
    </div>
  );
}
