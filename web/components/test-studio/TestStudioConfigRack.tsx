"use client";

import { useState } from "react";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import { CartesiaVoiceSelect } from "@/components/test-studio/CartesiaVoiceSelect";
import { SarvamVoiceSelect } from "@/components/test-studio/SarvamVoiceSelect";
import { TIER_META, TIER_ORDER, type TierName } from "@/lib/voice-tier-meta";
import {
  modelsFor,
  type ProviderEntry,
  type StackForm,
  type StackMode,
} from "@/lib/test-studio-stack";
import {
  applyPstnStackDefaults,
  defaultPstnSttModel,
  sttModelsForPstn,
} from "@/lib/pstn-stack";
import { cn } from "@/lib/cn";
import { StudioTabRail } from "@/components/test-studio/StudioTabRail";
import { defaultTtsVoice, ensureTtsVoice, ttsProviderFromStack } from "@/lib/voice/tts-config";
import type { TestStudioMode } from "@/components/test-studio/TestStudioModePicker";
import {
  DEFAULT_REALTIME_NOISE_REDUCTION,
  DEFAULT_REALTIME_TURN_DETECTION,
  DEFAULT_REALTIME_VAD_EAGERNESS,
  DEFAULT_REALTIME_VOICE,
  REALTIME_NOISE_REDUCTION,
  REALTIME_TURN_DETECTION,
  REALTIME_VAD_EAGERNESS,
  REALTIME_VOICES,
  isRealtimePstnMode,
  normalizeRealtimeSpeed,
  normalizeRealtimeSilenceMs,
} from "@/lib/realtime-voice";

type ChannelTab = TestStudioMode;
type RackTab = "channel" | "stack" | "voice" | "advanced";

function StageSelect({
  label,
  provider,
  model,
  providers,
  stage,
  disabled,
  modelOptions,
  onProviderChange,
  onModelChange,
}: {
  label: string;
  provider: string;
  model: string;
  providers: ProviderEntry[];
  stage: "stt" | "llm" | "tts";
  disabled?: boolean;
  modelOptions?: { id: string; label?: string }[];
  onProviderChange: (provider: string, model: string) => void;
  onModelChange: (model: string) => void;
}) {
  const options = providers.filter((p) => (p.models?.[stage]?.length ?? 0) > 0);
  const modelOpts = modelOptions ?? modelsFor(providers, provider, stage);

  return (
    <div className="space-y-2 rounded-skeuo-sm border border-surface-border-subtle skeuo-inset p-3">
      <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">{label}</p>
      <select
        disabled={disabled}
        className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-2.5 py-2 text-xs disabled:opacity-50"
        value={provider}
        onChange={(e) => {
          const next = e.target.value;
          const first = modelsFor(providers, next, stage)[0]?.id || model;
          onProviderChange(next, first);
        }}
      >
        {options.map((p) => (
          <option key={p.id} value={p.id}>
            {p.label || p.id}
            {!p.configured ? " (no key)" : ""}
          </option>
        ))}
      </select>
      <select
        disabled={disabled}
        className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-2.5 py-2 text-xs disabled:opacity-50"
        value={model}
        onChange={(e) => onModelChange(e.target.value)}
      >
        {modelOpts.map((m) => (
          <option key={m.id} value={m.id}>
            {m.label || m.id}
          </option>
        ))}
      </select>
    </div>
  );
}

export function TestStudioConfigRack({
  channel,
  onChannelChange,
  showPstn,
  showCustomStack = false,
  stackMode,
  onStackModeChange,
  tier,
  onTierChange,
  stack,
  onStackChange,
  providers,
  sttModes,
  sttStreamTypes,
  catalogLoading,
  language,
  sessionStatus,
  locked,
  sarvamSpeakersV3 = [],
  sarvamSpeakersV2 = [],
  runtimeTtsSpeaker = "",
  defaultCartesiaVoiceId,
}: {
  channel: ChannelTab;
  onChannelChange: (c: ChannelTab) => void;
  showPstn?: boolean;
  showCustomStack?: boolean;
  stackMode: StackMode;
  onStackModeChange: (m: StackMode) => void;
  tier: string;
  onTierChange: (t: string) => void;
  stack: StackForm;
  onStackChange: (s: StackForm) => void;
  providers: ProviderEntry[];
  sttModes: string[];
  sttStreamTypes: string[];
  catalogLoading?: boolean;
  language: string;
  sessionStatus: string;
  locked: boolean;
  sarvamSpeakersV3?: string[];
  sarvamSpeakersV2?: string[];
  runtimeTtsSpeaker?: string;
  defaultCartesiaVoiceId?: string;
}) {
  const tierKey = (tier.toLowerCase() as TierName) in TIER_META ? (tier.toLowerCase() as TierName) : "medium";
  const [rackTab, setRackTab] = useState<RackTab>("channel");
  const effectiveTtsProvider = stack.ttsProvider || "sarvam";
  const voiceValue = ensureTtsVoice(
    effectiveTtsProvider,
    stack.ttsVoiceId || runtimeTtsSpeaker,
    stack.ttsModel
  );
  const pstnSttModels =
    channel === "pstn"
      ? sttModelsForPstn(providers, stack.sttProvider, language)
      : undefined;
  const realtime = isRealtimePstnMode(channel);
  const rackTabs: { id: RackTab; label: string }[] = [
    { id: "channel", label: "Channel" },
    { id: "stack", label: "Stack" },
    { id: "voice", label: "Voice" },
    { id: "advanced", label: realtime ? "VAD" : "STT" },
  ];

  function patchStack(patch: Partial<StackForm>) {
    const next = { ...stack, ...patch };
    const ttsVoiceId = ensureTtsVoice(next.ttsProvider, next.ttsVoiceId, next.ttsModel);
    const withVoice = ttsVoiceId === next.ttsVoiceId ? next : { ...next, ttsVoiceId };
    onStackChange(channel === "pstn" ? applyPstnStackDefaults(withVoice, language) : withVoice);
  }

  return (
    <SkeuoPanel title="Configuration" description="Channel · stack · voice · STT" padding="md">
      <div className="mb-4">
        <StudioTabRail
          tone="child"
          ariaLabel="Configuration section"
          items={rackTabs}
          value={rackTab}
          onChange={setRackTab}
          locked={locked}
        />
      </div>

      <div className="space-y-4">
        {rackTab === "channel" && (
          <>
            <div className="flex flex-wrap gap-2">
              {(["agent", ...(showPstn ? ["pstn", "pstn_realtime"] : [])] as ChannelTab[]).map((c) => (
                <button
                  key={c}
                  type="button"
                  data-testid={`config-channel-${c}`}
                  onClick={() => onChannelChange(c)}
                  disabled={locked}
                  className={cn(
                    "rounded-skeuo-sm px-3 py-2 text-xs font-semibold uppercase tracking-wider transition-all",
                    channel === c ? "skeuo-btn-primary text-white" : "skeuo-btn-secondary",
                    locked && "opacity-50"
                  )}
                >
                  {c === "agent"
                    ? "Agent only · mic"
                    : c === "pstn_realtime"
                      ? "Realtime PSTN · audio"
                      : "Full PSTN · phone"}
                </button>
              ))}
            </div>
            <p className="text-xs text-text-muted">
              Agent only tests STT, brain, TTS, and memory without telephony. Full PSTN keeps the current duplex
              stack. Realtime PSTN uses Telnyx plus OpenAI Realtime mini audio-to-audio with the same compiled brain.
            </p>
            {channel === "pstn" && (
              <p className="rounded-skeuo-sm border border-accent/25 bg-accent/5 px-3 py-2 text-[11px] text-text-muted">
                PSTN requires realtime STT (<span className="font-mono">saaras:v3-realtime</span> or Cartesia{" "}
                <span className="font-mono">ink-whisper</span>). TTS voice must match provider (Sarvam name vs
                Cartesia UUID).
              </p>
            )}
            {realtime && (
              <p className="rounded-skeuo-sm border border-accent/25 bg-accent/5 px-3 py-2 text-[11px] text-text-muted">
                Realtime PSTN skips Sarvam STT/TTS. Configure OpenAI voice and VAD on the Voice / VAD tabs. The
                compiled agent brain is unchanged.
              </p>
            )}
          </>
        )}

        {rackTab === "stack" && (
          <>
            {showCustomStack && (
              <div className="space-y-2">
                <span className="text-xs text-text-muted">Stack resolution</span>
                <div className="flex gap-1 rounded-skeuo-sm border border-surface-border-subtle skeuo-inset p-1">
                  {(["tier", "custom"] as StackMode[]).map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      disabled={locked}
                      onClick={() => onStackModeChange(mode)}
                      className={cn(
                        "flex-1 rounded-skeuo-sm px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wide",
                        stackMode === mode ? "skeuo-btn-primary text-white" : "text-text-muted hover:text-text",
                        locked && "opacity-50"
                      )}
                    >
                      {mode === "tier" ? "Tier preset" : "Custom stack"}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {stackMode === "tier" || !showCustomStack ? (
              <div className="space-y-3">
              <label className="block text-sm">
                <span className="text-text-muted">Tier</span>
                <select
                  disabled={locked}
                  className="mt-2 w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm disabled:opacity-50"
                  value={tier}
                  onChange={(e) => onTierChange(e.target.value)}
                >
                  {TIER_ORDER.map((t) => (
                    <option key={t} value={t}>
                      {TIER_META[t].label} — {TIER_META[t].description}
                    </option>
                  ))}
                </select>
                <p className="mt-1.5 text-[11px] text-text-subtle">{TIER_META[tierKey].description}</p>
                {channel === "pstn" && (
                  <p className="mt-2 text-[11px] text-text-subtle">
                    Tier preset uses env-resolved stack (same as{" "}
                    <span className="font-mono">run_test5_outbound_phone.py</span>). Switch to Custom stack to
                    override STT/TTS for PSTN dial.
                  </p>
                )}
                {realtime && (
                  <p className="mt-2 text-[11px] text-text-subtle">
                    Realtime PSTN ignores STT/TTS providers. Live model is OpenAI Realtime mini unless you pick
                    another Realtime slug below.
                  </p>
                )}
              </label>
              {realtime && (
                <StageSelect
                  label="Realtime LLM"
                  stage="llm"
                  providers={providers}
                  provider="openai"
                  model={stack.llmModel.startsWith("gpt-realtime") ? stack.llmModel : "gpt-realtime-2.1-mini"}
                  disabled={locked}
                  modelOptions={
                    modelsFor(providers, "openai", "llm").filter((m) => m.id.startsWith("gpt-realtime")).length
                      ? modelsFor(providers, "openai", "llm").filter((m) => m.id.startsWith("gpt-realtime"))
                      : [
                          { id: "gpt-realtime-2.1-mini", label: "gpt-realtime-2.1-mini" },
                          { id: "gpt-realtime-2.1", label: "gpt-realtime-2.1" },
                        ]
                  }
                  onProviderChange={(_p, llmModel) => patchStack({ llmProvider: "openai", llmModel })}
                  onModelChange={(llmModel) => patchStack({ llmProvider: "openai", llmModel })}
                />
              )}
              </div>
            ) : catalogLoading ? (
              <p className="text-xs text-text-muted">Loading providers…</p>
            ) : providers.length === 0 ? (
              <p className="text-xs text-status-warning">No providers in catalog. Check Environment keys.</p>
            ) : realtime ? (
              <div className="space-y-3">
                <StageSelect
                  label="Realtime LLM"
                  stage="llm"
                  providers={providers}
                  provider="openai"
                  model={stack.llmModel.startsWith("gpt-realtime") ? stack.llmModel : "gpt-realtime-2.1-mini"}
                  disabled={locked}
                  modelOptions={modelsFor(providers, "openai", "llm").filter((m) =>
                    m.id.startsWith("gpt-realtime")
                  )}
                  onProviderChange={(_p, llmModel) => patchStack({ llmProvider: "openai", llmModel })}
                  onModelChange={(llmModel) => patchStack({ llmProvider: "openai", llmModel })}
                />
                <p className="text-[11px] text-text-subtle">
                  Audio in and audio out stay on this model. Sarvam STT/TTS are not used.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                <StageSelect
                  label="STT"
                  stage="stt"
                  providers={providers}
                  provider={stack.sttProvider}
                  model={stack.sttModel}
                  disabled={locked}
                  modelOptions={pstnSttModels}
                  onProviderChange={(sttProvider, sttModel) => {
                    const first =
                      channel === "pstn"
                        ? defaultPstnSttModel(sttProvider, language)
                        : modelsFor(providers, sttProvider, "stt")[0]?.id || sttModel;
                    patchStack({ sttProvider, sttModel: first });
                  }}
                  onModelChange={(sttModel) => patchStack({ sttModel })}
                />
                <StageSelect
                  label="LLM"
                  stage="llm"
                  providers={providers}
                  provider={stack.llmProvider}
                  model={stack.llmModel}
                  disabled={locked}
                  onProviderChange={(llmProvider, llmModel) => patchStack({ llmProvider, llmModel })}
                  onModelChange={(llmModel) => patchStack({ llmModel })}
                />
                <StageSelect
                  label="TTS"
                  stage="tts"
                  providers={providers}
                  provider={stack.ttsProvider}
                  model={stack.ttsModel}
                  disabled={locked}
                  onProviderChange={(ttsProvider, ttsModel) => {
                    patchStack({
                      ttsProvider,
                      ttsModel,
                      ttsVoiceId: defaultTtsVoice(ttsProviderFromStack(ttsProvider, ttsModel)),
                    });
                  }}
                  onModelChange={(ttsModel) => patchStack({ ttsModel })}
                />
                {channel === "pstn" && stackMode === "custom" && (
                  <p className="text-[11px] text-text-subtle">
                    Custom PSTN stack is validated before dial. Invalid combos return an error instead of a silent
                    call.
                  </p>
                )}
                {!catalogLoading && (
                  <div className="skeuo-inset rounded-skeuo-sm p-2.5">
                    <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Resolved preview</p>
                    <p className="mt-1 font-mono text-[10px] text-text-muted break-all">
                      {stack.sttProvider}/{stack.sttModel} → {stack.llmProvider}/{stack.llmModel} →{" "}
                      {stack.ttsProvider}/{stack.ttsModel}
                    </p>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {rackTab === "voice" && (
          <div className="space-y-4">
            {realtime ? (
              <>
                <p className="text-xs text-text-muted">
                  OpenAI Realtime voice is locked after the first spoken reply on a call. Start a new call after
                  changing it.
                </p>
                <label className="block text-sm">
                  <span className="text-text-muted">Realtime voice</span>
                  <select
                    disabled={locked}
                    className="mt-2 w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm disabled:opacity-50"
                    value={stack.realtimeVoice || DEFAULT_REALTIME_VOICE}
                    onChange={(e) => patchStack({ realtimeVoice: e.target.value })}
                  >
                    {REALTIME_VOICES.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-sm">
                  <span className="text-text-muted">Speech speed</span>
                  <input
                    type="number"
                    step="0.05"
                    min={0.25}
                    max={1.5}
                    disabled={locked}
                    className="mt-2 w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm disabled:opacity-50"
                    value={normalizeRealtimeSpeed(stack.realtimeSpeed)}
                    onChange={(e) => patchStack({ realtimeSpeed: Number(e.target.value) })}
                  />
                </label>
                <p className="text-[10px] text-text-subtle">
                  Model: <span className="font-mono">{stack.llmModel || "gpt-realtime-2.1-mini"}</span> · PCM16 @ 24 kHz
                </p>
              </>
            ) : (
              <>
            <p className="text-xs text-text-muted">
              Voice saves automatically. Start a <strong>new call</strong> after changing provider in Stack tab.
            </p>
            {effectiveTtsProvider === "cartesia" || stack.ttsModel.startsWith("sonic") ? (
              <label className="block text-sm">
                <span className="text-text-muted">Cartesia voice</span>
                <div className="mt-2">
                  <CartesiaVoiceSelect
                    key="cartesia-voice"
                    disabled={false}
                    value={voiceValue}
                    ttsModel={stack.ttsModel || "sonic-3.5"}
                    defaultVoiceId={defaultCartesiaVoiceId}
                    onChange={(ttsVoiceId) => patchStack({ ttsVoiceId })}
                  />
                </div>
              </label>
            ) : (
              <label className="block text-sm">
                <span className="text-text-muted">Sarvam voice</span>
                <div className="mt-2">
                  <SarvamVoiceSelect
                    key="sarvam-voice"
                    disabled={false}
                    value={voiceValue}
                    model={stack.ttsModel || "bulbul:v3"}
                    speakersV3={sarvamSpeakersV3}
                    speakersV2={sarvamSpeakersV2}
                    onChange={(ttsVoiceId) => patchStack({ ttsVoiceId })}
                  />
                </div>
              </label>
            )}
            <p className="text-[10px] text-text-subtle">
              TTS provider: <span className="font-mono">{effectiveTtsProvider}</span> · model{" "}
              <span className="font-mono">{stack.ttsModel}</span>
            </p>
              </>
            )}
          </div>
        )}

        {rackTab === "advanced" && (
          <div className="space-y-3">
            {realtime ? (
              <>
                <label className="block text-xs">
                  <span className="text-text-muted">Turn detection</span>
                  <select
                    disabled={locked}
                    className="mt-1 w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-2.5 py-2 text-xs"
                    value={stack.realtimeTurnDetection || DEFAULT_REALTIME_TURN_DETECTION}
                    onChange={(e) => patchStack({ realtimeTurnDetection: e.target.value })}
                  >
                    {REALTIME_TURN_DETECTION.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </label>
                {(stack.realtimeTurnDetection || DEFAULT_REALTIME_TURN_DETECTION) === "semantic_vad" ? (
                  <label className="block text-xs">
                    <span className="text-text-muted">Semantic VAD eagerness</span>
                    <select
                      disabled={locked}
                      className="mt-1 w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-2.5 py-2 text-xs"
                      value={stack.realtimeVadEagerness || DEFAULT_REALTIME_VAD_EAGERNESS}
                      onChange={(e) => patchStack({ realtimeVadEagerness: e.target.value })}
                    >
                      {REALTIME_VAD_EAGERNESS.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <label className="block text-xs">
                    <span className="text-text-muted">Silence duration (ms)</span>
                    <input
                      type="number"
                      min={200}
                      max={2000}
                      disabled={locked}
                      className="mt-1 w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-2.5 py-2 text-xs"
                      value={normalizeRealtimeSilenceMs(stack.realtimeSilenceMs)}
                      onChange={(e) => patchStack({ realtimeSilenceMs: Number(e.target.value) })}
                    />
                  </label>
                )}
                <label className="block text-xs">
                  <span className="text-text-muted">Noise reduction</span>
                  <select
                    disabled={locked}
                    className="mt-1 w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-2.5 py-2 text-xs"
                    value={stack.realtimeNoiseReduction || DEFAULT_REALTIME_NOISE_REDUCTION}
                    onChange={(e) => patchStack({ realtimeNoiseReduction: e.target.value })}
                  >
                    {REALTIME_NOISE_REDUCTION.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </label>
                <p className="text-[11px] text-text-subtle">
                  Semantic VAD waits for a natural pause. Server VAD triggers on silence and is better for noisy
                  lines.
                </p>
              </>
            ) : (
              <>
            <label className="block text-xs">
              <span className="text-text-muted">STT mode</span>
              <select
                disabled={locked}
                className="mt-1 w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-2.5 py-2 text-xs"
                value={stack.sttMode}
                onChange={(e) => patchStack({ sttMode: e.target.value })}
              >
                {(sttModes.length ? sttModes : ["transcribe", "translate"]).map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-xs">
              <span className="text-text-muted">STT stream</span>
              <select
                disabled={locked}
                className="mt-1 w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-2.5 py-2 text-xs"
                value={stack.sttStreamType}
                onChange={(e) => patchStack({ sttStreamType: e.target.value })}
              >
                {(sttStreamTypes.length ? sttStreamTypes : ["fast", "accurate"]).map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            {showCustomStack && stackMode === "custom" && (
              <p className="text-[11px] text-text-subtle">
                Cartesia is STT/TTS only (no LLM). Use Ink Whisper for Telugu STT, Sonic 3.5 for TTS.
              </p>
            )}
              </>
            )}
          </div>
        )}

        <div className="skeuo-inset rounded-skeuo-md p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-muted">Session</span>
            <SkeuoBadge tone={locked ? "warning" : "info"}>{sessionStatus}</SkeuoBadge>
          </div>
          {locked && <p className="text-xs text-status-warning">Configuration locked during active call</p>}
        </div>
      </div>
    </SkeuoPanel>
  );
}
