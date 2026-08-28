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
import { cn } from "@/lib/cn";

type ChannelTab = "browser" | "pstn";
type RackTab = "channel" | "stack" | "voice" | "advanced";

const RACK_TABS: { id: RackTab; label: string }[] = [
  { id: "channel", label: "Channel" },
  { id: "stack", label: "Stack" },
  { id: "voice", label: "Voice" },
  { id: "advanced", label: "STT" },
];

function StageSelect({
  label,
  provider,
  model,
  providers,
  stage,
  disabled,
  onProviderChange,
  onModelChange,
}: {
  label: string;
  provider: string;
  model: string;
  providers: ProviderEntry[];
  stage: "stt" | "llm" | "tts";
  disabled?: boolean;
  onProviderChange: (provider: string, model: string) => void;
  onModelChange: (model: string) => void;
}) {
  const options = providers.filter((p) => (p.models?.[stage]?.length ?? 0) > 0);
  const modelOptions = modelsFor(providers, provider, stage);

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
        {modelOptions.map((m) => (
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
  onLanguageChange,
  sessionStatus,
  locked,
  sarvamSpeakersV3 = [],
  sarvamSpeakersV2 = [],
  runtimeTtsSpeaker = "",
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
  onLanguageChange: (l: string) => void;
  sessionStatus: string;
  locked: boolean;
  sarvamSpeakersV3?: string[];
  sarvamSpeakersV2?: string[];
  runtimeTtsSpeaker?: string;
}) {
  const tierKey = (tier.toLowerCase() as TierName) in TIER_META ? (tier.toLowerCase() as TierName) : "medium";
  const [rackTab, setRackTab] = useState<RackTab>("channel");
  const effectiveTtsProvider = stack.ttsProvider || "sarvam";
  const voiceValue = stack.ttsVoiceId || runtimeTtsSpeaker || "";

  function patchStack(patch: Partial<StackForm>) {
    onStackChange({ ...stack, ...patch });
  }

  return (
    <SkeuoPanel title="Configuration" description="Channel · stack · voice · STT" padding="md">
      <div className="sticky top-0 z-20 -mx-1 mb-4 border-b border-surface-border-subtle bg-surface-panel/95 px-1 pb-3 backdrop-blur">
        <div className="flex flex-wrap gap-1 rounded-skeuo-sm border border-surface-border-subtle skeuo-inset p-1">
          {RACK_TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              disabled={locked}
              onClick={() => setRackTab(t.id)}
              className={cn(
                "flex-1 min-w-[4.5rem] rounded-skeuo-sm px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wide transition-colors disabled:opacity-50",
                rackTab === t.id ? "skeuo-btn-primary text-white" : "text-text-muted hover:text-text"
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-4">
        {rackTab === "channel" && (
          <>
            <div className="flex flex-wrap gap-2">
              {(["browser", ...(showPstn ? ["pstn"] : [])] as ChannelTab[]).map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => onChannelChange(c)}
                  disabled={locked}
                  className={cn(
                    "rounded-skeuo-sm px-3 py-2 text-xs font-semibold uppercase tracking-wider transition-all",
                    channel === c ? "skeuo-btn-primary text-white" : "skeuo-btn-secondary",
                    locked && "opacity-50"
                  )}
                >
                  {c === "browser" ? "Browser mic" : "PSTN · Plivo"}
                </button>
              ))}
            </div>
            <label className="block text-sm">
              <span className="text-text-muted">Language</span>
              <select
                disabled={locked}
                className="mt-2 w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm disabled:opacity-50"
                value={language}
                onChange={(e) => onLanguageChange(e.target.value)}
              >
                <option value="te-IN">te-IN — Telugu</option>
                <option value="en-IN">en-IN — English</option>
                <option value="hi-IN">hi-IN — Hindi</option>
              </select>
            </label>
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
              </label>
            ) : catalogLoading ? (
              <p className="text-xs text-text-muted">Loading providers…</p>
            ) : providers.length === 0 ? (
              <p className="text-xs text-status-warning">No providers in catalog. Check Environment keys.</p>
            ) : (
              <div className="space-y-3">
                <StageSelect
                  label="STT"
                  stage="stt"
                  providers={providers}
                  provider={stack.sttProvider}
                  model={stack.sttModel}
                  disabled={locked}
                  onProviderChange={(sttProvider, sttModel) => patchStack({ sttProvider, sttModel })}
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
                  onProviderChange={(ttsProvider, ttsModel) =>
                    patchStack({ ttsProvider, ttsModel, ttsVoiceId: stack.ttsVoiceId })
                  }
                  onModelChange={(ttsModel) => patchStack({ ttsModel })}
                />
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
            <p className="text-xs text-text-muted">
              Voice saves automatically. Start a <strong>new call</strong> after changing provider in Stack tab.
            </p>
            {effectiveTtsProvider === "cartesia" || stack.ttsModel.startsWith("sonic") ? (
              <label className="block text-sm">
                <span className="text-text-muted">Cartesia voice</span>
                <div className="mt-2">
                  <CartesiaVoiceSelect
                    disabled={false}
                    value={voiceValue}
                    ttsModel={stack.ttsModel || "sonic-3.5"}
                    onChange={(ttsVoiceId) => patchStack({ ttsVoiceId })}
                  />
                </div>
              </label>
            ) : (
              <label className="block text-sm">
                <span className="text-text-muted">Sarvam voice</span>
                <div className="mt-2">
                  <SarvamVoiceSelect
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
          </div>
        )}

        {rackTab === "advanced" && (
          <div className="space-y-3">
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
