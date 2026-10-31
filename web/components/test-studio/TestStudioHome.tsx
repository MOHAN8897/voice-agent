"use client";

import Link from "next/link";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { testStudioNewAgentPath } from "@/components/test-studio/TestStudioAgentSidebar";

export function TestStudioHome({ portal = "app" }: { portal?: "app" | "dev" }) {
  return (
    <div data-testid="test-studio-home">
    <SkeuoPanel
      title="Select an agent lab"
      description="Use the agent list on the left. Each agent has its own brief, language, stack, voice, and runtime — they do not share settings."
      padding="md"
    >
      <p className="mb-4 text-sm">
        <Link
          href={testStudioNewAgentPath(portal)}
          className="font-medium text-accent-primary hover:underline"
        >
          Create new agent from brief →
        </Link>
      </p>
      <ol className="list-decimal space-y-2 pl-5 text-sm text-text-muted">
        <li>Pick an agent from the sidebar, or use the brief-first creator above.</li>
        <li>Fine-tune extracted entity tags and the calling script in that agent&apos;s lab only.</li>
        <li>Use <span className="font-medium text-text">Quick create</span> in the sidebar for an empty lab.</li>
      </ol>
      <p className="mt-4 text-xs text-text-subtle">
        Portal: {portal === "dev" ? "Developer" : "Business"} · Settings are stored per agent session on disk.
      </p>
    </SkeuoPanel>
    </div>
  );
}
