"use client";

import { useState } from "react";
import Link from "next/link";
import { ensureArray } from "@/lib/ensure-array";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import { cn } from "@/lib/cn";
import { StudioTabRail } from "@/components/test-studio/StudioTabRail";
import {
  useTestStudioFineTune,
  CALL_END_REASONS,
  DEFAULT_CALL_END_FAREWELL,
  defaultCallEndPolicy,
} from "@/components/test-studio/useTestStudioFineTune";
import { compileLanguageLabel } from "@/components/test-studio/CompileLanguagePicker";
import { CompilerSectionsPanel } from "@/components/test-studio/CompilerSectionsPanel";
import { CartesiaVoiceSelect } from "@/components/test-studio/CartesiaVoiceSelect";
import { SarvamVoiceSelect } from "@/components/test-studio/SarvamVoiceSelect";
import {
  DEFAULT_REALTIME_NOISE_REDUCTION,
  DEFAULT_REALTIME_SPEED,
  DEFAULT_REALTIME_TURN_DETECTION,
  DEFAULT_REALTIME_VAD_EAGERNESS,
  DEFAULT_REALTIME_VOICE,
  REALTIME_MODEL_IDS,
  REALTIME_NOISE_REDUCTION,
  REALTIME_TURN_DETECTION,
  REALTIME_VAD_EAGERNESS,
  REALTIME_VOICES,
  isRealtimePstnMode,
  normalizeRealtimeSilenceMs,
  normalizeRealtimeSpeed,
} from "@/lib/realtime-voice";

type Tab = "prompts" | "llm" | "voice";

const TABS: { id: Tab; label: string }[] = [
  { id: "prompts", label: "Prompts" },
  { id: "llm", label: "LLM" },
  { id: "voice", label: "Voice & VAD" },
];

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-sm">
      <span className="text-text-muted">{label}</span>
      {hint && <p className="mt-0.5 text-[11px] text-text-subtle">{hint}</p>}
      <div className="mt-2">{children}</div>
    </label>
  );
}

const AGENT_BRIEF_PLACEHOLDER: Record<string, string> = {
  "te-IN":
    "Create a Telugu telecaller for Acme Realty.\nAgent name: Swetha.\nShe represents the business like a real teammate — listen, answer first, don't interrogate.\nKnown inventory: 1,000 sq ft from fifty lakhs. If they want a different size, follow them. Never invent prices.",
  "en-IN":
    "Create an English agent for Acme Support.\nAgent name: Priya.\nTalk like a person who works there — listen, answer first, don't interrogate.\nHandle billing tickets. Book callbacks. Never invent policies. Do not sell.",
  "hi-IN":
    "Create a Hindi telecaller for Acme Realty.\nAgent name: Priya.\nHinglish, like a real teammate — listen, answer first, don't interrogate.\nKnown inventory: 1,000 sq ft from fifty lakhs. If they want a different size, follow them. Never invent prices.",
};

const inputCls =
  "w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm disabled:opacity-50";

function countWords(text: string): number {
  const t = text.trim();
  if (!t) return 0;
  return t.split(/\s+/).length;
}

function SectionMeter({
  words,
  maxWords,
  recommended,
  chars,
  maxChars,
}: {
  words: number;
  maxWords: number;
  recommended: number;
  chars: number;
  maxChars: number;
}) {
  const over = words > maxWords || chars > maxChars;
  const warn = !over && words > recommended;
  return (
    <p
      className={cn(
        "mt-1 font-mono text-[10px]",
        over ? "text-status-error" : warn ? "text-status-warning" : "text-text-subtle"
      )}
    >
      {words}/{maxWords} words · {chars}/{maxChars} chars
      {over ? " — too long to save" : warn ? ` · keep under ~${recommended} words for cache + memory` : ""}
    </p>
  );
}

export function TestStudioFineTuneWorkbench({
  agentId,
  portal,
  language,
  locked,
  activeTab,
  onTabChange,
  stackTtsProvider,
  runtimeTtsSpeaker,
  onRuntimeSpeakerChange,
  sarvamSpeakersV3 = [],
  sarvamSpeakersV2 = [],
  channel = "agent",
  realtimeVoice,
  realtimeTurnDetection,
  realtimeVadEagerness,
  realtimeNoiseReduction,
  realtimeSpeed,
  realtimeSilenceMs,
  onRealtimeVoiceChange,
  onRealtimeTurnDetectionChange,
  onRealtimeSettingsChange,
  liveLlmModel,
  onLiveLlmChange,
}: {
  agentId: string;
  portal: "app" | "dev";
  language: string;
  locked: boolean;
  activeTab?: Tab;
  onTabChange?: (tab: Tab) => void;
  stackTtsProvider?: string;
  runtimeTtsSpeaker?: string;
  onRuntimeSpeakerChange?: (speaker: string) => void;
  sarvamSpeakersV3?: string[];
  sarvamSpeakersV2?: string[];
  channel?: "agent" | "pstn" | "pstn_realtime";
  realtimeVoice?: string;
  realtimeTurnDetection?: string;
  realtimeVadEagerness?: string;
  realtimeNoiseReduction?: string;
  realtimeSpeed?: number;
  realtimeSilenceMs?: number;
  onRealtimeVoiceChange?: (voice: string) => void;
  onRealtimeTurnDetectionChange?: (kind: string) => void;
  onRealtimeSettingsChange?: (patch: {
    realtimeVoice?: string;
    realtimeTurnDetection?: string;
    realtimeVadEagerness?: string;
    realtimeNoiseReduction?: string;
    realtimeSpeed?: number;
    realtimeSilenceMs?: number;
  }) => void;
  liveLlmModel?: string;
  onLiveLlmChange?: (model: string) => void;
}) {
  const [internalTab, setInternalTab] = useState<Tab>("prompts");
  const tab = activeTab ?? internalTab;
  const setTab = onTabChange ?? setInternalTab;
  const ft = useTestStudioFineTune(agentId, language, portal);
  const langLabel = compileLanguageLabel(language);
  const savedLang = ft.optimizerMeta.savedLanguage;
  const scriptLangMismatch = Boolean(savedLang && savedLang !== language && ft.instructions.agentScript);
  const callEnd = ft.instructions.callEndPolicy ?? defaultCallEndPolicy(language);
  const defaults = ft.catalog?.openai?.defaults || {};
  const modelLabels = ft.catalog?.openai?.modelLabels || {};
  const allowedModels = ensureArray<string>(ft.catalog?.openai?.allowedModels);
  const reasoningEfforts = ensureArray<string>(ft.catalog?.openai?.reasoningEfforts);
  const ttsCatalog = ft.catalog?.tts as
    | {
        defaultCartesiaVoiceId?: string;
        cartesiaModels?: { id: string; label: string }[];
        voicePresets?: { id: string; label: string }[];
        speakersV3?: string[];
        speakersV2?: string[];
      }
    | undefined;
  const defaultCartesiaVoice =
    String(ttsCatalog?.defaultCartesiaVoiceId || "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4");
  const useCartesia = stackTtsProvider === "cartesia" || String(ft.runtime.ttsModel || "").startsWith("sonic");
  const realtime = isRealtimePstnMode(channel);
  const filteredRealtime = allowedModels.filter((m) => m.startsWith("gpt-realtime"));
  const llmModels = realtime
    ? filteredRealtime.length
      ? filteredRealtime
      : [...REALTIME_MODEL_IDS]
    : allowedModels;

  const brainHref =
    portal === "dev" ? `/dev/agents/${agentId}/brain` : `/app/agents/${agentId}/brain`;

  return (
    <SkeuoPanel
      title="Fine-tune workbench"
      description="Saved to disk per agent — survives server restart"
      padding="md"
      className="console-page-enter"
    >
      <div className="mb-4 space-y-3">
        <StudioTabRail
          tone="child"
          ariaLabel="Fine-tune section"
          items={TABS.map((t) => ({ id: t.id, label: t.label }))}
          value={tab}
          onChange={setTab}
          locked={locked}
        />
        <div className="flex flex-wrap items-center gap-2">
            <SkeuoBadge tone="muted" className="font-mono text-[10px]">
              session: {ft.sessionId}
            </SkeuoBadge>
            <SkeuoButton type="button" variant="primary" size="sm"
              disabled={locked || ft.loading || ft.saving}
              onClick={tab === "prompts" ? ft.saveInstructions : ft.saveRuntime}>
              {ft.saving ? "Saving…" : `Save ${tab === "prompts" ? "prompts" : tab === "llm" ? "LLM" : "voice / VAD"}`}
            </SkeuoButton>
            {locked && (
              <SkeuoBadge tone="warning" className="text-[10px]">
                call in progress
              </SkeuoBadge>
            )}
        </div>
        <p role="status" className="text-xs text-text-muted">{ft.status}</p>
      </div>

      {ft.loading ? (
        <p className="text-sm text-text-muted">Loading fine-tune settings…</p>
      ) : (
        <>
          {tab === "prompts" && (
            <div className="space-y-5">
              <div className="flex flex-wrap gap-2">
                <SkeuoButton
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={locked}
                  onClick={ft.importFromAgentDraft}
                >
                  Import agent draft → brief
                </SkeuoButton>
                <SkeuoButton
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={locked}
                  onClick={ft.loadFactoryDefault}
                >
                  Load factory default
                </SkeuoButton>
                {portal === "dev" && (
                <Link
                  href={brainHref}
                  className="inline-flex items-center rounded-skeuo-sm border border-surface-border-subtle px-3 py-1.5 text-xs text-text-muted hover:bg-surface-raised"
                >
                  Open full brain editor →
                </Link>
                )}
              </div>

              <div className="rounded-skeuo-sm border border-surface-border-subtle skeuo-inset p-3 text-xs text-text-muted">
                Describe your agent in plain language — company, agent name, role, and goals. GPT expands it into a
                conversational policy (not a question tree) that answers first, follows the latest customer ask, and
                matches the role (sales vs support vs recruitment). Live memory still attaches after the cache
                breakpoint (~{ft.limits.memoryHeadroomTokens} tokens).
              </div>

              <p className="text-xs text-text-muted">
                Script compiles in <span className="font-medium text-text">{langLabel}</span>
                {scriptLangMismatch
                  ? ` — saved script is still ${compileLanguageLabel(savedLang || "")}; create agent script again.`
                  : "."}
              </p>

              <Field
                label="Agent brief"
                hint={`Business facts in any language — the live script will still be ${langLabel}.`}
              >
                <textarea
                  disabled={locked || ft.saving}
                  maxLength={ft.limits.agentBriefMax}
                  placeholder={AGENT_BRIEF_PLACEHOLDER[language] || AGENT_BRIEF_PLACEHOLDER["te-IN"]}
                  className={cn(inputCls, "min-h-[140px] resize-y text-sm")}
                  value={ft.instructions.agentBrief}
                  onChange={(e) =>
                    ft.setInstructions((p) => ({ ...p, agentBrief: e.target.value }))
                  }
                />
                <SectionMeter
                  words={countWords(ft.instructions.agentBrief)}
                  maxWords={ft.limits.agentBriefMaxWords}
                  recommended={ft.limits.recommendedAgentBriefWords}
                  chars={ft.instructions.agentBrief.length}
                  maxChars={ft.limits.agentBriefMax}
                />
              </Field>

              <Field
                label="Generated calling script"
                hint="Business script only — identity, offer, opening, and role. Platform rules are in Compiler sections below."
              >
                <textarea
                  readOnly
                  className={cn(inputCls, "min-h-[200px] resize-y font-mono text-[11px] opacity-90")}
                  value={
                    ft.instructions.agentScript ||
                    "Create agent script to generate the calling script from your brief…"
                  }
                />
              </Field>

              {portal === "dev" ? (
                <CompilerSectionsPanel data={ft.compilerSections} className="mt-2" />
              ) : null}

              <div className="rounded-skeuo-sm border border-surface-border-subtle p-4">
                <p className="text-sm text-text-muted">Call end</p>
                <p className="mt-0.5 text-[11px] text-text-subtle">
                  Optional. If you skip this, the default hangup line for {langLabel} is compiled into the brain
                  and used on web and phone. The model may propose hanging up; the server still validates goodbye /
                  refusal / goal / abuse. Farewell is spoken fully, then the call ends.
                </p>
                <p className="text-[11px] text-text-subtle">
                  Farewell line uses {langLabel}.
                </p>
                <div className="mt-3 grid gap-2">
                  {CALL_END_REASONS.map((reason) => {
                    const on = callEnd.allowedReasons.includes(reason.id);
                    return (
                      <label key={reason.id} className="flex items-start gap-2 text-sm">
                        <input
                          type="checkbox"
                          disabled={locked || ft.saving}
                          className="mt-1"
                          checked={on}
                          onChange={() => {
                            ft.setInstructions((p) => {
                              const cur = (p.callEndPolicy ?? defaultCallEndPolicy(language)).allowedReasons;
                              const next = on ? cur.filter((id) => id !== reason.id) : [...cur, reason.id];
                              return {
                                ...p,
                                callEndPolicy: {
                                  ...(p.callEndPolicy ?? defaultCallEndPolicy(language)),
                                  allowedReasons: next.length ? next : cur,
                                },
                              };
                            });
                          }}
                        />
                        <span>{reason.label}</span>
                      </label>
                    );
                  })}
                </div>
                <Field
                  label="Farewell"
                  hint={`One ${langLabel} sentence, spoken before hangup. Leave the default if you do not have a custom hangup script.`}
                >
                  <textarea
                    disabled={locked || ft.saving}
                    maxLength={240}
                    className={cn(inputCls, "min-h-[72px] resize-y text-sm")}
                    value={callEnd.farewell}
                    onChange={(e) =>
                      ft.setInstructions((p) => ({
                        ...p,
                        callEndPolicy: {
                          ...(p.callEndPolicy ?? defaultCallEndPolicy(language)),
                          farewell: e.target.value,
                        },
                      }))
                    }
                  />
                </Field>
                <div className="mt-3">
                  <SkeuoButton
                    type="button"
                    variant="secondary"
                    size="sm"
                    disabled={locked || ft.saving}
                    onClick={ft.saveCallEndPolicy}
                  >
                    Save call end
                  </SkeuoButton>
                </div>
              </div>

              <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                <Field label="Response style" hint="Optional style tag (e.g. concise, empathetic)">
                  <input
                    disabled={locked}
                    className={inputCls}
                    value={ft.instructions.responseStyle}
                    onChange={(e) =>
                      ft.setInstructions((p) => ({ ...p, responseStyle: e.target.value }))
                    }
                  />
                </Field>
                <div className="rounded-skeuo-sm border border-surface-border-subtle skeuo-inset p-3 text-xs text-text-muted">
                  <p>
                    Brain cache tokens:{" "}
                    <span className="font-mono text-text">{ft.instructions.estimatedTokens}</span> /{" "}
                    {ft.instructions.budgetTokens}
                    {ft.instructions.cacheEligible ? (
                      <span className="ml-2 text-status-success">cache ON</span>
                    ) : (
                      <span className="ml-2 text-status-warning">cache OFF</span>
                    )}
                  </p>
                  <p className="mt-1 text-[11px] text-text-subtle">
                    Headroom {ft.instructions.headroom} tokens · live memory uses ~{ft.limits.memoryHeadroomTokens} tokens after the breakpoint
                  </p>
                  {ft.optimizerMeta.compiledVersion ? (
                    <p className="mt-1 font-mono text-[10px]">
                      Script v{ft.optimizerMeta.compiledVersion}
                      {ft.optimizerMeta.optimizerModel ? ` · ${ft.optimizerMeta.optimizerModel}` : ""}
                      {ft.optimizerMeta.agentName ? ` · ${ft.optimizerMeta.agentName}` : ""}
                      {ft.optimizerMeta.detectedRole ? ` · ${ft.optimizerMeta.detectedRole}` : ""}
                    </p>
                  ) : (
                    <p className="mt-1">Create agent script to activate the cached brain</p>
                  )}
                </div>
              </div>
            </div>
          )}

          {tab === "llm" && (
            <div className="grid gap-5 lg:grid-cols-2">
              <Field
                label="OpenAI model"
                hint={realtime ? "Audio-to-audio Realtime models only. Temperature is not sent on this path." : undefined}
              >
                <select
                  disabled={locked}
                  className={inputCls}
                  value={
                    realtime
                      ? liveLlmModel && llmModels.includes(liveLlmModel)
                        ? liveLlmModel
                        : llmModels.includes(String(ft.runtime.openaiModel ?? defaults.openaiModel ?? ""))
                          ? String(ft.runtime.openaiModel ?? defaults.openaiModel ?? "")
                          : "gpt-realtime-2.1-mini"
                      : String(ft.runtime.openaiModel ?? defaults.openaiModel ?? "")
                  }
                  onChange={(e) => {
                    const value = e.target.value;
                    ft.setRuntime((r) => ({ ...r, openaiModel: value }));
                    if (realtime) onLiveLlmChange?.(value);
                  }}
                >
                  {llmModels.map((m) => (
                    <option key={m} value={m}>
                      {modelLabels[m] || m}
                    </option>
                  ))}
                </select>
              </Field>
              {!realtime && (
              <Field label="Reasoning effort">
                <select
                  disabled={locked}
                  className={inputCls}
                  value={String(
                    ft.runtime.openaiReasoningEffort ?? defaults.openaiReasoningEffort ?? "low"
                  )}
                  onChange={(e) =>
                    ft.setRuntime((r) => ({ ...r, openaiReasoningEffort: e.target.value }))
                  }
                >
                  {reasoningEfforts.map((e) => (
                    <option key={e} value={e}>
                      {e}
                    </option>
                  ))}
                </select>
              </Field>
              )}
              {!realtime && (
              <Field label="Temperature">
                <input
                  type="number"
                  step="0.1"
                  min={0}
                  max={2}
                  disabled={locked}
                  className={inputCls}
                  value={Number(ft.runtime.openaiTemperature ?? defaults.openaiTemperature ?? 0.7)}
                  onChange={(e) =>
                    ft.setRuntime((r) => ({ ...r, openaiTemperature: Number(e.target.value) }))
                  }
                />
              </Field>
              )}
              <Field label="Max output tokens">
                <input
                  type="number"
                  min={50}
                  max={800}
                  disabled={locked}
                  className={inputCls}
                  value={Number(ft.runtime.openaiMaxTokens ?? defaults.openaiMaxTokens ?? 200)}
                  onChange={(e) =>
                    ft.setRuntime((r) => ({ ...r, openaiMaxTokens: Number(e.target.value) }))
                  }
                />
              </Field>
              <Field label="Brain prompt budget (tokens)">
                <input
                  type="number"
                  min={1500}
                  max={10000}
                  disabled={locked}
                  className={inputCls}
                  value={Number(
                    ft.runtime.brainPromptBudgetTokens ?? defaults.brainPromptBudgetTokens ?? 2000
                  )}
                  onChange={(e) =>
                    ft.setRuntime((r) => ({
                      ...r,
                      brainPromptBudgetTokens: Number(e.target.value),
                    }))
                  }
                />
              </Field>
            </div>
          )}

          {tab === "voice" && (
            <div className="grid gap-5 lg:grid-cols-2">
              {realtime ? (
                <>
                  <Field
                    label="Realtime voice"
                    hint="OpenAI speech-to-speech voice. Locked after the first audio reply — start a new call to change it."
                  >
                    <select
                      disabled={locked}
                      className={inputCls}
                      value={realtimeVoice || DEFAULT_REALTIME_VOICE}
                      onChange={(e) => {
                        onRealtimeVoiceChange?.(e.target.value);
                        onRealtimeSettingsChange?.({ realtimeVoice: e.target.value });
                      }}
                    >
                      {REALTIME_VOICES.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field
                    label="Turn detection"
                    hint="Semantic VAD waits for meaning; server VAD uses silence."
                  >
                    <select
                      disabled={locked}
                      className={inputCls}
                      value={realtimeTurnDetection || DEFAULT_REALTIME_TURN_DETECTION}
                      onChange={(e) => {
                        onRealtimeTurnDetectionChange?.(e.target.value);
                        onRealtimeSettingsChange?.({ realtimeTurnDetection: e.target.value });
                      }}
                    >
                      {REALTIME_TURN_DETECTION.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                  {(realtimeTurnDetection || DEFAULT_REALTIME_TURN_DETECTION) === "semantic_vad" ? (
                    <Field label="Semantic VAD eagerness" hint="How quickly the model takes the turn.">
                      <select
                        disabled={locked}
                        className={inputCls}
                        value={realtimeVadEagerness || DEFAULT_REALTIME_VAD_EAGERNESS}
                        onChange={(e) => onRealtimeSettingsChange?.({ realtimeVadEagerness: e.target.value })}
                      >
                        {REALTIME_VAD_EAGERNESS.map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.label}
                          </option>
                        ))}
                      </select>
                    </Field>
                  ) : (
                    <Field label="Silence duration (ms)" hint="Server VAD endpointing — same role as STT silence on Full PSTN.">
                      <input
                        type="number"
                        min={200}
                        max={2000}
                        disabled={locked}
                        className={inputCls}
                        value={normalizeRealtimeSilenceMs(realtimeSilenceMs)}
                        onChange={(e) =>
                          onRealtimeSettingsChange?.({ realtimeSilenceMs: Number(e.target.value) })
                        }
                      />
                    </Field>
                  )}
                  <Field label="Noise reduction" hint="Far field is the usual choice for Telnyx PSTN.">
                    <select
                      disabled={locked}
                      className={inputCls}
                      value={realtimeNoiseReduction || DEFAULT_REALTIME_NOISE_REDUCTION}
                      onChange={(e) => onRealtimeSettingsChange?.({ realtimeNoiseReduction: e.target.value })}
                    >
                      {REALTIME_NOISE_REDUCTION.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Speech speed" hint="OpenAI audio output speed (0.25–1.5). Same idea as TTS pace.">
                    <input
                      type="number"
                      step="0.05"
                      min={0.25}
                      max={1.5}
                      disabled={locked}
                      className={inputCls}
                      value={normalizeRealtimeSpeed(realtimeSpeed ?? DEFAULT_REALTIME_SPEED)}
                      onChange={(e) => onRealtimeSettingsChange?.({ realtimeSpeed: Number(e.target.value) })}
                    />
                  </Field>
                </>
              ) : (
              <>
              {useCartesia ? (
                <>
                  <Field
                    label="Cartesia voice"
                    hint="Telugu, Hindi, Indian English & US/UK English — pulled live from Cartesia."
                  >
                    <CartesiaVoiceSelect
                      disabled={false}
                      value={String(ft.runtime.ttsSpeaker || runtimeTtsSpeaker || defaultCartesiaVoice)}
                      defaultVoiceId={defaultCartesiaVoice}
                      onChange={(ttsSpeaker) => {
                        ft.setRuntime((r) => ({
                          ...r,
                          ttsSpeaker,
                          ttsModel: r.ttsModel || "sonic-3.5",
                        }));
                        onRuntimeSpeakerChange?.(ttsSpeaker);
                      }}
                    />
                  </Field>
                  <Field label="Cartesia model">
                    <select
                      disabled={locked}
                      className={inputCls}
                      value={String(ft.runtime.ttsModel || "sonic-3.5")}
                      onChange={(e) => ft.setRuntime((r) => ({ ...r, ttsModel: e.target.value }))}
                    >
                      {ensureArray<{ id: string; label: string }>(ttsCatalog?.cartesiaModels).map(
                        (m) => (
                          <option key={m.id} value={m.id}>
                            {m.label || m.id}
                          </option>
                        )
                      )}
                    </select>
                  </Field>
                </>
              ) : (
                <>
                  <Field label="Voice preset">
                    <select
                      disabled={locked}
                      className={inputCls}
                      value={String(ft.runtime.voicePresetId ?? defaults.voicePresetId ?? "")}
                      onChange={(e) => ft.setRuntime((r) => ({ ...r, voicePresetId: e.target.value }))}
                    >
                      {ensureArray<{ id: string; label: string }>(ttsCatalog?.voicePresets).map(
                        (p) => (
                          <option key={p.id} value={p.id}>
                            {p.label}
                          </option>
                        )
                      )}
                    </select>
                  </Field>
                  <Field label="Sarvam TTS speaker" hint="Auto-saves to runtime when changed">
                    <SarvamVoiceSelect
                      disabled={false}
                      value={String(ft.runtime.ttsSpeaker || runtimeTtsSpeaker || defaults.ttsSpeaker || "shubh")}
                      model={String(ft.runtime.ttsModel || "bulbul:v3")}
                      speakersV3={sarvamSpeakersV3.length ? sarvamSpeakersV3 : ensureArray<string>(ttsCatalog?.speakersV3)}
                      speakersV2={sarvamSpeakersV2.length ? sarvamSpeakersV2 : ensureArray<string>(ttsCatalog?.speakersV2)}
                      onChange={(ttsSpeaker) => {
                        ft.setRuntime((r) => ({ ...r, ttsSpeaker }));
                        onRuntimeSpeakerChange?.(ttsSpeaker);
                      }}
                    />
                  </Field>
                </>
              )}
              <Field label="TTS pace / temperature">
                <div className="flex gap-2">
                  <input
                    type="number"
                    step="0.05"
                    min={0.5}
                    max={2}
                    disabled={locked}
                    className={inputCls}
                    value={Number(ft.runtime.ttsPace ?? defaults.ttsPace ?? 1)}
                    onChange={(e) => ft.setRuntime((r) => ({ ...r, ttsPace: Number(e.target.value) }))}
                  />
                  <input
                    type="number"
                    step="0.05"
                    min={0.01}
                    max={1}
                    disabled={locked}
                    className={inputCls}
                    value={Number(ft.runtime.ttsTemperature ?? defaults.ttsTemperature ?? 0.6)}
                    onChange={(e) =>
                      ft.setRuntime((r) => ({ ...r, ttsTemperature: Number(e.target.value) }))
                    }
                  />
                </div>
              </Field>
              <Field label="STT silence (ms)" hint="VAD endpointing — applied on next call STT websocket">
                <input
                  type="number"
                  min={100}
                  max={2000}
                  disabled={locked}
                  className={inputCls}
                  value={Number(ft.runtime.sttSilenceMs ?? defaults.sttSilenceMs ?? 500)}
                  onChange={(e) =>
                    ft.setRuntime((r) => ({ ...r, sttSilenceMs: Number(e.target.value) }))
                  }
                />
              </Field>
              <Field label="Barge min words">
                <input
                  type="number"
                  min={1}
                  max={10}
                  disabled={locked}
                  className={inputCls}
                  value={Number(ft.runtime.bargeMinWords ?? defaults.bargeMinWords ?? 3)}
                  onChange={(e) =>
                    ft.setRuntime((r) => ({ ...r, bargeMinWords: Number(e.target.value) }))
                  }
                />
              </Field>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  disabled={locked}
                  checked={Boolean(ft.runtime.bargeRequireVad ?? defaults.bargeRequireVad ?? true)}
                  onChange={(e) =>
                    ft.setRuntime((r) => ({ ...r, bargeRequireVad: e.target.checked }))
                  }
                />
                <span className="text-text-muted">Barge requires VAD speech start</span>
              </label>
              <Field label="TTS chunking (min buffer / max chunk)">
                <div className="flex gap-2">
                  <input
                    type="number"
                    disabled={locked}
                    className={inputCls}
                    value={Number(ft.runtime.ttsMinBuffer ?? defaults.ttsMinBuffer ?? 30)}
                    onChange={(e) =>
                      ft.setRuntime((r) => ({ ...r, ttsMinBuffer: Number(e.target.value) }))
                    }
                  />
                  <input
                    type="number"
                    disabled={locked}
                    className={inputCls}
                    value={Number(ft.runtime.ttsMaxChunk ?? defaults.ttsMaxChunk ?? 80)}
                    onChange={(e) =>
                      ft.setRuntime((r) => ({ ...r, ttsMaxChunk: Number(e.target.value) }))
                    }
                  />
                </div>
              </Field>
              </>
              )}
            </div>
          )}
        </>
      )}

      <div className="mt-6 flex flex-wrap items-center gap-2 border-t border-surface-border-subtle pt-4">
        <SkeuoButton type="button" variant="primary" disabled={locked || ft.loading || ft.saving} onClick={ft.saveAll}>
          {ft.saving ? "Creating script…" : "Save all for test session"}
        </SkeuoButton>
        <SkeuoButton
          type="button"
          variant="secondary"
          disabled={locked || ft.loading || ft.saving}
          onClick={ft.saveInstructions}
        >
          {ft.saving ? "Creating script…" : "Create agent script"}
        </SkeuoButton>
        <SkeuoButton
          type="button"
          variant="secondary"
          disabled={locked || ft.loading || ft.saving}
          onClick={ft.saveRuntime}
        >
          Save runtime only
        </SkeuoButton>
        <SkeuoButton
          type="button"
          variant="ghost"
          disabled={locked || ft.loading || ft.saving}
          onClick={ft.clearSession}
        >
          Clear session overrides
        </SkeuoButton>
        {ft.status && (
          <span
            className={cn(
              "text-xs",
              /fail|too long|exceed/i.test(ft.status) ? "text-status-error" : "text-text-muted"
            )}
          >
            {ft.status}
          </span>
        )}
      </div>
    </SkeuoPanel>
  );
}
