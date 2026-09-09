"use client";

import { TestStudioAgentSidebar } from "@/components/test-studio/TestStudioAgentSidebar";

export function TestStudioLayout({
  portal,
  children,
}: {
  portal: "app" | "dev";
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
      <TestStudioAgentSidebar portal={portal} />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
