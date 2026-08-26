"use client";

import { CallInvestigationConsole } from "@/components/calls/CallInvestigationConsole";
import { CallDetailInspectorTabs } from "@/components/calls/CallDetailInspectorTabs";

export function CallDetailView({
  callId,
  variant = "default",
}: {
  callId: string;
  variant?: "default" | "inspector";
}) {
  if (variant === "inspector") {
    return <CallDetailInspectorTabs callId={callId} />;
  }
  return <CallInvestigationConsole callId={callId} />;
}
