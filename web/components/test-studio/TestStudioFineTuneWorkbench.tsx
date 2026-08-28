"use client";

import { useState } from "react";
import Link from "next/link";
import { ensureArray } from "@/lib/ensure-array";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import { cn } from "@/lib/cn";
import { useTestStudioFineTune } from "@/components/test-studio/useTestStudioFineTune";
import { CartesiaVoiceSelect } from "@/components/test-studio/CartesiaVoiceSelect";
import { SarvamVoiceSelect } from "@/components/test-studio/SarvamVoiceSelect";

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

const inputCls =
  "w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm disabled:opacity-50";

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
}) {
  const [internalTab, setInternalTab] = useState<Tab>("prompts");
  const tab = activeTab ?? internalTab;
  const setTab = onTabChange ?? setInternalTab;
  const ft = useTestStudioFineTune(agentId, language);
  const defaults = ft.catalog?.openai?.defaults || {};
  const modelLabels = ft.catalog?.openai?.modelLabels || {};
  const allowedModels = ensureArray<string>(ft.catalog?.openai?.allowedModels);
  const reasoningEfforts = ensureArray<string>(ft.catalog?.openai?.reasoningEfforts);
  const defaultCartesiaVoice =
    String(ft.catalog?.tts?.defaultCartesiaVoiceId || "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4");
  const useCartesia = stackTtsProvider === "cartesia" || String(ft.runtime.ttsModel || "").startsWith("sonic");

  const brainHref =
    portal === "dev" ? `/dev/agents/${agentId}/brain` : `/app/agents/${agentId}/brain`;

  return (
    <SkeuoPanel
      title="Fine-tune workbench"
      description="Saved to disk — survives server restart (session: test-studio)"
      padding="md"
      className="console-page-enter"
    >
      <div className="sticky top-0 z-30 -mx-4 mb-4 border-b border-surface-border-subtle bg-surface/95 px-4 py-3 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-1 rounded-skeuo-sm border border-surface-border-subtle skeuo-inset p-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                disabled={locked}
                onClick={() => setTab(t.id)}
                className={cn(
                  "rounded-skeuo-sm px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50",
                  tab === t.id
                    ? "bg-accent text-accent-fg shadow-skeuo-sm"
                    : "text-text-muted hover:bg-surface-raised"
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <SkeuoBadge tone="muted" className="font-mono text-[10px]">
              session: {ft.sessionId}
            </SkeuoBadge>
            <SkeuoBadge tone="success" className="text-[10px]">
              persisted
            </SkeuoBadge>
            {locked && (
              <SkeuoBadge tone="warning" className="text-[10px]">
                call in progress
              </SkeuoBadge>
            )}
          </div>
        </div>
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
                  Import agent draft → business
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
                <Link
                  href={brainHref}
                  className="inline-flex items-center rounded-skeuo-sm border border-surface-border-subtle px-3 py-1.5 text-xs text-text-muted hover:bg-surface-raised"
                >
                  Open full brain editor →
                </Link>
              </div>

              <div className="grid gap-5 lg:grid-cols-2">
                <Field
                  label="Behaviour instructions (dev / platform)"
                  hint="Your platform rules — saved as entered. Merged into compiled cache prompt on Save."
                >
                  <textarea
                    disabled={locked}
                    className={cn(inputCls, "min-h-[140px] resize-y font-mono text-xs")}
                    value={ft.instructions.behaviourInstructions}
                    onChange={(e) =>
                      ft.setInstructions((p) => ({ ...p, behaviourInstructions: e.target.value }))
                    }
                  />
                </Field>
                <Field
                  label="Business instructions (customer)"
                  hint="What the business client provides — saved raw. Never replaced by the optimizer in the UI."
                >
                  <textarea
                    disabled={locked}
                    className={cn(inputCls, "min-h-[140px] resize-y font-mono text-xs")}
                    value={ft.instructions.businessInstructions}
                    onChange={(e) =>
                      ft.setInstructions((p) => ({ ...p, businessInstructions: e.target.value }))
                    }
                  />
                </Field>
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
                    Compiled cache tokens:{" "}
                    <span className="font-mono text-text">{ft.instructions.estimatedTokens}</span> /{" "}
                    {ft.instructions.budgetTokens}
                  </p>
                  {ft.optimizerMeta.rawTokenEstimate ? (
                    <p className="mt-1">
                      Raw ~{ft.optimizerMeta.rawTokenEstimate} → compiled {ft.instructions.estimatedTokens}
                      {ft.optimizerMeta.tokensSaved ? ` (saved ~${ft.optimizerMeta.tokensSaved})` : ""}
                    </p>
                  ) : null}
                  {ft.optimizerMeta.compiledVersion ? (
                    <p className="mt-1 font-mono text-[10px]">
                      v{ft.optimizerMeta.compiledVersion}
                      {ft.optimizerMeta.optimizerModel ? ` · ${ft.optimizerMeta.optimizerModel}` : ""}
                    </p>
                  ) : (
                    <p className="mt-1">Save prompts to run one-time compiler</p>
                  )}
                </div>
              </div>

              {portal === "dev" && (
                <Field
                  label="Compiled cache prompt (dev only)"
                  hint="LLM-compressed merge sent to the API cache breakpoint — not shown to business clients"
                >
                  <textarea
                    readOnly
                    className={cn(inputCls, "min-h-[160px] resize-y font-mono text-[11px] opacity-90")}
                    value={ft.effectivePreview || "Save prompts to generate compiled preview…"}
                  />
                </Field>
              )}
            </div>
          )}

          {tab === "llm" && (
            <div className="grid gap-5 lg:grid-cols-2">
              <Field label="OpenAI model">
                <select
                  disabled={locked}
                  className={inputCls}
                  value={String(ft.runtime.openaiModel ?? defaults.openaiModel ?? "")}
                  onChange={(e) => ft.setRuntime((r) => ({ ...r, openaiModel: e.target.value }))}
                >
                  {allowedModels.map((m) => (
                    <option key={m} value={m}>
                      {modelLabels[m] || m}
                    </option>
                  ))}
                </select>
              </Field>
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
                  max={2500}
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
              {useCartesia ? (
                <>
                  <Field
                    label="Cartesia voice"
                    hint="Telugu, Hindi, Indian English & US/UK English — pulled live from Cartesia."
                  >
                    <CartesiaVoiceSelect
                      disabled={false}
                      value={String(ft.runtime.ttsSpeaker || runtimeTtsSpeaker || defaultCartesiaVoice)}
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
                      {ensureArray<{ id: string; label: string }>(ft.catalog?.tts?.cartesiaModels).map(
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
                      {ensureArray<{ id: string; label: string }>(ft.catalog?.tts?.voicePresets).map(
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
                      speakersV3={sarvamSpeakersV3.length ? sarvamSpeakersV3 : ensureArray<string>(ft.catalog?.tts?.speakersV3)}
                      speakersV2={sarvamSpeakersV2.length ? sarvamSpeakersV2 : ensureArray<string>(ft.catalog?.tts?.speakersV2)}
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
            </div>
          )}
        </>
      )}

      <div className="mt-6 flex flex-wrap items-center gap-2 border-t border-surface-border-subtle pt-4">
        <SkeuoButton type="button" variant="primary" disabled={locked || ft.loading} onClick={ft.saveAll}>
          Save all for test session
        </SkeuoButton>
        <SkeuoButton
          type="button"
          variant="secondary"
          disabled={locked || ft.loading}
          onClick={async () => {
            await ft.saveInstructions();
            await ft.refreshEffectivePreview();
          }}
        >
          Save prompts only
        </SkeuoButton>
        <SkeuoButton
          type="button"
          variant="secondary"
          disabled={locked || ft.loading}
          onClick={ft.saveRuntime}
        >
          Save runtime only
        </SkeuoButton>
        <SkeuoButton
          type="button"
          variant="ghost"
          disabled={locked || ft.loading}
          onClick={ft.clearSession}
        >
          Clear session overrides
        </SkeuoButton>
        {ft.status && <span className="text-xs text-text-muted">{ft.status}</span>}
      </div>
    </SkeuoPanel>
  );
}
