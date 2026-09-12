"use client";

import type { TestStudioMode } from "@/components/test-studio/TestStudioModePicker";
import { PstnTestPanel, type PstnPanelSection } from "@/components/dev/test-studio/PstnTestPanel";
import { PstnCallStatusTimeline, mapProviderStatus } from "@/components/dev/test-studio/PstnCallStatusTimeline";
import { PstnContactsPanel } from "@/components/dev/test-studio/PstnContactsPanel";
import { PstnHistoryPanel } from "@/components/dev/test-studio/PstnHistoryPanel";
import type { StackForm, StackMode } from "@/lib/test-studio-stack";
import { isRealtimePstnMode } from "@/lib/realtime-voice";
import { useState } from "react";

const FLOW_LABEL: Record<"pstn" | "pstn_realtime", { title: string; hint: string }> = {
  pstn: {
    title: "Full PSTN flow",
    hint: "Telnyx · STT → Realtime text → TTS",
  },
  pstn_realtime: {
    title: "Realtime PSTN",
    hint: "Telnyx · OpenAI Realtime audio in/out",
  },
};

export type PstnWorkspaceSection = "live" | "setup" | "stack" | "history";

export function PstnFlowWorkspace({
  channel,
  section = "live",
  agentId,
  sourceSessionId,
  tier,
  language,
  stackMode,
  stack,
  runtimeTtsSpeaker,
  runtimeOpenAiModel,
  stackOverride,
  onInternalCallStart,
  onInternalCallEnd,
  onReviewCall,
  onDialPlaced,
  sessionClockMs,
}: {
  channel: TestStudioMode;
  section?: PstnWorkspaceSection;
  agentId: string;
  sourceSessionId: string;
  tier: string;
  language?: string;
  stackMode?: StackMode;
  stack?: StackForm;
  runtimeTtsSpeaker?: string;
  runtimeOpenAiModel?: string;
  stackOverride?: Record<string, unknown>;
  onInternalCallStart?: (callId: string) => void;
  onInternalCallEnd?: (callId: string) => void;
  onReviewCall?: (callId: string) => void;
  onDialPlaced?: () => void;
  sessionClockMs?: number;
}) {
  const flowKey = isRealtimePstnMode(channel) ? "pstn_realtime" : "pstn";
  const flow = FLOW_LABEL[flowKey];
  const [toPhone, setToPhone] = useState("");
  const [requestDialTo, setRequestDialTo] = useState<{ phone: string; nonce: number } | null>(null);
  const [lifecycleStage, setLifecycleStage] = useState<ReturnType<typeof mapProviderStatus>>("idle");
  const [placedAt, setPlacedAt] = useState<number | null>(null);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);

  const panelSection: PstnPanelSection =
    section === "setup" || section === "stack" || section === "live" ? section : "none";

  return (
    <div className="w-full min-w-0 space-y-5" data-testid="pstn-flow-workspace">
      <h3 className="text-lg font-semibold text-text">{flow.title}</h3>
      <p className="text-sm text-text-muted">{flow.hint}</p>

      {section === "live" ? (
        <PstnCallStatusTimeline stage={lifecycleStage} placedAt={placedAt} sessionClockMs={sessionClockMs} />
      ) : null}

      <PstnTestPanel
        agentId={agentId}
        sourceSessionId={sourceSessionId}
        tier={tier}
        language={language}
        stackMode={stackMode}
        stack={stack}
        runtimeTtsSpeaker={runtimeTtsSpeaker}
        runtimeOpenAiModel={runtimeOpenAiModel}
        stackOverride={stackOverride}
        initialToE164={toPhone}
        requestDialTo={requestDialTo}
        hideHistory
        section={panelSection}
        onDialPlaced={() => {
          setLifecycleStage("placed");
          setPlacedAt(Date.now());
          onDialPlaced?.();
        }}
        onInternalCallStart={onInternalCallStart}
        onInternalCallEnd={(id) => {
          setLifecycleStage("hangup");
          setHistoryRefreshKey((n) => n + 1);
          onInternalCallEnd?.(id);
        }}
        onReviewCall={onReviewCall}
        onActiveCallChange={(call) => {
          if (!call) {
            if (lifecycleStage === "ongoing" || lifecycleStage === "lifted" || lifecycleStage === "ringing") {
              setLifecycleStage("hangup");
            }
            return;
          }
          setLifecycleStage(mapProviderStatus(call.status, Boolean(call.internal_call_id)));
        }}
        onToChange={setToPhone}
      />

      {section === "live" ? (
        <PstnContactsPanel
          compact
          seedPhone={toPhone}
          onPickPhone={(phone) => setToPhone(phone)}
          onCallPhone={(phone) => {
            setToPhone(phone);
            setRequestDialTo({ phone, nonce: Date.now() });
          }}
        />
      ) : null}

      {section === "history" ? (
        <PstnHistoryPanel agentId={agentId} onReviewCall={onReviewCall} refreshKey={historyRefreshKey} />
      ) : null}
    </div>
  );
}
