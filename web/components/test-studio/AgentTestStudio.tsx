"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { SessionTraceEvent, TurnCompleteEvent } from "@/components/live/LiveVoiceSession";
import { CallDetailView } from "@/components/calls/CallDetailView";
import { PstnTestPanel } from "@/components/dev/test-studio/PstnTestPanel";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { refreshPortalSession } from "@/lib/auth-client";
import { TestStudioConfigRack } from "@/components/test-studio/TestStudioConfigRack";
import { TestStudioLivePanel } from "@/components/test-studio/TestStudioLivePanel";
import { TestStudioDiagnostics } from "@/components/test-studio/TestStudioDiagnostics";
import { TestStudioFineTuneWorkbench } from "@/components/test-studio/TestStudioFineTuneWorkbench";
import { TestStudioTurnMetrics, type TurnMetricRow } from "@/components/test-studio/TestStudioTurnMetrics";
import { TestStudioMemoryPanel } from "@/components/test-studio/TestStudioMemoryPanel";
import { useStackCatalog } from "@/components/test-studio/useStackCatalog";
import { useTestStudioPrefs } from "@/components/test-studio/useTestStudioPrefs";
import {
  buildStackOverride,
  defaultStackForm,
  TEST_STUDIO_SESSION_ID,
  type StackForm,
  type StackMode,
} from "@/lib/test-studio-stack";
import { cn } from "@/lib/cn";

type ChannelTab = "browser" | "pstn";
type FineTuneTab = "prompts" | "llm" | "voice";
type StudioTab = "live" | "config" | "tune" | "debug";

const STUDIO_TABS: { id: StudioTab; label: string; hint: string }[] = [
  { id: "live", label: "Live", hint: "Mic · transcript · conversation" },
  { id: "config", label: "Config", hint: "Stack · voice · tokens" },
  { id: "tune", label: "Fine-tune", hint: "Prompts · LLM · VAD" },
  { id: "debug", label: "Debug", hint: "Events · memory · review" },
];

export function AgentTestStudio({
  agentId,
  portal = "app",
}: {
  agentId: string;
  portal?: "app" | "dev";
}) {
  const [studioTab, setStudioTab] = useState<StudioTab>("live");
  const [channel, setChannel] = useState<ChannelTab>("browser");
  const [stackMode, setStackMode] = useState<StackMode>(portal === "dev" ? "custom" : "tier");
  const [tier, setTier] = useState("medium");
  const [stack, setStack] = useState<StackForm>(defaultStackForm());
  const [language, setLanguage] = useState("te-IN");
  const [fineTuneTab, setFineTuneTab] = useState<FineTuneTab>("prompts");
  const [runtimeTtsSpeaker, setRuntimeTtsSpeaker] = useState("");
  const { providers, sttModes, sttStreamTypes, loading: catalogLoading, stackForTier, catalog } =
    useStackCatalog(portal);
  const [events, setEvents] = useState<SessionTraceEvent[]>([]);
  const [callId, setCallId] = useState<string | null>(null);
  const [callEnded, setCallEnded] = useState(false);
  const [memoryJson, setMemoryJson] = useState("");
  const [sessionStatus, setSessionStatus] = useState("idle");
  const [locked, setLocked] = useState(false);
  const [turnRows, setTurnRows] = useState<TurnMetricRow[]>([]);
  const [prefsReady, setPrefsReady] = useState(false);

  const sarvamSpeakersV3 = (catalog?.tts as { speakersV3?: string[] } | undefined)?.speakersV3 || [];
  const sarvamSpeakersV2 = (catalog?.tts as { speakersV2?: string[] } | undefined)?.speakersV2 || [];

  const uiPrefs = useMemo(
    () => ({
      studioTab,
      stackMode,
      tier,
      channel,
      language,
      stack: stack as unknown as Record<string, unknown>,
      fineTuneTab,
    }),
    [studioTab, stackMode, tier, channel, language, stack, fineTuneTab]
  );

  useTestStudioPrefs(uiPrefs, (loaded) => {
    if (loaded.studioTab) setStudioTab(loaded.studioTab as StudioTab);
    if (loaded.stackMode) setStackMode(loaded.stackMode);
    if (loaded.tier) setTier(loaded.tier);
    if (loaded.channel) setChannel(loaded.channel);
    if (loaded.language) setLanguage(loaded.language);
    if (loaded.fineTuneTab) setFineTuneTab(loaded.fineTuneTab as FineTuneTab);
    if (loaded.stack && typeof loaded.stack === "object") {
      setStack((prev) => ({ ...prev, ...(loaded.stack as Partial<StackForm>) }));
    }
    setPrefsReady(true);
  });

  useEffect(() => {
    if (!prefsReady) {
      const t = setTimeout(() => setPrefsReady(true), 800);
      return () => clearTimeout(t);
    }
  }, [prefsReady]);

  useEffect(() => {
    fetch(`/api/settings/runtime?sessionId=${encodeURIComponent(TEST_STUDIO_SESSION_ID)}`, {
      credentials: "include",
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        const speaker = String(j?.values?.ttsSpeaker || "");
        if (speaker) {
          setRuntimeTtsSpeaker(speaker);
          setStack((prev) => ({ ...prev, ttsVoiceId: prev.ttsVoiceId || speaker }));
        }
      })
      .catch(() => {});
  }, []);

  const refreshMemory = useCallback(async (id: string) => {
    const r = await fetch(`/api/call/${id}/memory/projection`, { credentials: "include" });
    if (!r.ok) return;
    const j = await r.json();
    setMemoryJson(JSON.stringify(j?.projection || j, null, 2));
  }, []);

  useEffect(() => {
    if (portal === "dev") refreshPortalSession("dev");
    fetch(`/api/agents/${agentId}`, { credentials: "include" })
      .then((r) => r.json())
      .then((j) => {
        if (!prefsReady) return;
        if (j.agent?.default_tier && stackMode === "tier") setTier(j.agent.default_tier);
        const lang = j.agent?.languages?.[0];
        if (lang && !uiPrefs.language) setLanguage(lang);
      });
  }, [agentId, portal, prefsReady, stackMode, uiPrefs.language]);

  useEffect(() => {
    if (stackMode === "tier") {
      const next = stackForTier(tier);
      setStack((prev) => ({
        ...next,
        ttsVoiceId: prev.ttsVoiceId || runtimeTtsSpeaker || next.ttsVoiceId,
      }));
      if (next.language) setLanguage(next.language);
    }
  }, [stackMode, tier, stackForTier, runtimeTtsSpeaker]);

  useEffect(() => {
    if (!callId || callEnded) return;
    const t = setInterval(() => refreshMemory(callId), 4000);
    return () => clearInterval(t);
  }, [callId, callEnded, refreshMemory]);

  const sessionTotals = useMemo(
    () =>
      turnRows.reduce(
        (acc, r) => ({
          input: acc.input + (r.inputTokens ?? 0),
          output: acc.output + (r.outputTokens ?? 0),
          cached: acc.cached + (r.cachedTokens ?? 0),
        }),
        { input: 0, output: 0, cached: 0 }
      ),
    [turnRows]
  );

  function onTrace(event: SessionTraceEvent) {
    setEvents((prev) => [...prev, event]);
  }

  function onTurnComplete(ev: TurnCompleteEvent) {
    const cached = Number(ev.usage?.cached_tokens || 0);
    const input = Number(ev.usage?.input_tokens || 0);
    setTurnRows((prev) => [
      ...prev,
      {
        turn: ev.turn,
        userText: ev.userText,
        assistantText: ev.assistantText,
        at: ev.at,
        inputTokens: input,
        outputTokens: Number(ev.usage?.output_tokens || 0),
        cachedTokens: cached,
        cacheWriteTokens: Number(ev.usage?.cache_write_tokens || 0),
        memoryOps: Array.isArray(ev.memoryUpdate?.operations) ? ev.memoryUpdate.operations.length : 0,
        cacheHit: cached > 0 && input > 0 && cached >= input * 0.5,
      },
    ]);
  }

  function onCallStart(id: string) {
    setCallId(id);
    setCallEnded(false);
    setLocked(true);
    setEvents([]);
    setTurnRows([]);
    refreshMemory(id);
  }

  function onCallEnd(id: string) {
    setCallEnded(true);
    setLocked(false);
    setSessionStatus("ended");
    refreshMemory(id);
  }

  const showPstn = portal === "dev";
  const stackLocked = locked && (sessionStatus === "listening" || sessionStatus === "connecting");
  const stackOverride = useMemo(() => {
    if (stackMode === "custom") return buildStackOverride(stack);
    if (stack.ttsVoiceId) {
      return {
        tts: {
          config: { speaker: stack.ttsVoiceId },
        },
      };
    }
    return undefined;
  }, [stackMode, stack]);

  return (
    <div className="space-y-5">
      <div className="sticky top-0 z-40 -mx-1 rounded-skeuo-lg border border-surface-border-subtle bg-surface/95 px-2 py-3 backdrop-blur supports-[backdrop-filter]:bg-surface/90">
        <div className="flex flex-wrap gap-1 rounded-skeuo-sm border border-surface-border-subtle skeuo-inset p-1">
          {STUDIO_TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setStudioTab(t.id)}
              className={cn(
                "flex-1 min-w-[5.5rem] rounded-skeuo-sm px-3 py-2 text-left transition-colors",
                studioTab === t.id ? "skeuo-btn-primary text-white" : "text-text-muted hover:bg-surface-raised"
              )}
            >
              <span className="block text-xs font-semibold uppercase tracking-wide">{t.label}</span>
              <span
                className={cn(
                  "mt-0.5 block text-[10px] leading-tight",
                  studioTab === t.id ? "text-white/80" : "text-text-subtle"
                )}
              >
                {t.hint}
              </span>
            </button>
          ))}
        </div>
      </div>

      {studioTab === "live" && (
        <div className="grid gap-5 xl:grid-cols-12">
          <div className="xl:col-span-8 min-w-0">
            {channel === "browser" ? (
              <TestStudioLivePanel
                agentId={agentId}
                tier={tier}
                languageCode={language}
                stackOverride={stackOverride}
                sessionId={TEST_STUDIO_SESSION_ID}
                onTrace={onTrace}
                onCallStart={onCallStart}
                onCallEnd={onCallEnd}
                onStatusChange={setSessionStatus}
                onTurnComplete={onTurnComplete}
              />
            ) : (
              <SkeuoPanel title="PSTN · Plivo" description="Register numbers and place test calls" padding="md">
                <PstnTestPanel agentId={agentId} tier={tier} />
              </SkeuoPanel>
            )}
          </div>
          <div className="xl:col-span-4 space-y-5">
            <TestStudioTurnMetrics rows={turnRows} sessionTotal={sessionTotals} />
          </div>
        </div>
      )}

      {studioTab === "config" && (
        <div className="grid gap-5 lg:grid-cols-2">
          <TestStudioConfigRack
            channel={channel}
            onChannelChange={setChannel}
            showPstn={showPstn}
            showCustomStack
            stackMode={stackMode}
            onStackModeChange={(m) => {
              if (m === "custom") setStack(stackForTier(tier));
              setStackMode(m);
            }}
            tier={tier}
            onTierChange={setTier}
            stack={stack}
            onStackChange={setStack}
            providers={providers}
            sttModes={sttModes}
            sttStreamTypes={sttStreamTypes}
            catalogLoading={catalogLoading}
            language={language}
            onLanguageChange={setLanguage}
            sessionStatus={sessionStatus}
            locked={stackLocked}
            sarvamSpeakersV3={sarvamSpeakersV3}
            sarvamSpeakersV2={sarvamSpeakersV2}
            runtimeTtsSpeaker={runtimeTtsSpeaker}
          />
          <TestStudioTurnMetrics rows={turnRows} sessionTotal={sessionTotals} />
        </div>
      )}

      {studioTab === "tune" && (
        <TestStudioFineTuneWorkbench
          agentId={agentId}
          portal={portal}
          language={language}
          locked={stackLocked}
          activeTab={fineTuneTab}
          onTabChange={setFineTuneTab}
          stackTtsProvider={stack.ttsProvider}
          runtimeTtsSpeaker={runtimeTtsSpeaker}
          onRuntimeSpeakerChange={setRuntimeTtsSpeaker}
          sarvamSpeakersV3={sarvamSpeakersV3}
          sarvamSpeakersV2={sarvamSpeakersV2}
        />
      )}

      {studioTab === "debug" && (
        <div className="grid gap-5 lg:grid-cols-2">
          <TestStudioDiagnostics callId={callId} channel={channel} callEnded={callEnded} events={events} />
          <TestStudioMemoryPanel callId={callId} projectionJson={memoryJson} />
          {callId && callEnded && (
            <div className="lg:col-span-2">
              <SkeuoPanel title="Call review" description="Full transcript, memory, and outcome" padding="md">
                <CallDetailView callId={callId} />
              </SkeuoPanel>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
