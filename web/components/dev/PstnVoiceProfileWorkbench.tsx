"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";

const PROFILE_TIERS = ["low", "medium", "premium"] as const;
type ProfileTier = (typeof PROFILE_TIERS)[number];

type StageProfile = { provider: string; model: string };
type LlmProfile = { provider: string; modelId: string; apiMode: string };
type VoiceProfile = {
  id: string;
  label: string;
  providerVoiceId: string;
  languages: string[];
};
type ModelProfile = {
  id: string;
  label: string;
  provider: string;
  model: string;
  apiMode: string;
  voices: VoiceProfile[];
};
type EngineProfile = { id: string; label: string; models: ModelProfile[] };
type ProfileEvidence = {
  sarvamModelAccess: boolean;
  sttVerified: boolean;
  ttsCatalogVerified: boolean;
  toolsVerified: boolean;
  capacityVerified: boolean;
  mediaFormatsVerified: boolean;
  credentialRefConfigured: boolean;
};
type ComposedProfile = {
  schemaVersion: 1;
  enabled: boolean;
  supportedLanguages: string[];
  stt: StageProfile;
  llm: LlmProfile;
  engines: EngineProfile[];
  evidence: ProfileEvidence;
};
type ReadinessBlocker = { code: string; message: string };
type RetailRate = { complete?: boolean } | null;
type TierProfileRow = {
  tier: ProfileTier;
  profileRevision: number | null;
  composedProfile: ComposedProfile | null;
  readiness: { ready: boolean; enabled: boolean; blockers: ReadinessBlocker[] };
  retailRate: RetailRate;
};
type ProfilesResponse = { environment: string; profiles: TierProfileRow[] };

const EMPTY_EVIDENCE: ProfileEvidence = {
  sarvamModelAccess: false,
  sttVerified: false,
  ttsCatalogVerified: false,
  toolsVerified: false,
  capacityVerified: false,
  mediaFormatsVerified: false,
  credentialRefConfigured: false,
};

function emptyProfile(): ComposedProfile {
  return {
    schemaVersion: 1,
    enabled: false,
    supportedLanguages: [],
    stt: { provider: "", model: "" },
    llm: { provider: "", modelId: "", apiMode: "" },
    engines: [],
    evidence: { ...EMPTY_EVIDENCE },
  };
}

function normalizeProfile(profile: ComposedProfile | null | undefined): ComposedProfile {
  if (!profile) return emptyProfile();
  return {
    schemaVersion: 1,
    enabled: profile.enabled === true,
    supportedLanguages: Array.isArray(profile.supportedLanguages) ? [...profile.supportedLanguages] : [],
    stt: {
      provider: profile.stt?.provider || "",
      model: profile.stt?.model || "",
    },
    llm: {
      provider: profile.llm?.provider || "",
      modelId: profile.llm?.modelId || "",
      apiMode: profile.llm?.apiMode || "",
    },
    engines: Array.isArray(profile.engines)
      ? profile.engines.map((engine) => ({
          id: engine.id || "",
          label: engine.label || "",
          models: Array.isArray(engine.models)
            ? engine.models.map((model) => ({
                id: model.id || "",
                label: model.label || "",
                provider: model.provider || "",
                model: model.model || "",
                apiMode: model.apiMode || "",
                voices: Array.isArray(model.voices)
                  ? model.voices.map((voice) => ({
                      id: voice.id || "",
                      label: voice.label || "",
                      providerVoiceId: voice.providerVoiceId || "",
                      languages: Array.isArray(voice.languages) ? [...voice.languages] : [],
                    }))
                  : [],
              }))
            : [],
        }))
      : [],
    evidence: { ...EMPTY_EVIDENCE, ...(profile.evidence || {}) },
  };
}

function splitList(value: string): string[] {
  return value.split(",").map((part) => part.trim()).filter(Boolean);
}

function tierLabel(tier: ProfileTier): string {
  if (tier === "medium") return "Standard (medium)";
  if (tier === "premium") return "Premium · existing Live path";
  return "Low";
}

function isRateComplete(rate: RetailRate): boolean {
  return rate?.complete === true;
}

function StatusPill({ tone, children }: { tone: "good" | "warn" | "muted"; children: ReactNode }) {
  const style = {
    good: "border-emerald-400/25 bg-emerald-400/10 text-emerald-300",
    warn: "border-amber-400/25 bg-amber-400/10 text-amber-200",
    muted: "border-surface-border-subtle bg-surface-raised text-text-muted",
  }[tone];
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${style}`}>{children}</span>;
}

function TextField({
  label,
  value,
  onChange,
  disabled,
  placeholder,
  mono = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  placeholder?: string;
  mono?: boolean;
}) {
  return (
    <label className="block min-w-0 text-sm">
      <span className="mb-1.5 block text-xs font-medium text-text-muted">{label}</span>
      <input
        type="text"
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        spellCheck={false}
        onChange={(event) => onChange(event.target.value)}
        className={`w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text placeholder:text-text-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40 disabled:cursor-not-allowed disabled:opacity-60 ${mono ? "font-mono" : ""}`}
      />
    </label>
  );
}

function EvidenceToggle({
  label,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex min-h-11 items-start gap-3 rounded-xl border border-surface-border-subtle bg-surface-raised/50 px-3 py-3 text-sm text-text">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-0.5 size-4 accent-accent-primary disabled:cursor-not-allowed"
      />
      <span>{label}</span>
    </label>
  );
}

async function responseError(response: Response): Promise<string> {
  const payload: unknown = await response.json().catch(() => null);
  if (typeof payload === "object" && payload !== null && "detail" in payload) {
    const detail = payload.detail;
    if (typeof detail === "string" && detail.length < 240) return detail;
    if (typeof detail === "object" && detail !== null && "message" in detail) {
      const message = detail.message;
      if (typeof message === "string" && message.length < 240) return message;
    }
  }
  return `Request failed (${response.status}). Review the profile and try again.`;
}

export function PstnVoiceProfileWorkbench() {
  const [rows, setRows] = useState<TierProfileRow[]>([]);
  const [environment, setEnvironment] = useState("");
  const [selected, setSelected] = useState<ProfileTier>("low");
  const [draft, setDraft] = useState<ComposedProfile>(emptyProfile());
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const selectedRow = rows.find((row) => row.tier === selected);
  const isPremium = selected === "premium";
  const isEnabled = selectedRow?.readiness.enabled === true;
  const rateComplete = isPremium || isRateComplete(selectedRow?.retailRate ?? null);
  const blockers = selectedRow?.readiness.blockers ?? [];
  const canActivate = Boolean(
    selectedRow &&
      !isPremium &&
      !isEnabled &&
      !dirty &&
      selectedRow.composedProfile &&
      selectedRow.readiness.ready === true &&
      blockers.length === 0 &&
      rateComplete
  );
  const canEdit = !isPremium && !isEnabled && !busy;

  const loadProfiles = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true);
    setError("");
    try {
      await refreshPortalSession("dev");
      const response = await portalFetch("dev", "/api/dev/stack/voice-profiles");
      if (!response.ok) throw new Error(await responseError(response));
      const payload = (await response.json()) as ProfilesResponse;
      if (!Array.isArray(payload.profiles)) throw new Error("The voice profile response is incomplete.");
      setRows(payload.profiles);
      setEnvironment(typeof payload.environment === "string" ? payload.environment : "");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load PSTN voice profiles.");
    } finally {
      if (showLoading) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadProfiles();
  }, [loadProfiles]);

  useEffect(() => {
    const row = rows.find((profileRow) => profileRow.tier === selected);
    setDraft(normalizeProfile(row?.composedProfile));
    setDirty(false);
  }, [rows, selected]);

  function updateDraft(update: (current: ComposedProfile) => ComposedProfile) {
    setDraft((current) => update(current));
    setDirty(true);
  }

  function updateEngine(engineIndex: number, patch: Partial<EngineProfile>) {
    updateDraft((current) => ({
      ...current,
      engines: current.engines.map((engine, index) => index === engineIndex ? { ...engine, ...patch } : engine),
    }));
  }

  function updateModel(engineIndex: number, modelIndex: number, patch: Partial<ModelProfile>) {
    updateDraft((current) => ({
      ...current,
      engines: current.engines.map((engine, index) => index === engineIndex
        ? { ...engine, models: engine.models.map((model, itemIndex) => itemIndex === modelIndex ? { ...model, ...patch } : model) }
        : engine),
    }));
  }

  function updateVoice(engineIndex: number, modelIndex: number, voiceIndex: number, patch: Partial<VoiceProfile>) {
    updateDraft((current) => ({
      ...current,
      engines: current.engines.map((engine, index) => index === engineIndex
        ? {
            ...engine,
            models: engine.models.map((model, itemIndex) => itemIndex === modelIndex
              ? { ...model, voices: model.voices.map((voice, itemVoiceIndex) => itemVoiceIndex === voiceIndex ? { ...voice, ...patch } : voice) }
              : model),
          }
        : engine),
    }));
  }

  async function saveProfile() {
    if (!selectedRow || isPremium || busy) return;

    setBusy(true);
    setError("");
    setStatus("");
    try {
      const response = await portalFetch("dev", `/api/dev/stack/voice-profiles/${selected}`, {
        method: "PUT",
        body: JSON.stringify({
          expectedRevision: selectedRow.profileRevision,
          composedProfile: { ...draft, enabled: false },
        }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      await response.json().catch(() => null);
      await loadProfiles(false);
      setStatus("Profile draft saved. It remains disabled.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save the PSTN voice profile.");
    } finally {
      setBusy(false);
    }
  }

  async function setProfileEnabled(enabled: boolean) {
    if (!selectedRow || isPremium || busy) return;
    if (enabled && !canActivate) {
      setStatus("Activation is blocked until backend readiness and a complete native tier rate are confirmed.");
      return;
    }

    setBusy(true);
    setError("");
    setStatus("");
    try {
      const response = await portalFetch("dev", `/api/dev/stack/voice-profiles/${selected}/activation`, {
        method: "PUT",
        body: JSON.stringify({ expectedRevision: selectedRow.profileRevision, enabled }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      await response.json().catch(() => null);
      await loadProfiles(false);
      setStatus(enabled ? "Profile enabled for new PSTN admissions." : "Profile disabled for new PSTN admissions.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not update PSTN profile enablement.");
    } finally {
      setBusy(false);
    }
  }

  const tierOptions = useMemo(() => PROFILE_TIERS.map((tier) => ({ tier, label: tierLabel(tier) })), []);

  if (loading) return <p className="text-sm text-text-muted">Loading PSTN voice profile readiness…</p>;

  return (
    <section className="space-y-5" aria-labelledby="pstn-profile-heading">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="pstn-profile-heading" className="text-xl font-semibold text-text">PSTN voice profiles</h2>
          <p className="mt-1 max-w-3xl text-sm text-text-muted">
            Configure Low and Standard composed profiles for future PSTN admissions. Premium remains on its existing Live configuration.
          </p>
        </div>
        <span className="rounded-full border border-surface-border-subtle bg-surface-raised px-3 py-1.5 font-mono text-xs text-text-muted">
          Environment: {environment || "unknown"}
        </span>
      </div>

      {error && (
        <div role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
          <p>{error}</p>
          <Button type="button" variant="secondary" className="mt-3" onClick={() => void loadProfiles()}>
            Retry
          </Button>
        </div>
      )}

      {status && <p role="status" aria-live="polite" className="text-sm text-text-muted">{status}</p>}

      {rows.length > 0 && (
        <>
          <div className="flex flex-wrap gap-2" role="group" aria-label="PSTN voice tiers">
            {tierOptions.map(({ tier, label }) => (
              <button
                key={tier}
                type="button"
                aria-pressed={selected === tier}
                disabled={busy}
                onClick={() => { setSelected(tier); setStatus(""); }}
                className={`min-h-11 rounded-xl border px-4 py-2 text-left text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40 ${selected === tier ? "border-accent-primary/40 bg-accent-dim text-text" : "border-surface-border-subtle bg-surface-card text-text-muted hover:border-accent-primary/25 hover:text-text"}`}
              >
                {label}
              </button>
            ))}
          </div>

          {!selectedRow ? (
            <DevCard title={tierLabel(selected)}>
              <p className="text-sm text-warning">No profile status was returned for this tier. Reload before editing.</p>
            </DevCard>
          ) : (
            <>
              <DevCard title={`${tierLabel(selected)} · PSTN configuration`} description="Configuration, readiness, rate coverage, and enablement are separate states.">
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <div data-testid="pstn-profile-configured" className="rounded-xl border border-surface-border-subtle bg-surface-raised/60 p-3">
                    <p className="text-xs text-text-subtle">Configuration</p>
                    <p className="mt-1 font-medium text-text">{isPremium ? "Existing Live path" : selectedRow.composedProfile ? `Saved · revision ${selectedRow.profileRevision}` : "Not configured"}</p>
                  </div>
                  <div data-testid="pstn-profile-readiness" className="rounded-xl border border-surface-border-subtle bg-surface-raised/60 p-3">
                    <p className="text-xs text-text-subtle">Readiness</p>
                    <p className="mt-1"><StatusPill tone={selectedRow.readiness.ready ? "good" : "warn"}>{selectedRow.readiness.ready ? "Ready" : "Blocked"}</StatusPill></p>
                  </div>
                  <div data-testid="pstn-profile-enablement" className="rounded-xl border border-surface-border-subtle bg-surface-raised/60 p-3">
                    <p className="text-xs text-text-subtle">Enablement</p>
                    <p className="mt-1"><StatusPill tone={isEnabled ? "good" : "muted"}>{isEnabled ? "Enabled" : "Disabled"}</StatusPill></p>
                  </div>
                  <div data-testid="pstn-profile-retail-rate" className="rounded-xl border border-surface-border-subtle bg-surface-raised/60 p-3">
                    <p className="text-xs text-text-subtle">Retail rate</p>
                    <p className="mt-1"><StatusPill tone={rateComplete ? "good" : "warn"}>{isPremium ? "Legacy rate preserved" : rateComplete ? "Native rate complete" : "Not configured"}</StatusPill></p>
                  </div>
                </div>

                {isPremium ? (
                  <div className="mt-4 rounded-xl border border-surface-border-subtle bg-surface-raised/40 p-4 text-sm text-text-muted">
                    Premium continues to use the existing Live stack and legacy billing rate. This profile editor does not change either value.
                  </div>
                ) : (
                  <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(280px,0.9fr)]">
                    <section className="space-y-4" aria-label="Profile definition">
                      <div className="grid gap-3 sm:grid-cols-2">
                        <TextField label="STT provider ID" value={draft.stt.provider} disabled={!canEdit} mono onChange={(value) => updateDraft((current) => ({ ...current, stt: { ...current.stt, provider: value } }))} />
                        <TextField label="STT exact model ID" value={draft.stt.model} disabled={!canEdit} mono onChange={(value) => updateDraft((current) => ({ ...current, stt: { ...current.stt, model: value } }))} />
                        <TextField label="LLM provider ID" value={draft.llm.provider} disabled={!canEdit} mono onChange={(value) => updateDraft((current) => ({ ...current, llm: { ...current.llm, provider: value } }))} />
                        <TextField label="LLM exact model ID" value={draft.llm.modelId} disabled={!canEdit} mono onChange={(value) => updateDraft((current) => ({ ...current, llm: { ...current.llm, modelId: value } }))} />
                        <TextField label="LLM API mode" value={draft.llm.apiMode} disabled={!canEdit} mono onChange={(value) => updateDraft((current) => ({ ...current, llm: { ...current.llm, apiMode: value } }))} />
                        <TextField label="Supported languages" value={draft.supportedLanguages.join(", ")} disabled={!canEdit} placeholder="Comma-separated verified locale IDs" mono onChange={(value) => updateDraft((current) => ({ ...current, supportedLanguages: splitList(value) }))} />
                      </div>

                      <div className="rounded-xl border border-surface-border-subtle p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <h3 className="font-medium text-text">TTS engines and model-specific voices</h3>
                            <p className="mt-1 text-xs text-text-muted">Add only verified combinations. Each voice belongs to the exact model listed above it.</p>
                          </div>
                          <Button
                            type="button"
                            variant="secondary"
                            disabled={!canEdit}
                            onClick={() => updateDraft((current) => ({ ...current, engines: [...current.engines, { id: "", label: "", models: [] }] }))}
                          >
                            Add engine
                          </Button>
                        </div>

                        {draft.engines.length === 0 ? (
                          <p className="mt-4 rounded-lg bg-surface-raised/50 p-3 text-sm text-text-muted">No TTS engines configured. Add an engine only after its account, model, language, voice, and media evidence is available.</p>
                        ) : (
                          <div className="mt-4 space-y-4">
                            {draft.engines.map((engine, engineIndex) => (
                              <fieldset key={`engine-${engineIndex}`} className="space-y-3 rounded-xl border border-surface-border-subtle bg-surface-raised/30 p-4">
                                <legend className="px-1 text-sm font-semibold text-text">Engine {engineIndex + 1}</legend>
                                <div className="flex flex-wrap items-end gap-3">
                                  <div className="grid min-w-0 flex-1 gap-3 sm:grid-cols-2">
                                    <TextField label="Engine ID" value={engine.id} disabled={!canEdit} mono onChange={(value) => updateEngine(engineIndex, { id: value })} />
                                    <TextField label="Display label" value={engine.label} disabled={!canEdit} onChange={(value) => updateEngine(engineIndex, { label: value })} />
                                  </div>
                                  <Button type="button" variant="secondary" disabled={!canEdit} onClick={() => updateDraft((current) => ({ ...current, engines: current.engines.filter((_, index) => index !== engineIndex) }))}>
                                    Remove engine
                                  </Button>
                                </div>

                                <div className="space-y-3 border-l border-surface-border pl-3">
                                  {engine.models.map((model, modelIndex) => (
                                    <div key={`model-${engineIndex}-${modelIndex}`} className="space-y-3 rounded-lg border border-surface-border-subtle bg-surface-card p-3">
                                      <div className="flex items-end gap-3">
                                        <div className="grid min-w-0 flex-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                                          <TextField label="Model alias ID" value={model.id} disabled={!canEdit} mono onChange={(value) => updateModel(engineIndex, modelIndex, { id: value })} />
                                          <TextField label="Display label" value={model.label} disabled={!canEdit} onChange={(value) => updateModel(engineIndex, modelIndex, { label: value })} />
                                          <TextField label="Provider ID" value={model.provider} disabled={!canEdit} mono onChange={(value) => updateModel(engineIndex, modelIndex, { provider: value })} />
                                          <TextField label="Exact model ID" value={model.model} disabled={!canEdit} mono onChange={(value) => updateModel(engineIndex, modelIndex, { model: value })} />
                                          <TextField label="API mode" value={model.apiMode} disabled={!canEdit} mono onChange={(value) => updateModel(engineIndex, modelIndex, { apiMode: value })} />
                                        </div>
                                        <Button type="button" variant="secondary" disabled={!canEdit} onClick={() => updateEngine(engineIndex, { models: engine.models.filter((_, index) => index !== modelIndex) })}>
                                          Remove model
                                        </Button>
                                      </div>

                                      <div className="space-y-2">
                                        <div className="flex flex-wrap items-center justify-between gap-2">
                                          <p className="text-xs font-medium text-text-muted">Voices for this exact model</p>
                                          <Button type="button" variant="secondary" disabled={!canEdit} onClick={() => updateEngine(engineIndex, { models: engine.models.map((item, index) => index === modelIndex ? { ...item, voices: [...item.voices, { id: "", label: "", providerVoiceId: "", languages: [] }] } : item) })}>
                                            Add voice
                                          </Button>
                                        </div>
                                        {model.voices.length === 0 ? <p className="text-xs text-text-subtle">No voice verified for this model.</p> : model.voices.map((voice, voiceIndex) => (
                                          <div key={`voice-${engineIndex}-${modelIndex}-${voiceIndex}`} className="grid gap-3 rounded-lg border border-surface-border-subtle p-3 sm:grid-cols-2 xl:grid-cols-4">
                                            <TextField label="Public voice ID" value={voice.id} disabled={!canEdit} mono onChange={(value) => updateVoice(engineIndex, modelIndex, voiceIndex, { id: value })} />
                                            <TextField label="Display label" value={voice.label} disabled={!canEdit} onChange={(value) => updateVoice(engineIndex, modelIndex, voiceIndex, { label: value })} />
                                            <TextField label="Provider voice ID" value={voice.providerVoiceId} disabled={!canEdit} mono onChange={(value) => updateVoice(engineIndex, modelIndex, voiceIndex, { providerVoiceId: value })} />
                                            <div className="flex items-end gap-2">
                                              <div className="min-w-0 flex-1">
                                                <TextField label="Verified languages" value={voice.languages.join(", ")} disabled={!canEdit} placeholder="Comma-separated locale IDs" mono onChange={(value) => updateVoice(engineIndex, modelIndex, voiceIndex, { languages: splitList(value) })} />
                                              </div>
                                              <Button type="button" variant="secondary" disabled={!canEdit} onClick={() => updateModel(engineIndex, modelIndex, { voices: model.voices.filter((_, index) => index !== voiceIndex) })}>
                                                Remove
                                              </Button>
                                            </div>
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  ))}
                                  <Button type="button" variant="secondary" disabled={!canEdit} onClick={() => updateEngine(engineIndex, { models: [...engine.models, { id: "", label: "", provider: "", model: "", apiMode: "", voices: [] }] })}>
                                    Add model
                                  </Button>
                                </div>
                              </fieldset>
                            ))}
                          </div>
                        )}
                      </div>
                    </section>

                    <aside className="space-y-4">
                      <div className="rounded-xl border border-surface-border-subtle p-4">
                        <h3 className="font-medium text-text">Readiness evidence</h3>
                        <p className="mt-1 text-xs text-text-muted">These attestations are admin-owned. Mark only checks completed for this exact profile.</p>
                        <div className="mt-3 grid gap-2">
                          <EvidenceToggle label="Account access confirmed for the approved Sarvam model" checked={draft.evidence.sarvamModelAccess} disabled={!canEdit} onChange={(checked) => updateDraft((current) => ({ ...current, evidence: { ...current.evidence, sarvamModelAccess: checked } }))} />
                          <EvidenceToggle label="Credential reference configured in server storage" checked={draft.evidence.credentialRefConfigured} disabled={!canEdit} onChange={(checked) => updateDraft((current) => ({ ...current, evidence: { ...current.evidence, credentialRefConfigured: checked } }))} />
                          <EvidenceToggle label="Selected STT model verified" checked={draft.evidence.sttVerified} disabled={!canEdit} onChange={(checked) => updateDraft((current) => ({ ...current, evidence: { ...current.evidence, sttVerified: checked } }))} />
                          <EvidenceToggle label="Model-specific TTS voice catalog verified" checked={draft.evidence.ttsCatalogVerified} disabled={!canEdit} onChange={(checked) => updateDraft((current) => ({ ...current, evidence: { ...current.evidence, ttsCatalogVerified: checked } }))} />
                          <EvidenceToggle label="Required tools verified for this profile" checked={draft.evidence.toolsVerified} disabled={!canEdit} onChange={(checked) => updateDraft((current) => ({ ...current, evidence: { ...current.evidence, toolsVerified: checked } }))} />
                          <EvidenceToggle label="Carrier, STT, LLM, and TTS capacity verified" checked={draft.evidence.capacityVerified} disabled={!canEdit} onChange={(checked) => updateDraft((current) => ({ ...current, evidence: { ...current.evidence, capacityVerified: checked } }))} />
                          <EvidenceToggle label="PSTN media formats and conversion verified" checked={draft.evidence.mediaFormatsVerified} disabled={!canEdit} onChange={(checked) => updateDraft((current) => ({ ...current, evidence: { ...current.evidence, mediaFormatsVerified: checked } }))} />
                        </div>
                      </div>

                      <div className="rounded-xl border border-surface-border-subtle p-4">
                        <div className="flex items-center justify-between gap-2">
                          <h3 className="font-medium text-text">Backend readiness blockers</h3>
                          <StatusPill tone={selectedRow.readiness.ready && blockers.length === 0 ? "good" : "warn"}>{selectedRow.readiness.ready && blockers.length === 0 ? "Clear" : `${blockers.length} blocker${blockers.length === 1 ? "" : "s"}`}</StatusPill>
                        </div>
                        {blockers.length === 0 && selectedRow.readiness.ready ? (
                          <p className="mt-3 text-sm text-text-muted">The server reports this saved profile as ready.</p>
                        ) : blockers.length === 0 ? (
                          <p className="mt-3 text-sm text-text-muted">The server has not marked this profile ready yet. Save the draft to refresh its checks.</p>
                        ) : (
                          <ul className="mt-3 space-y-2">
                            {blockers.map((blocker, index) => (
                              <li key={`${blocker.code}-${index}`} className="rounded-lg border border-amber-400/20 bg-amber-400/5 p-3">
                                <p className="text-sm text-text">{blocker.message}</p>
                                <p className="mt-1 font-mono text-[11px] text-text-subtle">{blocker.code}</p>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>

                      <div className={`rounded-xl border p-4 ${rateComplete ? "border-emerald-400/20 bg-emerald-400/5" : "border-amber-400/20 bg-amber-400/5"}`}>
                        <h3 className="font-medium text-text">Native PSTN price</h3>
                        <p className="mt-1 text-sm text-text-muted">
                          {rateComplete
                            ? "Backend reports complete native USD and INR per-minute prices for this tier."
                            : "No native per-tier PSTN price is configured. Activation stays blocked until both native prices are approved and saved."}
                        </p>
                        <p className="mt-2 text-xs text-text-subtle">Legacy Premium billing values are not edited from this profile screen.</p>
                      </div>
                    </aside>
                  </div>
                )}
              </DevCard>

              {!isPremium && (
                <div className="flex flex-wrap items-center gap-3">
                  {isEnabled ? (
                    <Button type="button" variant="secondary" disabled={busy} onClick={() => void setProfileEnabled(false)}>
                      {busy ? "Saving…" : "Disable for new calls"}
                    </Button>
                  ) : (
                    <>
                      <Button type="button" disabled={!dirty || busy} onClick={() => void saveProfile()}>
                        {busy ? "Saving…" : "Save disabled draft"}
                      </Button>
                      <Button type="button" variant="secondary" disabled={!canActivate || busy} onClick={() => void setProfileEnabled(true)}>
                        {busy ? "Saving…" : "Enable for new PSTN calls"}
                      </Button>
                    </>
                  )}
                  {dirty && <span className="text-sm text-warning">Unsaved profile changes</span>}
                </div>
              )}
            </>
          )}
        </>
      )}

      {!error && rows.length === 0 && (
        <DevCard title="No profile records">
          <p className="text-sm text-text-muted">The server returned no PSTN tier profiles. No defaults were created. Reload after profile storage is available.</p>
          <Button type="button" variant="secondary" className="mt-3" onClick={() => void loadProfiles()}>
            Reload profiles
          </Button>
        </DevCard>
      )}
    </section>
  );
}
