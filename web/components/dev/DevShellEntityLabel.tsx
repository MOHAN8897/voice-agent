"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { parseTestStudioAgentId } from "@/components/test-studio/TestStudioAgentSidebar";

export function DevShellEntityLabel() {
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
  if (pathname.startsWith("/dev/test-studio")) {
    return "Test Studio · Agent labs";
  }
  return "Platform Control";
}
