"use client";

import { usePathname } from "next/navigation";
import { parseTestStudioAgentId } from "@/components/test-studio/TestStudioAgentSidebar";
import { useEffect, useState } from "react";

export function ConsoleShellEntityLabel() {
  const pathname = usePathname();
  const agentId = parseTestStudioAgentId(pathname);
  const [agentName, setAgentName] = useState("");

  useEffect(() => {
    if (!agentId) {
      setAgentName("");
      return;
    }
    fetch(`/api/agents/${agentId}`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => setAgentName(String(j?.agent?.name || "")))
      .catch(() => setAgentName(""));
  }, [agentId]);

  if (agentId) {
    return agentName ? `Test Studio · ${agentName}` : "Test Studio · Agent lab";
  }
  if (pathname.startsWith("/app/test-studio")) {
    return "Test Studio · Agent labs";
  }
  return "Business Console";
}
