"use client";

import { usePathname } from "next/navigation";
import { TestStudioAgentSidebar, parseTestStudioAgentId } from "@/components/test-studio/TestStudioAgentSidebar";

export function TestStudioLayout({
  portal,
  children,
}: {
  portal: "app" | "dev";
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const agentId = parseTestStudioAgentId(pathname);

  if (agentId) {
    return <div className="min-w-0 w-full">{children}</div>;
  }

  return (
    <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
      <TestStudioAgentSidebar portal={portal} />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
