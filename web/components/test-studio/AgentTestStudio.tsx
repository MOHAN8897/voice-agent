"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SessionTraceEvent, TurnCompleteEvent } from "@/components/live/LiveVoiceSession";
import { CallDetailView } from "@/components/calls/CallDetailView";
import { PstnTestPanel } from "@/components/dev/test-studio/PstnTestPanel";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { refreshPortalSession } from "@/lib/auth-client";
import { TestStudioConfigRack } from "@/components/test-studio/TestStudioConfigRack";
import { TestStudioLivePanel } from "@/components/test-studio/TestStudioLivePanel";
import { TestStudioDiagnostics } from "@/components/test-studio/TestStudioDiagnostics";
import { TestStudioFineTuneWorkbench } from "@/components/test-studio/TestStudioFineTuneWorkbench";
import { TestStudioTurnMetrics, emptySessionTotals, type TurnMetricRow } from "@/components/test-studio/TestStudioTurnMetrics";
import { TestStudioModePicker, type TestStudioMode } from "@/components/test-studio/TestStudioModePicker";
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
import { applyPstnStackDefaults } from "@/lib/pstn-stack";
import { classifyCacheEvent, type PricingMeta } from "@/lib/usage-cost";
import { billingCharCount } from "@/lib/billing-chars";
import { isCartesiaVoiceId } from "@/lib/voice/tts-config";
import { onTestStudioVoiceSaved } from "@/lib/voice/voice-runtime-events";
import { cn } from "@/lib/cn";

type ChannelTab = TestStudioMode;
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
  const [channel, setChannel] = useState<ChannelTab>("agent");
  const [stackMode, setStackMode] = useState<StackMode>("tier");
  const [tier, setTier] = useState("medium");
  const [stack, setStack] = useState<StackForm>(defaultStackForm());
  const [language, setLanguage] = useState("te-IN");
  const [fineTuneTab, setFineTuneTab] = useState<FineTuneTab>("prompts");
  const [runtimeTtsSpeaker, setRuntimeTtsSpeaker] = useState("");
  const [voiceRuntime, setVoiceRuntime] = useState<{
    sttSilenceMs?: number;
    sttThreshold?: number;
    sttStreamType?: string;
    bargeMinWords?: number;
    bargeRequireVad?: boolean;
  }>({});
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
  const [sessionStartedAt, setSessionStartedAt] = useState<number | null>(null);
  const [sessionEndedAt, setSessionEndedAt] = useState<number | null>(null);
  const prefsHydratedRef = useRef(false);
  const channelTouchedRef = useRef(false);

  const setChannelMode = useCallback((next: ChannelTab) => {
    channelTouchedRef.current = true;
    setChannel(next);
  }, []);

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
    if (prefsHydratedRef.current) return;
    prefsHydratedRef.current = true;
    if (loaded.studioTab) setStudioTab(loaded.studioTab as StudioTab);
    if (loaded.stackMode) setStackMode(loaded.stackMode);
    if (loaded.tier) setTier(loaded.tier);
    if (loaded.channel && !channelTouchedRef.current) {
      const ch = loaded.channel === "browser" ? "agent" : loaded.channel;
      if (ch === "agent" || ch === "pstn") setChannel(ch);
    }
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
        const values = j?.values || {};
        const speaker = String(values.ttsSpeaker || "");
        if (speaker) {
          setRuntimeTtsSpeaker(speaker);
          setStack((prev) => ({ ...prev, ttsVoiceId: speaker }));
        }
        setVoiceRuntime({
          sttSilenceMs: values.sttSilenceMs != null ? Number(values.sttSilenceMs) : undefined,
          sttThreshold: values.sttThreshold != null ? Number(values.sttThreshold) : undefined,
          sttStreamType: values.sttStreamType ? String(values.sttStreamType) : undefined,
          bargeMinWords: values.bargeMinWords != null ? Number(values.bargeMinWords) : undefined,
          bargeRequireVad: values.bargeRequireVad != null ? Boolean(values.bargeRequireVad) : undefined,
        });
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    return onTestStudioVoiceSaved((speaker) => {
      setRuntimeTtsSpeaker(speaker);
      setStack((prev) => ({ ...prev, ttsVoiceId: speaker }));
    });
  }, []);

  const refreshMemory = useCallback(async (id: string) => {
    try {
      const r = await fetch(`/api/call/${id}/memory/projection`, { credentials: "include" });
      if (!r.ok) return;
      const j = await r.json();
      setMemoryJson(JSON.stringify(j?.projection || j, null, 2));
    } catch {
      /* API blip must not crash the live mic session */
    }
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
      })
      .catch(() => {});
  }, [agentId, portal, prefsReady, stackMode, uiPrefs.language]);

  useEffect(() => {
    if (stackMode === "tier") {
      const next = stackForTier(tier);
      setStack((prev) => {
        const inherited = prev.ttsVoiceId || runtimeTtsSpeaker || next.ttsVoiceId;
        const ttsVoiceId =
          next.ttsProvider !== "cartesia" && isCartesiaVoiceId(inherited)
            ? next.ttsVoiceId || ""
            : inherited;
        const merged = { ...next, ttsVoiceId };
        return channel === "pstn" ? applyPstnStackDefaults(merged, language) : merged;
      });
      if (next.language) setLanguage(next.language);
    }
  }, [stackMode, tier, stackForTier, runtimeTtsSpeaker, channel, language]);

  useEffect(() => {
    if (channel !== "pstn") return;
    setStack((prev) => applyPstnStackDefaults(prev, language));
  }, [channel, language]);

  useEffect(() => {
    if (!callId || callEnded) return;
    const t = setInterval(() => refreshMemory(callId), 4000);
    return () => clearInterval(t);
  }, [callId, callEnded, refreshMemory]);

  const pricingMeta = useMemo<PricingMeta | null>(() => {
    if (!catalog) return null;
    const top = catalog as {
      pricing_metadata?: PricingMeta;
      fx_rate_inr?: number;
      providers?: { pricing_metadata?: PricingMeta; fx_rate_inr?: number } | unknown[];
    };
    if (top.pricing_metadata) {
      return { ...top.pricing_metadata, fx_rate_inr: top.fx_rate_inr ?? top.pricing_metadata.fx_rate_inr };
    }
    const nested = top.providers;
    if (nested && !Array.isArray(nested) && nested.pricing_metadata) {
      return { ...nested.pricing_metadata, fx_rate_inr: nested.fx_rate_inr ?? nested.pricing_metadata.fx_rate_inr };
    }
    return null;
  }, [catalog]);

  const sessionDurationMs = useMemo(() => {
    if (!sessionStartedAt) return 0;
    return (sessionEndedAt ?? Date.now()) - sessionStartedAt;
  }, [sessionStartedAt, sessionEndedAt, turnRows, sessionStatus]);

  const sessionTotals = useMemo(
    () =>
      turnRows.reduce(
        (acc, r) => ({
          sttChars: acc.sttChars + (r.sttChars ?? 0),
          sttAudioSec: acc.sttAudioSec + (r.sttAudioSec ?? 0),
          llmInput: acc.llmInput + (r.inputTokens ?? 0),
          llmOutput: acc.llmOutput + (r.outputTokens ?? 0),
          llmCached: acc.llmCached + (r.cachedTokens ?? 0),
          llmCacheWrite: acc.llmCacheWrite + (r.cacheWriteTokens ?? 0),
          ttsChars: acc.ttsChars + (r.ttsChars ?? 0),
          ttsAudioBytes: acc.ttsAudioBytes + (r.ttsAudioBytes ?? 0),
          turns: acc.turns + 1,
        }),
        emptySessionTotals()
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
        micDurationMs: ev.micDurationMs,
        inputTokens: input,
        outputTokens: Number(ev.usage?.output_tokens || 0),
        cachedTokens: cached,
        cacheWriteTokens: Number(ev.usage?.cache_write_tokens || 0),
        sttChars: Number(ev.usage?.stt_chars ?? billingCharCount(ev.userText)),
        sttAudioSec: Number(ev.usage?.stt_audio_sec ?? 0),
        ttsChars: Number(ev.usage?.tts_chars ?? billingCharCount(ev.assistantText)),
        ttsAudioBytes: Number(ev.usage?.tts_audio_bytes ?? 0),
        memoryOps: Array.isArray(ev.memoryUpdate?.operations) ? ev.memoryUpdate.operations.length : 0,
        cacheEvent: classifyCacheEvent(input, cached, Number(ev.usage?.cache_write_tokens || 0)),
        cacheHit: cached > 0,
      },
    ]);
  }

  function onCallStart(id: string) {
    setCallId(id);
    setCallEnded(false);
    setLocked(true);
    setEvents([]);
    setTurnRows([]);
    setSessionStartedAt(Date.now());
    setSessionEndedAt(null);
    refreshMemory(id);
  }

  function onCallEnd(id: string) {
    setCallEnded(true);
    setLocked(false);
    setSessionStatus("ended");
    setSessionEndedAt(Date.now());
    refreshMemory(id);
  }

  const showPstn = portal === "dev";
  const stackLocked = locked && (sessionStatus === "listening" || sessionStatus === "connecting");
  const stackOverride = useMemo(() => {
    const voiceId = stack.ttsVoiceId || runtimeTtsSpeaker;
    if (stackMode === "custom") {
      const form = voiceId ? { ...stack, ttsVoiceId: voiceId } : stack;
      return buildStackOverride(form);
    }
    if (voiceId) {
      if (isCartesiaVoiceId(voiceId) && stack.ttsProvider !== "cartesia") {
        return undefined;
      }
      return {
        tts: {
          config: { speaker: voiceId },
        },
      };
    }
    return undefined;
  }, [stackMode, stack, runtimeTtsSpeaker]);

  const pstnStackOverride = useMemo(() => {
    if (stackMode !== "custom") return undefined;
    const voiceId = stack.ttsVoiceId || runtimeTtsSpeaker;
    const form = applyPstnStackDefaults(
      voiceId ? { ...stack, ttsVoiceId: voiceId } : stack,
      language
    );
    return buildStackOverride(form);
  }, [stackMode, stack, runtimeTtsSpeaker, language]);

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

      <div className={studioTab === "live" ? "space-y-5" : "hidden"}>
          {showPstn && (
            <TestStudioModePicker
              mode={channel}
              onModeChange={setChannelMode}
              locked={stackLocked}
              showPstn={showPstn}
            />
          )}
          <div className="grid gap-5 xl:grid-cols-12">
            <div className="xl:col-span-8 min-w-0">
              {channel === "agent" ? (
                <TestStudioLivePanel
                  agentId={agentId}
                  tier={tier}
                  languageCode={language}
                  stackOverride={stackOverride}
                  sessionId={TEST_STUDIO_SESSION_ID}
                  voiceConfig={voiceRuntime}
                  onTrace={onTrace}
                  onCallStart={onCallStart}
                  onCallEnd={onCallEnd}
                  onStatusChange={setSessionStatus}
                  onTurnComplete={onTurnComplete}
                />
              ) : (
                <SkeuoPanel
                  title="PSTN · Telephony"
                  description="Telnyx L16 @ 16 kHz — same path as validation tests 1–10"
                  padding="md"
                >
                  <PstnTestPanel
                    agentId={agentId}
                    tier={tier}
                    language={language}
                    stackMode={stackMode}
                    stackOverride={pstnStackOverride}
                    onInternalCallStart={onCallStart}
                    onInternalCallEnd={onCallEnd}
                  />
                </SkeuoPanel>
              )}
            </div>
            <div className="xl:col-span-4 space-y-5">
              <TestStudioTurnMetrics
                rows={turnRows}
                sessionTotal={sessionTotals}
                mode={channel}
                ttsProvider={stack.ttsProvider}
                ttsModel={stack.ttsModel}
                sttProvider={stack.sttProvider}
                sttModel={stack.sttModel}
                llmModel={stack.llmModel}
                pricing={pricingMeta}
                sessionDurationMs={sessionDurationMs}
              />
            </div>
          </div>
        </div>

      {studioTab === "config" && (
        <div className="grid gap-5 lg:grid-cols-2">
          <TestStudioConfigRack
            channel={channel}
            onChannelChange={setChannelMode}
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
          <TestStudioTurnMetrics
            rows={turnRows}
            sessionTotal={sessionTotals}
            mode={channel}
            ttsProvider={stack.ttsProvider}
            ttsModel={stack.ttsModel}
            sttProvider={stack.sttProvider}
            sttModel={stack.sttModel}
            llmModel={stack.llmModel}
            pricing={pricingMeta}
            sessionDurationMs={sessionDurationMs}
          />
        </div>
      )}

      <div className={studioTab === "tune" ? "" : "hidden"}>
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
      </div>

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
