"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SessionTraceEvent, TurnCompleteEvent } from "@/components/live/LiveVoiceSession";
import { CallDetailView } from "@/components/calls/CallDetailView";
import { PstnTestPanel } from "@/components/dev/test-studio/PstnTestPanel";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { refreshPortalSession } from "@/lib/auth-client";
import { TestStudioConfigRack } from "@/components/test-studio/TestStudioConfigRack";
import { TestStudioLivePanel } from "@/components/test-studio/TestStudioLivePanel";
import { TestStudioDiagnostics } from "@/components/test-studio/TestStudioDiagnostics";
import { CompileLanguagePicker } from "@/components/test-studio/CompileLanguagePicker";
import { TestStudioFineTuneWorkbench } from "@/components/test-studio/TestStudioFineTuneWorkbench";
import { TestStudioTurnMetrics, emptySessionTotals, type TurnMetricRow } from "@/components/test-studio/TestStudioTurnMetrics";
import { TestStudioModePicker, type TestStudioMode } from "@/components/test-studio/TestStudioModePicker";
import { TestStudioMemoryPanel } from "@/components/test-studio/TestStudioMemoryPanel";
import { useStackCatalog } from "@/components/test-studio/useStackCatalog";
import { useTestStudioPrefs, patchPrefsCache } from "@/components/test-studio/useTestStudioPrefs";
import {
  buildPstnStackOverride,
  buildStackOverride,
  defaultStackForm,
  stackFormEqual,
  testStudioSessionId,
  type StackForm,
  type StackMode,
} from "@/lib/test-studio-stack";
import { applyPstnStackDefaults } from "@/lib/pstn-stack";
import { classifyCacheEvent, type PricingMeta } from "@/lib/usage-cost";
import { billingCharCount } from "@/lib/billing-chars";
import { DEFAULT_CARTESIA_VOICE_ID, ensureTtsVoice, voiceMatchesTtsProvider } from "@/lib/voice/tts-config";
import { onTestStudioVoiceSaved } from "@/lib/voice/voice-runtime-events";
import { cn } from "@/lib/cn";
import Link from "next/link";
import { TestStudioSessionProvider } from "@/components/test-studio/TestStudioSessionContext";
import { normalizeLanguageCode, primaryAgentLanguage } from "@/lib/agent-language";
import { persistAgentCallLanguage } from "@/lib/bootstrap-test-studio-agent";

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
  const sessionId = useMemo(() => testStudioSessionId(agentId), [agentId]);
  const studioHomeHref = portal === "dev" ? "/dev/test-studio" : "/app/test-studio";
  const [agentName, setAgentName] = useState("");
  const [studioTab, setStudioTab] = useState<StudioTab>("live");
  const [channel, setChannel] = useState<ChannelTab>("agent");
  const [stackMode, setStackMode] = useState<StackMode>("tier");
  const [tier, setTier] = useState("medium");
  const [stack, setStack] = useState<StackForm>(defaultStackForm());
  const [language, setLanguage] = useState("te-IN");
  const [fineTuneTab, setFineTuneTab] = useState<FineTuneTab>("prompts");
  const [runtimeTtsSpeaker, setRuntimeTtsSpeaker] = useState("");
  const [runtimeOpenAiModel, setRuntimeOpenAiModel] = useState("");
  const [voiceRuntime, setVoiceRuntime] = useState<{
    sttSilenceMs?: number;
    sttThreshold?: number;
    sttStreamType?: string;
    bargeMinWords?: number;
    bargeRequireVad?: boolean;
    voicePresetId?: string;
    mobileAudioMode?: "handset" | "speakerphone";
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
  const [configSaving, setConfigSaving] = useState(false);
  const [configStatus, setConfigStatus] = useState("");
  const [runtimeRevision, setRuntimeRevision] = useState(0);
  const [sessionStartedAt, setSessionStartedAt] = useState<number | null>(null);
  const [sessionEndedAt, setSessionEndedAt] = useState<number | null>(null);
  const prefsHydratedRef = useRef(false);
  const prefsHadLanguageRef = useRef(false);
  const prefsHadTierRef = useRef(false);
  const languageUserOverrideRef = useRef(false);
  const languageRef = useRef(language);
  languageRef.current = language;
  const scopedAgentRef = useRef<string | null>(null);
  const channelTouchedRef = useRef(false);

  const setChannelMode = useCallback((next: ChannelTab) => {
    channelTouchedRef.current = true;
    setChannel(next);
  }, []);

  const setAgentLanguage = useCallback(
    (next: string) => {
      const lang = normalizeLanguageCode(next);
      languageUserOverrideRef.current = true;
      prefsHadLanguageRef.current = true;
      // Always apply — even if code matches, force UI/stack sync after stale prefs races.
      setLanguage(lang);
      setStack((prev) => {
        const base = { ...prev, language: lang };
        return channel === "pstn" ? applyPstnStackDefaults(base, lang) : base;
      });
      void persistAgentCallLanguage({ agentId, sessionId, language: lang });
    },
    [agentId, sessionId, channel]
  );

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

  const onPrefsLoaded = useCallback((loaded: import("@/components/test-studio/useTestStudioPrefs").TestStudioUiPrefs) => {
    if (prefsHydratedRef.current) return;
    prefsHydratedRef.current = true;
    if (loaded.studioTab) setStudioTab(loaded.studioTab as StudioTab);
    if (loaded.stackMode) setStackMode(loaded.stackMode);
    if (loaded.tier) {
      prefsHadTierRef.current = true;
      setTier(loaded.tier);
    }
    if (loaded.channel && !channelTouchedRef.current) {
      const ch = loaded.channel === "browser" ? "agent" : loaded.channel;
      if (ch === "agent" || ch === "pstn") setChannel(ch);
    }
    // Prefs may be stale vs the agent record — never treat prefs language as final.
    // Agent hydrate (below) is source of truth unless the user already clicked.
    if (loaded.language) {
      prefsHadLanguageRef.current = true;
      if (!languageUserOverrideRef.current) {
        setLanguage(normalizeLanguageCode(loaded.language));
      }
    }
    if (loaded.fineTuneTab) setFineTuneTab(loaded.fineTuneTab as FineTuneTab);
    if (loaded.stack && typeof loaded.stack === "object") {
      setStack((prev) => {
        const next = { ...prev, ...(loaded.stack as Partial<StackForm>) };
        if (languageUserOverrideRef.current) next.language = languageRef.current;
        return next;
      });
    }
    setPrefsReady(true);
  }, []);

  useTestStudioPrefs(sessionId, uiPrefs, onPrefsLoaded);

  async function saveConfig() {
    setConfigSaving(true);
    setConfigStatus("");
    try {
      const response = await fetch("/api/test-studio/prefs", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId, ...uiPrefs, saveConfig: true,
          stackOverride: { ...buildStackOverride(stack), pipeline: "realtime_text" } }),
      });
      if (!response.ok) throw new Error(`Save failed (${response.status})`);
      const saved = await response.json();
      window.dispatchEvent(new CustomEvent("test-studio-runtime-saved", {
        detail: { sessionId, patch: saved.runtimePatch },
      }));
      patchPrefsCache(sessionId, uiPrefs);
      setConfigStatus("Config saved for this agent. New browser and phone calls use these settings.");
    } catch (error) {
      setConfigStatus(error instanceof Error ? error.message : "Save failed. Try again.");
    } finally {
      setConfigSaving(false);
    }
  }

  useEffect(() => {
    if (scopedAgentRef.current === agentId) return;
    const switching = scopedAgentRef.current !== null;
    scopedAgentRef.current = agentId;
    prefsHydratedRef.current = false;
    if (switching) {
      languageUserOverrideRef.current = false;
      prefsHadLanguageRef.current = false;
      prefsHadTierRef.current = false;
      channelTouchedRef.current = false;
    }
    setPrefsReady(false);
  }, [agentId, sessionId]);

  useEffect(() => {
    fetch(`/api/settings/runtime?sessionId=${encodeURIComponent(sessionId)}`, {
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
        const openaiModel = String(values.openaiModel || "");
        if (openaiModel) setRuntimeOpenAiModel(openaiModel);
        setVoiceRuntime({
          sttSilenceMs: values.sttSilenceMs != null ? Number(values.sttSilenceMs) : undefined,
          sttThreshold: values.sttThreshold != null ? Number(values.sttThreshold) : undefined,
          sttStreamType: values.sttStreamType ? String(values.sttStreamType) : undefined,
          bargeMinWords: values.bargeMinWords != null ? Number(values.bargeMinWords) : undefined,
          bargeRequireVad: values.bargeRequireVad != null ? Boolean(values.bargeRequireVad) : undefined,
          voicePresetId: values.voicePresetId ? String(values.voicePresetId) : undefined,
        });
      })
      .catch(() => {});
  }, [sessionId, runtimeRevision]);

  useEffect(() => {
    const refresh = (event: Event) => {
      if ((event as CustomEvent).detail?.sessionId === sessionId) setRuntimeRevision((value) => value + 1);
    };
    window.addEventListener("test-studio-runtime-saved", refresh);
    return () => window.removeEventListener("test-studio-runtime-saved", refresh);
  }, [sessionId]);

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
    if (!prefsReady || languageUserOverrideRef.current) return;
    let cancelled = false;
    void (async () => {
      const agentR = await fetch(`/api/agents/${agentId}`, { credentials: "include" });
      if (cancelled || languageUserOverrideRef.current) return;
      const agent = agentR.ok ? (await agentR.json()).agent : null;
      const lang = primaryAgentLanguage(agent);
      setLanguage(lang);
      setStack((prev) => ({ ...prev, language: lang }));
      // Keep prefs cache aligned with the agent so reload does not flash the wrong language.
      if (lang) patchPrefsCache(sessionId, { language: lang });
    })();
    return () => {
      cancelled = true;
    };
  }, [prefsReady, sessionId, agentId]);

  useEffect(() => {
    if (portal === "dev") refreshPortalSession("dev");
    fetch(`/api/agents/${agentId}`, { credentials: "include" })
      .then((r) => r.json())
      .then((j) => {
        if (j.agent?.name) setAgentName(String(j.agent.name));
        if (!prefsReady) return;
        if (j.agent?.default_tier && stackMode === "tier" && !prefsHadTierRef.current) setTier(j.agent.default_tier);
      })
      .catch(() => {});
  }, [agentId, portal, prefsReady, stackMode]);

  useEffect(() => {
    if (stackMode === "tier") {
      const next = stackForTier(tier);
      setStack((prev) => {
        const inherited = prev.ttsVoiceId || runtimeTtsSpeaker || next.ttsVoiceId;
        const ttsVoiceId = voiceMatchesTtsProvider(next.ttsProvider, inherited)
          ? inherited
          : ensureTtsVoice(next.ttsProvider, inherited, next.ttsModel);
        const merged = { ...next, ttsVoiceId, language };
        const result = channel === "pstn" ? applyPstnStackDefaults(merged, language) : merged;
        return stackFormEqual(result, prev) ? prev : result;
      });
    }
  }, [stackMode, tier, stackForTier, runtimeTtsSpeaker, channel, language]);

  useEffect(() => {
    if (channel !== "pstn") return;
    setStack((prev) => {
      const next = applyPstnStackDefaults(prev, language);
      if (
        next.sttModel === prev.sttModel &&
        next.ttsVoiceId === prev.ttsVoiceId &&
        next.language === prev.language
      ) {
        return prev;
      }
      return next;
    });
  }, [channel, language]);

  useEffect(() => {
    setStack((prev) => {
      const voice = ensureTtsVoice(prev.ttsProvider, prev.ttsVoiceId || runtimeTtsSpeaker, prev.ttsModel);
      if (voice === prev.ttsVoiceId) return prev;
      return { ...prev, ttsVoiceId: voice };
    });
  }, [stack.ttsProvider, stack.ttsModel, runtimeTtsSpeaker]);

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

  const onCallStart = useCallback((id: string) => {
    setCallId(id);
    setCallEnded(false);
    setLocked(true);
    setEvents([]);
    setTurnRows([]);
    setSessionStartedAt(Date.now());
    setSessionEndedAt(null);
    refreshMemory(id);
  }, [refreshMemory]);

  const onCallEnd = useCallback((id: string) => {
    setCallEnded(true);
    setLocked(false);
    setSessionStatus("ended");
    setSessionEndedAt(Date.now());
    refreshMemory(id);
  }, [refreshMemory]);

  const showPstn = portal === "dev";
  const stackLocked =
    locked && Boolean(callId) && !callEnded && (sessionStatus === "listening" || sessionStatus === "connecting");
  const stackOverride = useMemo(() => {
    const voiceId = ensureTtsVoice(
      stack.ttsProvider,
      stack.ttsVoiceId || runtimeTtsSpeaker,
      stack.ttsModel
    );
    if (stackMode === "custom") {
      return buildStackOverride({ ...stack, ttsVoiceId: voiceId });
    }
    return {
      tts: {
        config: { speaker: voiceId },
      },
    };
  }, [stackMode, stack, runtimeTtsSpeaker]);

  const pstnStackOverride = useMemo(() => {
    const voiceId = stack.ttsVoiceId || runtimeTtsSpeaker;
    const form = applyPstnStackDefaults(
      voiceId ? { ...stack, ttsVoiceId: voiceId } : stack,
      language
    );
    return buildPstnStackOverride(form, stackMode);
  }, [stackMode, stack, runtimeTtsSpeaker, language]);

  return (
    <TestStudioSessionProvider agentId={agentId} sessionId={sessionId}>
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Link href={studioHomeHref} className="text-xs font-medium text-text-muted hover:text-text">
            ← All Test Studio agents
          </Link>
          <h2 className="mt-1 text-xl font-semibold tracking-tight text-text">
            {agentName || "Agent"} <span className="text-text-subtle font-normal">· Test Studio</span>
          </h2>
          <p className="mt-0.5 font-mono text-[10px] text-text-subtle truncate max-w-xl">{sessionId}</p>
        </div>
        <CompileLanguagePicker
          compact
          id="studio-call-language"
          value={language}
          disabled={false}
          onChange={setAgentLanguage}
          hint="Only place to change this agent's language — Live, Config, Fine-tune, web, and phone all follow it."
        />
      </div>
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
                  sessionId={sessionId}
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
                    sourceSessionId={sessionId}
                    tier={tier}
                    language={language}
                    stackMode={stackMode}
                    stack={stack}
                    runtimeTtsSpeaker={runtimeTtsSpeaker}
                    runtimeOpenAiModel={runtimeOpenAiModel}
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
          <div className="flex flex-wrap items-center gap-3 lg:col-span-2">
            <SkeuoButton type="button" variant="primary" disabled={stackLocked || !prefsReady || catalogLoading || configSaving} onClick={saveConfig}>
              {configSaving ? "Saving…" : "Save Config"}
            </SkeuoButton>
            <span role="status" className="text-xs text-text-muted">{configStatus}</span>
          </div>
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
            sessionStatus={sessionStatus}
            locked={stackLocked}
            sarvamSpeakersV3={sarvamSpeakersV3}
            sarvamSpeakersV2={sarvamSpeakersV2}
            runtimeTtsSpeaker={runtimeTtsSpeaker}
            defaultCartesiaVoiceId={DEFAULT_CARTESIA_VOICE_ID}
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
    </TestStudioSessionProvider>
  );
}
