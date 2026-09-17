"use client";

import type { TestStudioMode } from "@/components/test-studio/TestStudioModePicker";
import { PstnTestPanel, type PstnPanelSection } from "@/components/dev/test-studio/PstnTestPanel";
import { PstnCallStatusTimeline } from "@/components/dev/test-studio/PstnCallStatusTimeline";
import { PstnContactsPanel } from "@/components/dev/test-studio/PstnContactsPanel";
import { PstnHistoryPanel } from "@/components/dev/test-studio/PstnHistoryPanel";
import type { StackForm, StackMode } from "@/lib/test-studio-stack";
import { portalFetch } from "@/lib/auth-client";
import {
  advanceLifecycle,
  isInternalCallId,
  mapProviderStatus,
  type PstnLifecycleStage,
} from "@/lib/pstn-lifecycle";
import { isRealtimePstnMode } from "@/lib/realtime-voice";
import { useCallback, useEffect, useRef, useState } from "react";

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
  onFarFieldNoiseReductionChange,
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
  onFarFieldNoiseReductionChange?: (enabled: boolean) => void;
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
  const [lifecycleStage, setLifecycleStage] = useState<PstnLifecycleStage>("idle");
  const [placedAt, setPlacedAt] = useState<number | null>(null);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);
  const [internalCallId, setInternalCallId] = useState<string | null>(null);
  const endedNotifiedRef = useRef(false);
  const onInternalCallEndRef = useRef(onInternalCallEnd);
  onInternalCallEndRef.current = onInternalCallEnd;

  const notifyEnded = useCallback((id?: string) => {
    if (endedNotifiedRef.current) return;
    endedNotifiedRef.current = true;
    setLifecycleStage((prev) => advanceLifecycle(prev, "hangup"));
    setHistoryRefreshKey((n) => n + 1);
    if (isInternalCallId(id)) onInternalCallEndRef.current?.(id);
    else onInternalCallEndRef.current?.("");
  }, []);

  useEffect(() => {
    if (!internalCallId || lifecycleStage === "idle" || lifecycleStage === "hangup") return;
    let cancelled = false;
    async function pollFlow() {
      try {
        const response = await portalFetch(
          "dev",
          `/api/dev/telephony/media-flow?call_id=${encodeURIComponent(internalCallId || "")}`,
        );
        if (!response.ok || cancelled) return;
        const body = await response.json();
        const stages = body?.flow?.stages || {};
        const events = body?.flow?.events || [];
        const metrics = body?.flow?.metrics || {};
        const hasComplete =
          Boolean(stages.hangup_complete) ||
          events.some((event: { stage?: string }) => event.stage === "hangup_complete");
        const hasClosing =
          Boolean(stages.hangup_closing) ||
          events.some((event: { stage?: string }) => event.stage === "hangup_closing");
        const talking =
          Number(metrics.inbound_frames || 0) > 0 || Number(metrics.outbound_sent_frames || 0) > 0;
        if (cancelled) return;
        if (hasComplete) {
          notifyEnded(internalCallId || "");
        } else if (hasClosing) {
          setLifecycleStage((prev) => advanceLifecycle(prev, "closing"));
        } else if (talking) {
          setLifecycleStage((prev) => advanceLifecycle(prev, "ongoing"));
        }
      } catch {
        /* live timeline is best-effort */
      }
    }
    void pollFlow();
    const timer = window.setInterval(pollFlow, 700);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [internalCallId, lifecycleStage, notifyEnded]);

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
        onFarFieldNoiseReductionChange={onFarFieldNoiseReductionChange}
        initialToE164={toPhone}
        requestDialTo={requestDialTo}
        hideHistory
        section={panelSection}
        onDialPlaced={() => {
          endedNotifiedRef.current = false;
          setInternalCallId(null);
          setLifecycleStage("placed");
          setPlacedAt(Date.now());
          onDialPlaced?.();
        }}
        onInternalCallStart={(id) => {
          setInternalCallId(id);
          setLifecycleStage((prev) => advanceLifecycle(prev, "lifted"));
          onInternalCallStart?.(id);
        }}
        onInternalCallEnd={(id) => {
          notifyEnded(id);
        }}
        onReviewCall={onReviewCall}
        onActiveCallChange={(call) => {
          if (!call) return;
          const mapped = mapProviderStatus(call.status, {
            hasInternal: isInternalCallId(call.internal_call_id),
            lastEvent: call.last_event,
            ended: Boolean(call.ended),
            mediaFramesIn: Number(call.media_frames_in || 0),
            mediaFramesOut: Number(call.media_frames_out || 0),
          });
          if (mapped === "hangup") {
            notifyEnded(isInternalCallId(call.internal_call_id) ? String(call.internal_call_id) : undefined);
            return;
          }
          setLifecycleStage((prev) => {
            if (prev === "hangup") return "hangup";
            if (prev === "closing" && mapped === "ongoing") return "closing";
            return advanceLifecycle(prev, mapped);
          });
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
