"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { testStudioAgentPath } from "@/components/test-studio/TestStudioAgentSidebar";

export function TestStudioLegacyAgentRedirect({ portal }: { portal: "app" | "dev" }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const agentFromQuery = searchParams.get("agent");

  useEffect(() => {
    if (agentFromQuery) {
      router.replace(testStudioAgentPath(agentFromQuery, portal));
    }
  }, [agentFromQuery, portal, router]);

  return null;
}
