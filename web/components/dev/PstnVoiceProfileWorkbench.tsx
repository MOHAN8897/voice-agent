"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { DevCard } from "@/components/dev/DevCard";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";
import {
  DEFAULT_TIER_LABELS,
  DEFAULT_VOICE_DYNAMICS,
  FALLBACK_SPEED_KNOB,
  NATIVE_LIVE_KNOBS,
  StatusPill,
  allModels,
  defaultProfileForTier,
  dynamicsValue,
  formatInr,
  getVoicesForTtsProvider,
  knobPatch,
  normalizeDynamicsForKnobs,
  normalizeProfile,
  parseApiError,
  resolveModelKnobs,
  responseError,
  runtimeSignature,
  speedPresetsFor,
  type CatalogProvider,
  type CatalogResponse,
  type ComposedProfile,
  type ProfileTier,
  type ProfilesResponse,
  type TierProfileRow,
  type VerificationCheck,
  type VoiceDynamics,
} from "@/components/dev/voice-stack/profileModel";
import { TierResolvesToCard } from "@/components/dev/voice-stack/TierResolvesToCard";
import { PrewarmGreetingCard } from "@/components/dev/voice-stack/PrewarmGreetingCard";
import { PlatformPricesPanel } from "@/components/dev/voice-stack/PlatformPricesPanel";
import { TelephonyTrunkPanel } from "@/components/dev/voice-stack/TelephonyTrunkPanel";
import { TranscriptionPanel } from "@/components/dev/voice-stack/TranscriptionPanel";

const PROFILE_SECTIONS = [
  { id: "stack", label: "Voice Stack" },
  { id: "pricing", label: "Pricing" },
  { id: "telephony", label: "Telephony" },
  { id: "transcription", label: "Transcription" },
] as const;

type ProfileSectionId = (typeof PROFILE_SECTIONS)[number]["id"];

/** Unsaved, per-tier edits. Nothing reaches live calls until Save. */
type TierDraft = {
  profile: ComposedProfile;
  label: string;
  retail: string;
  supplier: string;
  web: string;
};

type PendingSave = {
  kind: "live" | "offline";
  tier: ProfileTier;
  payload: ComposedProfile;
  blockers?: string[];
};

function priceString(value: number | null | undefined): string {
  return value !== null && value !== undefined && Number.isFinite(Number(value)) ? String(value) : "";
}

function draftFromRow(row: TierProfileRow | undefined, tier: ProfileTier): TierDraft {
  const profile = normalizeProfile(row?.composedProfile, tier);
  // The card shows the price calls are billed today, so saving it makes the
  // tier card the single source even for tiers still priced by the rate table.
  if ((profile.retailRateInr === null || profile.retailRateInr === undefined) && row?.retailRate?.inrPaisePerMin) {
    profile.retailRateInr = Number((row.retailRate.inrPaisePerMin / 100).toFixed(2));
  }
  return {
    profile,
    label: row?.label || profile.label || DEFAULT_TIER_LABELS[tier] || tier,
    retail: priceString(profile.retailRateInr),
    supplier: priceString(profile.supplierCostInr),
    web: priceString(profile.webRetailRateInr),
  };
}

function tierDisplayName(row: TierProfileRow | undefined, tier: ProfileTier): string {
  return row?.label || DEFAULT_TIER_LABELS[tier] || tier.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function FieldError({ message, id }: { message?: string; id: string }) {
  if (!message) return null;
  return <p id={id} role="alert" className="mt-1 text-[11px] font-medium text-rose-300">{message}</p>;
}

export function PstnVoiceProfileWorkbench() {
  const [rows, setRows] = useState<TierProfileRow[]>([]);
  const [activeSection, setActiveSection] = useState<ProfileSectionId>("stack");
  const [environment, setEnvironment] = useState("");
  const [selected, setSelected] = useState<ProfileTier>("low");
  const [draft, setDraft] = useState<ComposedProfile>(defaultProfileForTier("low"));
  const [tierLabelInput, setTierLabelInput] = useState<string>("");
  const [retailRateInput, setRetailRateInput] = useState<string>("");
  const [supplierCostInput, setSupplierCostInput] = useState<string>("");
  const [webRateInput, setWebRateInput] = useState<string>("");
  const [dirtyTiers, setDirtyTiers] = useState<Record<string, boolean>>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [verification, setVerification] = useState<Record<string, VerificationCheck> | null>(null);
  const [providers, setProviders] = useState<CatalogProvider[]>([]);
  const [catalogError, setCatalogError] = useState("");
  const [catalogRefreshing, setCatalogRefreshing] = useState(false);
  const [voiceCategory, setVoiceCategory] = useState("");
  const [agentsByTier, setAgentsByTier] = useState<Record<string, number> | null>(null);
  const [pendingSave, setPendingSave] = useState<PendingSave | null>(null);
  const [pendingDisable, setPendingDisable] = useState(false);
  const editsRef = useRef<Record<string, TierDraft>>({});

  // Audio preview playback state
  const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null);
  const [previewLoadingId, setPreviewLoadingId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Knob audition state
  const [testText, setTestText] = useState("నమస్కారం! నేను మీ రియల్ ఎస్టేట్ సేల్స్ అసిస్టెంట్ మోహన్‌ని. మీకు ఎలా సహాయపడగలను?");
  const [testVoiceId, setTestVoiceId] = useState("");
  const [isTestingDynamics, setIsTestingDynamics] = useState(false);
  const [isPlayingDynamics, setIsPlayingDynamics] = useState(false);
  const dynamicsAudioRef = useRef<HTMLAudioElement | null>(null);

  // Stack duplication state
  const [showDuplicateModal, setShowDuplicateModal] = useState(false);
  const [duplicateNewSlug, setDuplicateNewSlug] = useState("");
  const [duplicateLabel, setDuplicateLabel] = useState("");

  const selectedRow = rows.find((r) => r.tier === selected);
  const isEnabled = selectedRow?.readiness.enabled === true;
  const dirty = dirtyTiers[selected] === true;
  const selectedName = tierLabelInput || tierDisplayName(selectedRow, selected);
  const agentCount = agentsByTier ? (agentsByTier[selected] ?? 0) : null;
  const agentPhrase = agentCount === null
    ? "Agents on this tier"
    : `${agentCount} agent${agentCount === 1 ? "" : "s"} on this tier`;

  const allDisplayTiers = useMemo(() => {
    const list: string[] = ["low", "medium", "premium"];
    rows.forEach((r) => {
      if (!list.includes(r.tier)) list.push(r.tier);
    });
    return list;
  }, [rows]);

  const loadCatalog = useCallback(async (refreshVoices = false) => {
    setCatalogRefreshing(true);
    try {
      const response = await portalFetch("dev", `/api/dev/stack/catalog${refreshVoices ? "?refreshVoices=true" : ""}`);
      if (!response.ok) throw new Error("The provider catalog could not be loaded.");
      const payload: CatalogResponse = await response.json();
      if (Array.isArray(payload.providers)) {
        setProviders(payload.providers);
        setCatalogError(payload.voiceInventory?.errors?.join(" ") || "");
      }
    } catch {
      setCatalogError("The provider catalog could not be loaded. Refresh before changing a stack.");
    } finally {
      setCatalogRefreshing(false);
    }
  }, []);

  const loadProfiles = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true);
    setError("");
    try {
      await refreshPortalSession("dev");
      const response = await portalFetch("dev", "/api/dev/stack/voice-profiles");
      if (!response.ok) throw new Error(await responseError(response));
      const payload = (await response.json()) as ProfilesResponse;
      if (!Array.isArray(payload.profiles)) throw new Error("Voice profiles response is incomplete.");
      setRows(payload.profiles);
      setEnvironment(typeof payload.environment === "string" ? payload.environment : "");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load voice profiles.");
    } finally {
      if (showLoading) setLoading(false);
    }
  }, []);

  const loadUsage = useCallback(async () => {
    try {
      const response = await portalFetch("dev", "/api/dev/stack/voice-profiles/usage");
      if (!response.ok) return;
      const payload = await response.json();
      if (payload?.available && payload.agentsByTier && typeof payload.agentsByTier === "object") {
        setAgentsByTier(payload.agentsByTier as Record<string, number>);
      }
    } catch {
      // The count only informs confirmations; saving never depends on it.
    }
  }, []);

  useEffect(() => {
    void loadProfiles();
    void loadCatalog();
    void loadUsage();
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
    };
  }, [loadProfiles, loadCatalog, loadUsage]);

  const applyDraft = useCallback((next: TierDraft) => {
    setDraft(next.profile);
    setTierLabelInput(next.label);
    setRetailRateInput(next.retail);
    setSupplierCostInput(next.supplier);
    setWebRateInput(next.web);
  }, []);

  useEffect(() => {
    const row = rows.find((r) => r.tier === selected);
    // Do not show an empty startup draft ahead of the saved profile response.
    if (!row && loading) return;
    applyDraft(editsRef.current[selected] ?? draftFromRow(row, selected));
  }, [rows, selected, loading, applyDraft]);

  /** Record an edit for the selected tier. Nothing is sent to the server. */
  function updateEdit(patch: Partial<TierDraft>) {
    const current = editsRef.current[selected] ?? draftFromRow(selectedRow, selected);
    const next: TierDraft = { ...current, ...patch };
    editsRef.current[selected] = next;
    applyDraft(next);
    setDirtyTiers((prev) => ({ ...prev, [selected]: true }));
    setStatus("");
  }

  function updateProfile(nextProfile: ComposedProfile) {
    updateEdit({ profile: nextProfile });
  }

  function clearFieldError(field: string) {
    setFieldErrors((prev) => {
      if (!(field in prev)) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  }

  function discardChanges() {
    delete editsRef.current[selected];
    setDirtyTiers((prev) => ({ ...prev, [selected]: false }));
    setFieldErrors({});
    setError("");
    applyDraft(draftFromRow(selectedRow, selected));
    setStatus(`Unsaved changes to ${selectedName} were discarded.`);
  }

  function switchSelectedTier(newTier: ProfileTier) {
    if (newTier === selected) return;
    // Edits stay in memory per tier and are marked "Unsaved" on the tier tab.
    setStatus("");
    setError("");
    setFieldErrors({});
    setVerification(null);
    setSelected(newTier);
  }

  // STT Options
  const availableSttProviders = useMemo(() => {
    return providers.filter((p) => (p.models?.stt?.length || 0) > 0).map((p) => {
      const suffix = !p.enabled || !p.configured ? " · setup required" : "";
      return { id: p.id, label: `${p.label}${suffix}` };
    });
  }, [providers]);

  const currentSttModels = useMemo(() => {
    const catModels = providers.find((p) => p.id === draft.stt.provider)?.models?.stt;
    return catModels && catModels.length > 0 ? catModels.map((m) => ({ id: m.id, label: m.label || m.id })) : [];
  }, [providers, draft.stt.provider]);

  // LLM Options
  const availableLlmProviders = useMemo(() => {
    return providers.filter((p) => (p.models?.llm?.length || 0) > 0).map((p) => {
      const suffix = !p.enabled || !p.configured ? " · setup required" : "";
      return { id: p.id, label: `${p.label}${suffix}` };
    });
  }, [providers]);

  const currentLlmModels = useMemo(() => {
    const catModels = providers.find((p) => p.id === draft.llm.provider)?.models?.llm;
    return catModels && catModels.length > 0
      ? catModels.map((m) => ({ id: m.id, label: m.label || m.id, apiMode: m.api_mode || "chat_completions_v1" }))
      : [];
  }, [providers, draft.llm.provider]);

  // TTS Options
  const currentTtsModelObj = draft.engines[0]?.models[0];
  const currentTtsProvider = currentTtsModelObj?.provider || "";
  const currentTtsModel = currentTtsModelObj?.model || "";

  const availableTtsProviders = useMemo(() => {
    return providers.filter((p) => (p.models?.tts?.length || 0) > 0).map((p) => {
      const isConfigured = p.enabled !== false && p.configured !== false;
      return { id: p.id, label: `${p.label}${isConfigured ? "" : " · setup or credits required"}`, hasWarning: !isConfigured };
    });
  }, [providers]);

  const currentTtsModels = useMemo(() => {
    const catModels = providers.find((p) => p.id === currentTtsProvider)?.models?.tts;
    return catModels && catModels.length > 0
      ? catModels.map((m) => ({ id: m.id, label: m.label || m.id, apiMode: m.api_mode || "websocket" }))
      : [];
  }, [providers, currentTtsProvider]);

  // Native realtime voice (Gemini Live / OpenAI Realtime) bypasses the composed
  // TTS engine, so only the live voice pace knob applies.
  const isNativeRealtimeLlm = draft.llm.apiMode === "websocket";
  const currentTtsKnobs = useMemo(() => {
    if (isNativeRealtimeLlm) return NATIVE_LIVE_KNOBS;
    return resolveModelKnobs(providers, currentTtsProvider, currentTtsModel) || [FALLBACK_SPEED_KNOB];
  }, [providers, currentTtsProvider, currentTtsModel, isNativeRealtimeLlm]);
  const speedKnob = currentTtsKnobs.find((spec) => spec.key === "speed") || FALLBACK_SPEED_KNOB;
  const secondaryKnobs = currentTtsKnobs.filter((spec) => spec.key !== "speed");
  const draftModels = allModels(draft);
  const knobTargets = isNativeRealtimeLlm
    ? "the native live voice"
    : draftModels.map((model) => `${model.provider} / ${model.model}`).join(", ") || "the selected speech model";

  /** Validate and assemble the save payload; returns null and marks fields on error. */
  function buildPayload(): ComposedProfile | null {
    const edit = editsRef.current[selected] ?? draftFromRow(selectedRow, selected);
    const activeDraft = edit.profile;
    const errors: Record<string, string> = {};
    const isNativeLive = activeDraft.llm.apiMode === "websocket";
    const primary = activeDraft.engines[0]?.models[0];
    const ttsProv = primary?.provider || "";
    const ttsMdl = primary?.model || "";
    const matchedTtsModel = providers.find((entry) => entry.id === ttsProv)?.models?.tts?.find((entry) => entry.id === ttsMdl);
    const languages = activeDraft.supportedLanguages.length > 0
      ? activeDraft.supportedLanguages
      : [...new Set((matchedTtsModel?.voices || []).flatMap((voice) => voice.languages))];
    const catalogVoices = getVoicesForTtsProvider(providers, ttsProv, ttsMdl, languages, primary?.voices);
    // Never substitute voices the catalog does not offer for this model.
    const voices = catalogVoices.length ? catalogVoices : (primary?.voices || []);

    if (!isNativeLive && (!activeDraft.stt.model || !activeDraft.stt.provider)) errors["stt.model"] = "Choose a speech recognition model.";
    if (!activeDraft.llm.modelId) errors["llm.modelId"] = "Choose a conversation model.";
    if (!ttsProv || !ttsMdl) errors["tts.model"] = "Choose a speech output model.";
    else if (!voices.length) errors["tts.model"] = "This speech model has no voices for the tier languages. Refresh provider voices or pick another model.";

    const retail = edit.retail.trim();
    const retailNum = Number(retail);
    if (!retail) errors.retailRateInr = "Set the phone call price for this tier.";
    else if (!Number.isFinite(retailNum) || retailNum <= 0) errors.retailRateInr = "Phone call price must be greater than zero.";
    const supplier = edit.supplier.trim();
    const supplierNum = Number(supplier);
    if (supplier && (!Number.isFinite(supplierNum) || supplierNum < 0)) errors.supplierCostInr = "Supplier cost must be zero or more.";
    const web = edit.web.trim();
    const webNum = Number(web);
    if (web && (!Number.isFinite(webNum) || webNum <= 0)) errors.webRetailRateInr = "Web call price must be greater than zero, or blank to use the platform default.";

    setFieldErrors(errors);
    if (Object.keys(errors).length) {
      setError("Fix the highlighted fields before saving.");
      return null;
    }

    const singleModel = allModels(activeDraft).length <= 1;
    const targetKnobs = isNativeLive ? NATIVE_LIVE_KNOBS : resolveModelKnobs(providers, ttsProv, ttsMdl);
    const labelVal = edit.label.trim() || DEFAULT_TIER_LABELS[selected] || selected;
    return {
      schemaVersion: 1,
      enabled: selectedRow?.readiness?.enabled === true,
      label: labelVal,
      webRetailRateInr: web ? webNum : null,
      retailRateInr: retailNum,
      supplierCostInr: supplier ? supplierNum : null,
      supportedLanguages: languages,
      stt: { provider: activeDraft.stt.provider, model: activeDraft.stt.model },
      llm: { provider: activeDraft.llm.provider, modelId: activeDraft.llm.modelId, apiMode: activeDraft.llm.apiMode },
      engines: [
        {
          id: activeDraft.engines[0]?.id || ttsProv,
          label: activeDraft.engines[0]?.label || ttsProv,
          models: [
            {
              id: primary?.id || ttsMdl,
              label: primary?.label || ttsMdl,
              provider: ttsProv,
              model: ttsMdl,
              apiMode: primary?.apiMode || matchedTtsModel?.api_mode || (isNativeLive ? "websocket" : ""),
              voices,
            },
            ...(activeDraft.engines[0]?.models.slice(1) || []),
          ],
        },
        ...activeDraft.engines.slice(1),
      ],
      evidence: { ...activeDraft.evidence },
      // With one speech model the knobs are trimmed to what it supports. With
      // several, the server keeps the union and clamps per model on each call.
      voiceDynamics: singleModel && targetKnobs
        ? normalizeDynamicsForKnobs(activeDraft.voiceDynamics, targetKnobs)
        : (activeDraft.voiceDynamics || { ...DEFAULT_VOICE_DYNAMICS }),
    };
  }

  function requestSave() {
    if (busy) return;
    setError("");
    setStatus("");
    const payload = buildPayload();
    if (!payload) return;
    if (isEnabled) {
      const runtimeChanged = selectedRow?.native !== true
        && runtimeSignature(selectedRow?.composedProfile) !== runtimeSignature(payload);
      setPendingSave({ kind: runtimeChanged ? "offline" : "live", tier: selected, payload });
      return;
    }
    void commitSave(payload, selected, false);
  }

  async function commitSave(payload: ComposedProfile, tier: ProfileTier, confirmTakeOffline: boolean) {
    setBusy(true);
    setError("");
    try {
      const row = rows.find((r) => r.tier === tier);
      const response = await portalFetch("dev", `/api/dev/stack/voice-profiles/${tier}`, {
        method: "PUT",
        body: JSON.stringify({
          expectedRevision: row?.profileRevision ?? 0,
          composedProfile: payload,
          confirmTakeOffline,
        }),
      });
      if (!response.ok) {
        const apiError = await parseApiError(response);
        if (apiError.code === "change_takes_tier_offline" && !confirmTakeOffline) {
          const blockers = Array.isArray(apiError.details.blockers)
            ? (apiError.details.blockers as Array<{ message?: string }>).map((b) => String(b?.message || "")).filter(Boolean)
            : [];
          setPendingSave({ kind: "offline", tier, payload, blockers });
          return;
        }
        if (apiError.field) setFieldErrors((prev) => ({ ...prev, [apiError.field as string]: apiError.message }));
        setError(apiError.code === "revision_conflict"
          ? "Someone else saved this tier. Discard your changes to load the latest version, then edit again."
          : apiError.message);
        return;
      }
      const saved = (await response.json().catch(() => null)) as TierProfileRow | null;
      delete editsRef.current[tier];
      setDirtyTiers((prev) => ({ ...prev, [tier]: false }));
      setFieldErrors({});
      await loadProfiles(false);
      void loadUsage();
      const name = tierDisplayName(row, tier);
      if (confirmTakeOffline && saved?.readiness && !saved.readiness.enabled) {
        setStatus(`${name} saved and taken offline. Verify the setup, then enable it again.`);
      } else {
        setStatus(`${name} saved (revision ${saved?.profileRevision ?? "updated"}). New calls use it now.`);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save tier configuration.");
    } finally {
      setBusy(false);
      setPendingSave(null);
    }
  }

  function handleSttProviderChange(provider: string) {
    const models = providers.find((entry) => entry.id === provider)?.models?.stt || [];
    const firstModel = models[0]?.id;
    if (!firstModel) return;
    clearFieldError("stt.model");
    updateProfile({ ...draft, stt: { provider, model: firstModel } });
  }

  function handleSttModelChange(model: string) {
    clearFieldError("stt.model");
    updateProfile({ ...draft, stt: { ...draft.stt, model } });
  }

  function handleLlmProviderChange(provider: string) {
    const models = providers.find((entry) => entry.id === provider)?.models?.llm || [];
    const first = models[0];
    if (!first) return;
    const nextKnobs = first.api_mode === "websocket"
      ? NATIVE_LIVE_KNOBS
      : (resolveModelKnobs(providers, currentTtsProvider, currentTtsModel) || [FALLBACK_SPEED_KNOB]);
    clearFieldError("llm.modelId");
    updateProfile({
      ...draft,
      llm: { provider, modelId: first.id, apiMode: first.api_mode || "" },
      voiceDynamics: normalizeDynamicsForKnobs(draft.voiceDynamics, nextKnobs),
    });
  }

  function handleLlmModelChange(modelId: string) {
    const matched = currentLlmModels.find((m) => m.id === modelId);
    const apiMode = matched?.apiMode || "chat_completions_v1";
    const nextKnobs = apiMode === "websocket"
      ? NATIVE_LIVE_KNOBS
      : (resolveModelKnobs(providers, currentTtsProvider, currentTtsModel) || [FALLBACK_SPEED_KNOB]);
    clearFieldError("llm.modelId");
    updateProfile({
      ...draft,
      llm: { ...draft.llm, modelId, apiMode },
      voiceDynamics: normalizeDynamicsForKnobs(draft.voiceDynamics, nextKnobs),
    });
  }

  function handleTtsProviderChange(provider: string) {
    const models = providers.find((entry) => entry.id === provider)?.models?.tts || [];
    const first = models[0];
    if (!first) return;
    const voices = getVoicesForTtsProvider(providers, provider, first.id, []);
    const nextKnobs = draft.llm.apiMode === "websocket"
      ? NATIVE_LIVE_KNOBS
      : (resolveModelKnobs(providers, provider, first.id) || [FALLBACK_SPEED_KNOB]);
    clearFieldError("tts.model");
    updateProfile({
      ...draft,
      supportedLanguages: [...new Set(voices.flatMap((voice) => voice.languages))],
      voiceDynamics: normalizeDynamicsForKnobs(draft.voiceDynamics, nextKnobs),
      engines: [
        {
          id: provider,
          label: provider === "sarvam" ? "Sarvam Bulbul" : provider === "gemini" ? "Gemini TTS" : provider === "gnani" ? "Gnani.ai Timbre" : "Cartesia Sonic",
          models: [{ id: first.id, label: first.id, provider, model: first.id, apiMode: first.api_mode || "", voices }],
        },
      ],
    });
  }

  function handleTtsModelChange(model: string) {
    const matched = currentTtsModels.find((m) => m.id === model);
    const voices = getVoicesForTtsProvider(providers, currentTtsProvider, model, []);
    const nextKnobs = draft.llm.apiMode === "websocket"
      ? NATIVE_LIVE_KNOBS
      : (resolveModelKnobs(providers, currentTtsProvider, model) || [FALLBACK_SPEED_KNOB]);
    const engine = { ...(draft.engines[0] || { id: currentTtsProvider, label: currentTtsProvider, models: [] }) };
    engine.models = [{ id: model, label: model, provider: currentTtsProvider, model, apiMode: matched?.apiMode || "websocket", voices }];
    clearFieldError("tts.model");
    updateProfile({
      ...draft,
      supportedLanguages: [...new Set(voices.flatMap((voice) => voice.languages))],
      voiceDynamics: normalizeDynamicsForKnobs(draft.voiceDynamics, nextKnobs),
      engines: [engine],
    });
  }

  function handleTierLabelChange(val: string) {
    updateEdit({ label: val });
  }

  function handleRetailRateChange(val: string) {
    clearFieldError("retailRateInr");
    updateEdit({ retail: val });
  }

  function handleSupplierCostChange(val: string) {
    clearFieldError("supplierCostInr");
    updateEdit({ supplier: val });
  }

  function handleWebRateChange(val: string) {
    clearFieldError("webRetailRateInr");
    updateEdit({ web: val });
  }

  function handleDynamicsChange(patch: Partial<VoiceDynamics>) {
    const merged: VoiceDynamics = {
      speed: draft.voiceDynamics?.speed ?? 1.0,
      pitch: draft.voiceDynamics?.pitch,
      temperature: draft.voiceDynamics?.temperature,
      emotion: draft.voiceDynamics?.emotion,
      volume: draft.voiceDynamics?.volume,
      ...patch,
    };
    updateProfile({ ...draft, voiceDynamics: normalizeDynamicsForKnobs(merged, currentTtsKnobs) });
  }

  async function handleLoadRecommended() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await portalFetch("dev", `/api/dev/stack/voice-profiles/${selected}/template`);
      if (!response.ok) throw new Error(await responseError(response));
      const payload = await response.json();
      const recommended = normalizeProfile(payload?.composedProfile as ComposedProfile, selected);
      // Keep the operator's name and prices; only the stack is replaced.
      recommended.label = draft.label;
      updateEdit({ profile: recommended });
      setStatus("Recommended setup loaded as unsaved changes. Review it, then save.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load the recommended setup.");
    } finally {
      setBusy(false);
    }
  }

  async function handleTestSpeedDynamics() {
    if (isPlayingDynamics && dynamicsAudioRef.current) {
      dynamicsAudioRef.current.pause();
      dynamicsAudioRef.current = null;
      setIsPlayingDynamics(false);
      return;
    }
    if (dynamicsAudioRef.current) {
      dynamicsAudioRef.current.pause();
      dynamicsAudioRef.current = null;
    }
    setIsTestingDynamics(true);
    setError("");
    try {
      const activeVoice = currentVoices.find((voice) => voice.id === testVoiceId) || currentVoices[0];
      if (!activeVoice) throw new Error("Choose a verified voice first.");
      const dyn = normalizeDynamicsForKnobs(draft.voiceDynamics || DEFAULT_VOICE_DYNAMICS, currentTtsKnobs);
      const response = await portalFetch("dev", "/api/dev/stack/voice-preview", {
        method: "POST",
        body: JSON.stringify({
          provider: currentTtsProvider,
          model: currentTtsModel,
          voiceId: activeVoice.providerVoiceId,
          text: testText,
          language: activeVoice.languages[0],
          speed: dyn.speed,
          pitch: dyn.pitch,
          temperature: dyn.temperature,
          emotion: dyn.emotion,
          volume: dyn.volume,
        }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const data = await response.json();
      const b64 = data.audio_base64;
      if (!b64) throw new Error("No audition audio returned by server.");
      const audio = new Audio(`data:audio/wav;base64,${b64}`);
      dynamicsAudioRef.current = audio;
      audio.onended = () => {
        setIsPlayingDynamics(false);
        dynamicsAudioRef.current = null;
      };
      audio.onerror = () => {
        setIsPlayingDynamics(false);
        dynamicsAudioRef.current = null;
      };
      await audio.play();
      setIsPlayingDynamics(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate the knob preview.");
    } finally {
      setIsTestingDynamics(false);
    }
  }

  async function handleDeleteTier(tierToDelete: string) {
    if (["low", "medium", "premium"].includes(tierToDelete)) {
      setError("Core tiers (Economical, Standard, and Flagship) cannot be deleted.");
      return;
    }
    const tierRow = rows.find((r) => r.tier === tierToDelete);
    const label = tierDisplayName(tierRow, tierToDelete);
    const count = agentsByTier ? (agentsByTier[tierToDelete] ?? 0) : null;
    const usage = count === null ? "" : ` ${count} agent${count === 1 ? "" : "s"} use it and will stop placing calls.`;
    if (!window.confirm(`Delete the tier "${label}" (${tierToDelete})? This permanently removes it.${usage}`)) {
      return;
    }
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const response = await portalFetch("dev", `/api/dev/stack/voice-profiles/${tierToDelete}`, { method: "DELETE" });
      if (!response.ok) throw new Error(await responseError(response));
      delete editsRef.current[tierToDelete];
      setDirtyTiers((prev) => ({ ...prev, [tierToDelete]: false }));
      await loadProfiles(false);
      switchSelectedTier("medium");
      setStatus(`Tier "${label}" (${tierToDelete}) was deleted.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete tier.");
    } finally {
      setBusy(false);
    }
  }

  async function handleVerifyReadiness() {
    if (busy || dirty || selectedRow?.profileRevision == null) return;
    setBusy(true);
    setError("");
    setVerification(null);
    try {
      const response = await portalFetch("dev", `/api/dev/stack/voice-profiles/${selected}/verify`, {
        method: "POST", body: JSON.stringify({ expectedRevision: selectedRow.profileRevision }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const result = await response.json();
      setVerification(result.checks);
      const verified = result.profile as TierProfileRow;
      await loadProfiles(false);
      setStatus(verified.readiness.ready
        ? `${selectedName} meets every readiness requirement.${verified.readiness.enabled ? "" : " Enable it to offer it to tenants."}`
        : "Checks completed. Review the remaining requirements in the Resolves to card.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Verification could not finish. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleActivation(newEnabledState: boolean) {
    if (busy) return;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const response = await portalFetch("dev", `/api/dev/stack/voice-profiles/${selected}/activation`, {
        method: "PUT",
        body: JSON.stringify({ expectedRevision: selectedRow?.profileRevision ?? 0, enabled: newEnabledState }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      await response.json().catch(() => null);
      await loadProfiles(false);
      setStatus(newEnabledState
        ? `${selectedName} is enabled and offered to tenants.`
        : `${selectedName} is disabled and hidden from tenants.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not update tier activation.");
      void loadProfiles(false);
    } finally {
      setBusy(false);
      setPendingDisable(false);
    }
  }

  const currentVoices = useMemo(() => {
    return getVoicesForTtsProvider(providers, currentTtsProvider, currentTtsModel, draft.supportedLanguages, currentTtsModelObj?.voices);
  }, [providers, currentTtsProvider, currentTtsModel, currentTtsModelObj?.voices, draft.supportedLanguages]);

  const currentModelInventory = useMemo(() => {
    const inventory = providers.find((entry) => entry.id === currentTtsProvider)?.models?.tts?.find((entry) => entry.id === currentTtsModel)?.voices || [];
    return inventory.map((voice) => ({ ...voice,
      id: currentTtsModelObj?.voices.find((item) => item.providerVoiceId === voice.providerVoiceId)?.id || voice.id,
    }));
  }, [providers, currentTtsProvider, currentTtsModel, currentTtsModelObj?.voices]);

  useEffect(() => { setVoiceCategory(""); }, [currentTtsProvider, currentTtsModel]);

  const handlePlayVoicePreview = useCallback(async (voiceId: string) => {
    if (playingVoiceId === voiceId && audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
      setPlayingVoiceId(null);
      return;
    }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setPreviewLoadingId(voiceId);
    setError("");
    try {
      const voice = currentVoices.find((item) => item.id === voiceId);
      if (!voice) throw new Error("Choose a current model voice.");
      const response = await portalFetch("dev", "/api/dev/stack/voice-preview", {
        method: "POST",
        body: JSON.stringify({
          provider: currentTtsProvider,
          model: currentTtsModel,
          voiceId: voice.providerVoiceId,
          language: voice.languages[0],
        }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const data = await response.json();
      const b64 = data.audio_base64;
      if (!b64) throw new Error("No preview audio returned from server.");
      const audio = new Audio(`data:audio/wav;base64,${b64}`);
      audioRef.current = audio;
      audio.onended = () => {
        setPlayingVoiceId(null);
        audioRef.current = null;
      };
      audio.onerror = () => {
        setPlayingVoiceId(null);
        audioRef.current = null;
      };
      await audio.play();
      setPlayingVoiceId(voiceId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to play voice preview.");
    } finally {
      setPreviewLoadingId(null);
    }
  }, [currentTtsProvider, currentTtsModel, currentVoices, playingVoiceId]);

  function handleOpenDuplicateModal() {
    const basePrefix = selected.slice(0, 10).replace(/[^a-z0-9_]/g, "_");
    const existingTiers = new Set(rows.map((r) => r.tier));
    let idx = 1;
    while (existingTiers.has(`${basePrefix}_copy_${idx}`)) idx++;
    setDuplicateNewSlug(`${basePrefix}_copy_${idx}`.slice(0, 20));
    setDuplicateLabel(`${selectedName} (Copy ${idx})`);
    setShowDuplicateModal(true);
  }

  async function handleConfirmDuplicate() {
    if (busy) return;
    const slug = duplicateNewSlug.trim().toLowerCase().replace(/[^a-z0-9_]/g, "_").slice(0, 20);
    if (!slug) {
      setError("Enter a valid identifier for the new tier (lowercase letters, numbers and underscores).");
      return;
    }
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const response = await portalFetch("dev", "/api/dev/stack/voice-profiles/duplicate", {
        method: "POST",
        body: JSON.stringify({ sourceTier: selected, targetTier: slug, targetLabel: duplicateLabel.trim() || undefined }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const data = await response.json();
      const createdTier = data.tier || slug;
      await loadProfiles(false);
      switchSelectedTier(createdTier);
      setShowDuplicateModal(false);
      setStatus(`Created "${duplicateLabel || createdTier}" (${createdTier}) from the saved ${selectedName} setup. It starts disabled.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not duplicate tier.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-text-muted">Loading voice stack configurations…</p>;
  }

  return (
    <section className="space-y-6" aria-labelledby="pstn-profile-heading">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="pstn-profile-heading" className="text-xl font-semibold text-text">
            Voice Stacks & Tier Configuration
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-text-muted">
            Each tier bundles speech recognition, a conversation model, speech output and a price. Edits stay as unsaved
            changes until you save; tenants only ever see enabled, ready tiers.
          </p>
        </div>
        <span className="rounded-full border border-surface-border-subtle bg-surface-raised px-3 py-1.5 font-mono text-xs text-text-muted">
          Environment: {environment || "development"}
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

      {status && (
        <div role="status" aria-live="polite" className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-300">
          {status}
        </div>
      )}

      {/* Tier Selector Tabs */}
      <div className="flex flex-wrap gap-3" role="group" aria-label="Select voice stack tier">
        {allDisplayTiers.map((tier) => {
          const row = rows.find((r) => r.tier === tier);
          const active = selected === tier;
          const tierEnabled = row?.readiness?.enabled === true;
          const tierReady = row?.readiness?.ready === true;
          const label = tierDisplayName(row, tier);
          const tierDirty = dirtyTiers[tier] === true;

          return (
            <button
              key={tier}
              type="button"
              disabled={busy}
              onClick={() => switchSelectedTier(tier)}
              className={`flex min-w-[200px] flex-col rounded-xl border p-3.5 text-left transition-all ${
                active
                  ? "border-accent-primary bg-accent-dim shadow-md"
                  : "border-surface-border bg-surface-card hover:border-surface-border-subtle hover:bg-surface-raised/40"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs uppercase tracking-wider text-text-subtle font-mono">{tier}</span>
                <span
                  className={`size-2 rounded-full ${
                    tierEnabled ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]" : "bg-neutral-600"
                  }`}
                />
              </div>
              <span className="mt-1 font-semibold text-sm text-text">{label}</span>
              <div className="mt-2 flex items-center gap-2">
                <span className={`text-[11px] font-medium ${tierEnabled ? (tierReady ? "text-emerald-400" : "text-rose-300") : "text-text-muted"}`}>
                  {tierEnabled ? (tierReady ? "Live" : "Enabled, not ready: calls fail") : "Offline"}
                </span>
                <span className="font-mono text-[11px] text-text-subtle">· {formatInr(row?.retailRate?.inrPaisePerMin)}</span>
              </div>
              {tierDirty && <span className="mt-1 text-[11px] font-semibold text-amber-300">Unsaved changes</span>}
            </button>
          );
        })}
      </div>

      <div
        role="tablist"
        aria-label="Voice stack configuration sections"
        className="flex flex-wrap gap-1.5 rounded-2xl border border-surface-border bg-surface-card p-1.5"
      >
        {PROFILE_SECTIONS.map((tab) => {
          const active = activeSection === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`pstn-section-tab-${tab.id}`}
              aria-selected={active}
              aria-controls={`pstn-section-panel-${tab.id}`}
              tabIndex={active ? 0 : -1}
              onClick={() => setActiveSection(tab.id)}
              onKeyDown={(event) => {
                if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
                event.preventDefault();
                const current = PROFILE_SECTIONS.findIndex((section) => section.id === activeSection);
                const step = event.key === "ArrowRight" ? 1 : -1;
                const next = PROFILE_SECTIONS[(current + step + PROFILE_SECTIONS.length) % PROFILE_SECTIONS.length];
                setActiveSection(next.id);
                document.getElementById(`pstn-section-tab-${next.id}`)?.focus();
              }}
              className={`flex-1 rounded-xl px-4 py-2.5 text-sm font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/50 ${
                active
                  ? "bg-accent-dim text-text shadow-sm ring-1 ring-accent-primary/40"
                  : "text-text-muted hover:bg-surface-raised/60 hover:text-text"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Selected Tier Management Panel */}
      <div
        role="tabpanel"
        id="pstn-section-panel-stack"
        aria-labelledby="pstn-section-tab-stack"
        hidden={activeSection !== "stack"}
      >
      <DevCard
        title={`${selectedName} configuration`}
        description="Edits are kept as unsaved changes. Save applies them to new calls on this tier; Discard restores the saved version."
      >
        {/* Tier Controls Bar (Name + Enable/Disable Toggle + Duplicate Stack) */}
        <div className="rounded-xl border border-surface-border bg-surface-raised/50 p-4 mb-6">
          <div className="grid gap-4 md:grid-cols-3 items-center">
            {/* Custom Name */}
            <div>
              <label htmlFor="tier-display-name" className="block text-xs font-medium text-text-muted mb-1.5">
                Tier display name (visible to tenants)
              </label>
              <input
                id="tier-display-name"
                type="text"
                value={tierLabelInput}
                onChange={(e) => handleTierLabelChange(e.target.value)}
                placeholder={DEFAULT_TIER_LABELS[selected] || selected}
                className="w-full rounded-xl border border-surface-border bg-surface-panel px-3 py-2 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
              />
            </div>

            {/* Enable/Disable Status & Toggle */}
            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-text-muted">Tier status for tenants</span>
              <div className="flex items-center gap-3">
                <StatusPill tone={isEnabled ? "good" : "muted"}>
                  {isEnabled ? "Enabled" : "Disabled (hidden)"}
                </StatusPill>
                <button
                  type="button"
                  disabled={busy || dirty}
                  title={dirty ? "Save or discard your changes first." : undefined}
                  onClick={() => (isEnabled ? setPendingDisable(true) : void handleToggleActivation(true))}
                  className={`rounded-lg px-3 py-1 text-xs font-semibold transition-colors ${
                    isEnabled
                      ? "border border-amber-500/30 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20"
                      : "border border-emerald-500/30 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20"
                  }`}
                >
                  {isEnabled ? "Disable tier" : "Enable tier"}
                </button>
              </div>
              {dirty && <span className="text-[11px] text-text-subtle">Save or discard changes before enabling or disabling.</span>}
            </div>

            {/* Tier Actions (Duplicate + Delete) */}
            <div className="flex flex-col gap-1.5 md:items-end">
              <span className="text-xs font-medium text-text-muted">Tier actions</span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={handleOpenDuplicateModal}
                  className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-surface-border bg-surface-card px-3 py-1.5 text-xs font-semibold text-text hover:border-surface-border-subtle hover:bg-surface-raised transition-colors shadow-sm"
                  title="Replicate this stack configuration as a new tier"
                >
                  Duplicate
                </button>
                {!["low", "medium", "premium"].includes(selected) && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void handleDeleteTier(selected)}
                    className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-300 hover:bg-rose-500/20 transition-colors shadow-sm"
                    title="Permanently delete this custom tier"
                  >
                    Delete tier
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="mb-6">
          <TierResolvesToCard row={selectedRow} agentCount={agentCount} hasUnsavedChanges={dirty} />
        </div>

        {/* Tier Pricing & Provider Cost Configuration */}
        <div className="rounded-xl border border-surface-border bg-surface-card p-4 mb-6 shadow-sm">
          <div className="flex items-center justify-between border-b border-surface-border-subtle pb-3 mb-4">
            <h3 className="text-sm font-semibold text-text">Tier price</h3>
            <span className="text-[11px] text-text-subtle">The only place this tier&apos;s price is edited</span>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <label htmlFor="tier-retail-rate" className="block text-xs font-semibold text-text mb-1">
                Phone call price (₹/min)
                <span className="text-text-muted font-normal ml-1">· billed to tenants</span>
              </label>
              <div className="relative">
                <span className="absolute left-3 top-2.5 text-sm font-semibold text-text-muted">₹</span>
                <input
                  id="tier-retail-rate"
                  type="number"
                  step="0.05"
                  min="0.01"
                  aria-invalid={Boolean(fieldErrors.retailRateInr)}
                  aria-describedby={fieldErrors.retailRateInr ? "tier-retail-rate-error" : undefined}
                  value={retailRateInput}
                  onChange={(e) => handleRetailRateChange(e.target.value)}
                  placeholder="e.g. 5.00"
                  className="w-full rounded-xl border border-surface-border bg-surface-panel pl-7 pr-3 py-2 text-sm text-text font-mono focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
                />
              </div>
              <FieldError id="tier-retail-rate-error" message={fieldErrors.retailRateInr} />
              <p className="mt-1 text-[11px] text-text-subtle">
                Deducted from tenant wallets per minute. Saving a core tier price also publishes a new billing rate version.
                Billed now: {formatInr(selectedRow?.retailRate?.inrPaisePerMin)}.
              </p>
            </div>

            <div>
              <label htmlFor="tier-web-rate" className="block text-xs font-semibold text-text mb-1">Web agent price (₹/min)</label>
              <input id="tier-web-rate" type="number" min="0.01" step="0.01" value={webRateInput}
                aria-invalid={Boolean(fieldErrors.webRetailRateInr)}
                onChange={(event) => handleWebRateChange(event.target.value)}
                placeholder={selectedRow?.webRetailRate?.inrPaisePerMin ? `${selectedRow.webRetailRate.inrPaisePerMin / 100}` : "Use saved web default"}
                className="w-full rounded-xl border border-surface-border bg-surface-panel px-3 py-2 text-sm text-text font-mono" />
              <FieldError id="tier-web-rate-error" message={fieldErrors.webRetailRateInr} />
              <p className="mt-1 text-[11px] text-text-subtle">Browser and embedded web calls on this stack. Blank uses the saved global web default. Each call locks its price at start.</p>
            </div>

            <div>
              <label htmlFor="tier-supplier-cost" className="block text-xs font-semibold text-text mb-1">
                Estimated supplier cost (₹/min)
                <span className="text-text-muted font-normal ml-1">· admin only</span>
              </label>
              <div className="relative">
                <span className="absolute left-3 top-2.5 text-sm font-semibold text-text-muted">₹</span>
                <input
                  id="tier-supplier-cost"
                  type="number"
                  step="0.05"
                  min="0"
                  aria-invalid={Boolean(fieldErrors.supplierCostInr)}
                  value={supplierCostInput}
                  onChange={(e) => handleSupplierCostChange(e.target.value)}
                  placeholder="e.g. 1.80"
                  className="w-full rounded-xl border border-surface-border bg-surface-panel pl-7 pr-3 py-2 text-sm text-text font-mono focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
                />
              </div>
              <FieldError id="tier-supplier-cost-error" message={fieldErrors.supplierCostInr} />
              <p className="mt-1 text-[11px] text-text-subtle">
                Estimated cost of trunk, recognition, model and speech, used for margin tracking. Never shown to tenants.
              </p>
            </div>
          </div>
        </div>

        {isNativeRealtimeLlm && (
          <div className="rounded-xl border border-indigo-500/30 bg-indigo-500/10 p-4 mb-6 text-xs text-indigo-100">
            <h4 className="font-semibold text-indigo-200">Native audio tier</h4>
            <p className="mt-1 text-indigo-200/90">
              One live model listens, reasons and speaks over a single session, so there is no separate recognition or speech
              engine to verify. Readiness checks the provider, model, voices and price; confirm call quality in Test Studio.
            </p>
          </div>
        )}

        {/* 3 Pipeline Component Dropdowns */}
        <div className="grid gap-6 md:grid-cols-3">
          {/* 1. Speech-to-Text (STT) */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-4">
            <div className="flex items-center justify-between border-b border-surface-border-subtle pb-3">
              <div className="flex items-center gap-2">
                <span className="flex size-6 items-center justify-center rounded-full bg-blue-500/20 text-xs font-bold text-blue-400">
                  1
                </span>
                <h3 className="text-sm font-semibold text-text">Speech-to-Text (STT)</h3>
              </div>
              <span className="text-[10px] font-mono text-text-subtle uppercase">Recognition</span>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-text-muted mb-1.5">
                  STT Provider
                </label>
                <select
                  aria-label="STT provider"
                  value={draft.stt.provider}
                  onChange={(e) => handleSttProviderChange(e.target.value)}
                  disabled={busy || selected === "premium"}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40 disabled:opacity-75"
                >
                  <option value="" disabled>Choose a provider</option>
                  {availableSttProviders.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-text-muted mb-1.5">
                  STT Model
                </label>
                <select
                  aria-label="STT model"
                  aria-invalid={Boolean(fieldErrors["stt.model"])}
                  value={draft.stt.model}
                  onChange={(e) => handleSttModelChange(e.target.value)}
                  disabled={busy || selected === "premium"}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40 font-mono text-xs disabled:opacity-75"
                >
                  <option value="" disabled>Choose a model</option>
                  {currentSttModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
                <FieldError id="stt-model-error" message={fieldErrors["stt.model"]} />
              </div>
            </div>

            <p className="text-[11px] text-text-subtle">
              Streaming audio chunk recognition over low-latency WebSockets. The selected recognition model stays bound to this stack.
            </p>
          </div>

          {/* 2. Intelligence / LLM */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-4">
            <div className="flex items-center justify-between border-b border-surface-border-subtle pb-3">
              <div className="flex items-center gap-2">
                <span className="flex size-6 items-center justify-center rounded-full bg-purple-500/20 text-xs font-bold text-purple-400">
                  2
                </span>
                <h3 className="text-sm font-semibold text-text">Intelligence (LLM)</h3>
              </div>
              <span className="text-[10px] font-mono text-text-subtle uppercase">Reasoning</span>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-text-muted mb-1.5">
                  LLM Provider
                </label>
                <select
                  aria-label="LLM provider"
                  value={draft.llm.provider}
                  onChange={(e) => handleLlmProviderChange(e.target.value)}
                  disabled={busy || selected === "premium"}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40 disabled:opacity-75"
                >
                  <option value="" disabled>Choose a provider</option>
                  {availableLlmProviders.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-text-muted mb-1.5">
                  LLM Model
                </label>
                <select
                  aria-label="LLM model"
                  value={draft.llm.modelId}
                  onChange={(e) => handleLlmModelChange(e.target.value)}
                  disabled={busy || selected === "premium"}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40 font-mono text-xs disabled:opacity-75"
                >
                  <option value="" disabled>Choose a model</option>
                  {currentLlmModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
                <FieldError id="llm-model-error" message={fieldErrors["llm.modelId"]} />
              </div>
            </div>

            <p className="text-[11px] text-text-subtle">
              System instructions, dynamic persona rules, and dialogue turns are executed on this model.
            </p>
          </div>

          {/* 3. Speech Synthesis (TTS) */}
          <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-4">
            <div className="flex items-center justify-between border-b border-surface-border-subtle pb-3">
              <div className="flex items-center gap-2">
                <span className="flex size-6 items-center justify-center rounded-full bg-emerald-500/20 text-xs font-bold text-emerald-400">
                  3
                </span>
                <h3 className="text-sm font-semibold text-text">Speech Output (TTS)</h3>
              </div>
              <span className="text-[10px] font-mono text-text-subtle uppercase">Synthesis</span>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-text-muted mb-1.5">
                  TTS Provider
                </label>
                <select
                  aria-label="TTS provider"
                  value={currentTtsProvider}
                  onChange={(e) => handleTtsProviderChange(e.target.value)}
                  disabled={busy || selected === "premium"}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40 disabled:opacity-75"
                >
                  <option value="" disabled>Choose a provider</option>
                  {availableTtsProviders.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-text-muted mb-1.5">
                  TTS Model
                </label>
                <select
                  aria-label="TTS model"
                  value={currentTtsModel}
                  onChange={(e) => handleTtsModelChange(e.target.value)}
                  disabled={busy || selected === "premium"}
                  className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40 font-mono text-xs disabled:opacity-75"
                >
                  <option value="" disabled>Choose a model</option>
                  {currentTtsModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
                <FieldError id="tts-model-error" message={fieldErrors["tts.model"]} />
              </div>
            </div>

            {/* Warning when chosen provider is missing setup/credits */}
            {(() => {
              const cat = providers.find((cp) => cp.id === currentTtsProvider);
              const hasWarning = cat && (!cat.enabled || !cat.configured);
              if (!hasWarning) return null;
              return (
                <div className="flex items-start gap-2.5 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
                  <div className="space-y-0.5">
                    <p className="font-semibold text-amber-100">
                      {currentTtsProvider.toUpperCase()} credentials or credits are not configured
                    </p>
                    <p className="text-[11px] text-amber-200/80">
                      The chosen stack will <strong>never silently fall back to any default provider</strong>. If credits or quota are exhausted, call synthesis will report an error for this provider. Ensure account balance is active.
                    </p>
                  </div>
                </div>
              );
            })()}

            <p className="text-[11px] text-text-subtle">
              Curated voice personas are automatically bound to this speech engine. All speech options stream over low-latency WebSockets.
            </p>
          </div>
        </div>

        {/* Acoustic Calibration & Speech Dynamics (Universal Platform Controls) */}
        <div className="mt-6 rounded-2xl border border-surface-border bg-gradient-to-b from-surface-card to-surface-raised/40 p-5 shadow-sm space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-border-subtle pb-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <h3 className="text-base font-semibold text-text">
                  Voice knobs
                </h3>
                <span className="rounded-full border border-purple-500/30 bg-purple-500/10 px-2.5 py-0.5 text-[10px] font-semibold text-purple-300">
                  Tier default
                </span>
              </div>
              <p className="text-xs text-text-muted">
                {isNativeRealtimeLlm
                  ? <>Fine-tune the native live voice pace. This tier speaks through the realtime voice, so no separate TTS engine is active.</>
                  : <>Only the knobs supported by <strong>{currentTtsProvider ? currentTtsProvider.toUpperCase() : "the selected engine"}</strong> are shown. Agents inherit these unless they set their own pace.</>}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-text-muted bg-surface-raised border border-surface-border px-2.5 py-1 rounded-lg">
                Applies to: {knobTargets}
              </span>
            </div>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {currentTtsKnobs.map((spec) => (
              <span
                key={spec.key}
                className="inline-flex items-center gap-1.5 rounded-full border border-surface-border bg-surface-raised px-2.5 py-1 text-[10px] font-medium text-text-muted"
              >
                <span className="size-1.5 rounded-full bg-emerald-400" />
                {spec.label}
                {spec.native ? <code className="text-[9px] text-text-subtle">{spec.native}</code> : null}
              </span>
            ))}
          </div>

          {/* Dynamic Knobs — driven by the selected model's catalog capability list */}
          <div className="grid gap-6 md:grid-cols-2">
            <div className="space-y-3 rounded-xl border border-surface-border/60 bg-surface-panel/70 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs font-semibold text-text block">{speedKnob.label}</span>
                  <span className="text-[10px] text-text-subtle">{speedKnob.description}</span>
                </div>
                <span className="font-mono text-xs font-bold text-accent-primary px-2 py-0.5 rounded bg-accent-primary/10 border border-accent-primary/20">
                  {Number(draft.voiceDynamics?.speed ?? speedKnob.default ?? 1.0).toFixed(2)}{speedKnob.unit || "x"}
                </span>
              </div>

              <input
                type="range"
                min={speedKnob.min}
                max={speedKnob.max}
                step={speedKnob.step || 0.05}
                value={Number(draft.voiceDynamics?.speed ?? speedKnob.default ?? 1.0)}
                onChange={(e) => handleDynamicsChange({ speed: parseFloat(e.target.value) })}
                className="w-full h-2 bg-surface-raised rounded-lg appearance-none cursor-pointer accent-accent-primary"
              />

              <div className="flex justify-between text-[10px] text-text-subtle font-mono">
                <span>{Number(speedKnob.min).toFixed(2)}{speedKnob.unit || "x"} (Slow)</span>
                <span className="text-accent-primary font-semibold">1.00{speedKnob.unit || "x"} (Standard)</span>
                <span>{Number(speedKnob.max).toFixed(2)}{speedKnob.unit || "x"} (Fast)</span>
              </div>

              <div className="pt-2 border-t border-surface-border-subtle">
                <span className="text-[10px] font-semibold text-text-muted uppercase block mb-1.5">
                  Pacing Presets ({isNativeRealtimeLlm ? "LIVE VOICE" : currentTtsProvider.toUpperCase()})
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {speedPresetsFor(speedKnob).map((preset) => {
                    const active = Math.abs(Number(draft.voiceDynamics?.speed ?? 1.0) - preset.value) < 0.01;
                    return (
                      <button
                        key={`${preset.label}-${preset.value}`}
                        type="button"
                        onClick={() => handleDynamicsChange({ speed: preset.value })}
                        className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
                          active
                            ? "bg-accent-primary text-white shadow-xs"
                            : "border border-surface-border bg-surface-raised text-text hover:bg-surface-raised/80"
                        }`}
                      >
                        {preset.label} ({preset.value.toFixed(2)}x)
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            <div className="space-y-4 rounded-xl border border-surface-border/60 bg-surface-panel/70 p-4">
              {secondaryKnobs.length === 0 ? (
                <div className="space-y-2">
                  <span className="text-xs font-semibold text-text block">No additional delivery knobs</span>
                  <p className="text-[11px] text-text-subtle">
                    {isNativeRealtimeLlm
                      ? "The native live voice exposes pace only; tone and expression come from the voice model itself. Unsupported settings are never sent."
                      : "This engine exposes speaking pace only. Other controls are hidden because the provider would ignore them."}
                  </p>
                </div>
              ) : (
                secondaryKnobs.map((spec, index) => {
                  const raw = dynamicsValue(draft.voiceDynamics, spec.key);
                  if (spec.kind === "select") {
                    const current = String(raw ?? spec.default ?? "");
                    return (
                      <div key={spec.key} className={index > 0 ? "pt-3 border-t border-surface-border-subtle" : ""}>
                        <label className="block text-xs font-medium text-text-muted mb-1">{spec.label}</label>
                        <select
                          value={current}
                          onChange={(e) => handleDynamicsChange(knobPatch(spec.key, e.target.value))}
                          className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-xs text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
                        >
                          {(spec.options || []).map((option) => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                          ))}
                        </select>
                        {spec.description ? <p className="mt-1 text-[10px] text-text-subtle">{spec.description}</p> : null}
                      </div>
                    );
                  }
                  const current = Number(raw ?? spec.default ?? 1);
                  return (
                    <div key={spec.key} className={index > 0 ? "space-y-2 pt-3 border-t border-surface-border-subtle" : "space-y-2"}>
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="text-xs font-semibold text-text block">{spec.label}</span>
                          <span className="text-[10px] text-text-subtle">{spec.description}</span>
                        </div>
                        <span className="font-mono text-xs font-bold text-accent-primary px-2 py-0.5 rounded bg-accent-primary/10 border border-accent-primary/20">
                          {current.toFixed(2)}{spec.unit || ""}
                        </span>
                      </div>
                      <input
                        type="range"
                        min={spec.min}
                        max={spec.max}
                        step={spec.step || 0.01}
                        value={current}
                        onChange={(e) => handleDynamicsChange(knobPatch(spec.key, parseFloat(e.target.value)))}
                        className="w-full h-2 bg-surface-raised rounded-lg appearance-none cursor-pointer accent-accent-primary"
                      />
                      <div className="flex justify-between text-[10px] text-text-subtle font-mono">
                        <span>{Number(spec.min).toFixed(2)}{spec.unit || ""} (Low)</span>
                        <span className="text-accent-primary font-semibold">{Number(spec.default ?? 1).toFixed(2)}{spec.unit || ""} (Default)</span>
                        <span>{Number(spec.max).toFixed(2)}{spec.unit || ""} (High)</span>
                      </div>
                    </div>
                  );
                })
              )}

              {currentTtsProvider === "gnani" && (
                <div className="space-y-2 pt-2 border-t border-surface-border-subtle">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-text">Expressive Audio Tags</span>
                    <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                      {currentTtsModel === "timbre-v3.0" ? "Timbre v3.0" : "Timbre v2.5"}
                    </span>
                  </div>
                  <p className="text-[11px] text-text-subtle">
                    {currentTtsModel === "timbre-v3.0"
                      ? "Timbre v3.0 accepts inline expressive audio tags. Speaking speed is the documented numeric delivery control; numeric pitch, volume and temperature are not documented by the provider."
                      : "Timbre v2.5 supports speaking speed. Expressive audio tags are available on Timbre v3.0 only; numeric pitch, volume and temperature are not documented by the provider."}
                  </p>
                </div>
              )}

              {currentTtsProvider === "cartesia" && (
                <p className="pt-2 border-t border-surface-border-subtle text-[11px] text-text-subtle" data-testid="cartesia-delivery-guidance">
                  Sonic offers all 58 documented emotion choices for English. Emotion, speed and volume are generation guidance;
                  results depend on the voice and transcript. Saved choices are included in every synthesis request.
                </p>
              )}

              {currentTtsProvider === "gemini" && !isNativeRealtimeLlm && (
                <div className="space-y-2 pt-2 border-t border-surface-border-subtle">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-text">Delivery Persona Modulation</span>
                    <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                      Speech Metadata
                    </span>
                  </div>
                  <p className="text-[11px] text-text-subtle">
                    Pace and pitch character are sent as speech metadata directions on every turn; Gemini has no numeric pitch, temperature, or volume parameters.
                  </p>
                </div>
              )}

              {currentTtsProvider === "sarvam" && (
                <div className="space-y-2 pt-2 border-t border-surface-border-subtle">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-text">Model Knob Matrix</span>
                    <span className="text-[10px] font-mono text-sky-300 bg-sky-500/10 px-2 py-0.5 rounded border border-sky-500/20">
                      Per-model
                    </span>
                  </div>
                  <p className="text-[11px] text-text-subtle">
                    v3 and v4-flash expose pace + temperature. v2 exposes pace + pitch + loudness. Only parameters accepted by the selected model are sent.
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Test Speed Dynamics & Live Audition Box */}
          <div className="rounded-xl border border-surface-border bg-surface-panel p-4 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-surface-border-subtle pb-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-text">
                  Audition the knobs
                </span>
                <span className="text-[10px] text-text-subtle font-mono">
                  (uses your unsaved knob values)
                </span>
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={testVoiceId || currentVoices[0]?.id || ""}
                  onChange={(e) => setTestVoiceId(e.target.value)}
                  className="rounded-lg border border-surface-border bg-surface-raised px-2.5 py-1 text-xs text-text focus:outline-none"
                >
                  {currentVoices.map((v) => (
                    <option key={v.id} value={v.id}>
                      Voice: {v.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Test Sample Text Input */}
            <div className="space-y-2">
              <label className="block text-xs font-medium text-text-muted">
                Audition Sample Text (Telugu / English / Hindi)
              </label>
              <textarea
                rows={2}
                value={testText}
                onChange={(e) => setTestText(e.target.value)}
                placeholder="Enter test script to synthesize with configured dynamics..."
                className="w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-xs text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40 font-sans resize-none"
              />

              {/* Preset Sample Text Chips */}
              <div className="flex flex-wrap items-center gap-1.5 pt-1">
                <span className="text-[10px] text-text-subtle mr-1">Quick Scripts:</span>
                {[
                  {
                    label: "Real Estate Mohan (Telugu)",
                    text: "నమస్కారం! నేను మీ రియల్ ఎస్టేట్ సేల్స్ అసిస్టెంట్ మోహన్‌ని. మీకు ఎలా సహాయపడగలను?",
                  },
                  {
                    label: "Real Estate Mohan (English)",
                    text: "Hello! This is Mohan from real estate sales. How can I help you explore prime properties today?",
                  },
                  {
                    label: "Customer Support (Hindi)",
                    text: "नमस्ते! मैं आपका रियल एस्टेट सेल्स कंसल्टेंट मोहन हूँ। मैं आपकी क्या मदद कर सकता हूँ?",
                  },
                ].map((s) => (
                  <button
                    key={s.label}
                    type="button"
                    onClick={() => setTestText(s.text)}
                    className="rounded-md border border-surface-border bg-surface-raised/70 px-2 py-0.5 text-[10px] text-text-muted hover:text-text hover:bg-surface-raised transition-all"
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Audition Trigger & Status */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
              <div className="flex items-center gap-3">
                <Button
                  type="button"
                  disabled={isTestingDynamics}
                  onClick={() => void handleTestSpeedDynamics()}
                  className={`flex items-center gap-2 px-4 py-2 text-xs font-medium transition-all ${
                    isPlayingDynamics
                      ? "bg-amber-600 hover:bg-amber-700 text-white"
                      : "bg-accent-primary hover:bg-accent-primary/90 text-white shadow-sm"
                  }`}
                >
                  {isTestingDynamics ? (
                    <>
                      <span className="size-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                      <span>Synthesizing Audio…</span>
                    </>
                  ) : isPlayingDynamics ? (
                    <>
                      <span>Stop audition</span>
                    </>
                  ) : (
                    <>
                      <span>Play audition</span>
                    </>
                  )}
                </Button>

                {isPlayingDynamics && (
                  <div className="flex items-center gap-2 text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 rounded-lg animate-pulse">
                    <span className="size-2 rounded-full bg-emerald-400" />
                    <span>Playing at {Number(draft.voiceDynamics?.speed || 1.0).toFixed(2)}x ({currentTtsProvider.toUpperCase()})</span>
                  </div>
                )}
              </div>

              <span className="text-[11px] text-text-subtle font-mono">
                API: POST /api/dev/stack/voice-preview
              </span>
            </div>
          </div>
        </div>

        <PrewarmGreetingCard />

        {/* Curated Voice Catalog Auto-Binding Notification & Audio Playback Preview */}
        <div className="mt-6 rounded-xl border border-surface-border-subtle bg-surface-raised/40 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div>
              <p className="text-xs font-semibold text-text">
                Active Speech Engine: {currentTtsProvider.toUpperCase()} ({currentTtsModel})
              </p>
              <p className="mt-0.5 text-xs text-text-muted">
                {currentModelInventory.length} provider voices in the complete model catalogue · {currentVoices.length} available for the configured languages.
              </p>
            </div>
            <span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-300">
              Provider voice catalog
            </span>
          </div>

          {/* Voice Preview Playback Grid */}
          <div className="mb-3 flex items-center gap-3">
            <label className="text-xs text-text-muted">Voice style
              <select aria-label="Voice style" value={voiceCategory} onChange={(event) => setVoiceCategory(event.target.value)} className="ml-2 rounded-lg border border-surface-border bg-surface-panel p-2">
                <option value="">All styles</option>
                {[...new Set(currentModelInventory.map((voice) => voice.category).filter(Boolean))].sort().map((category) => <option key={category} value={category}>{category}</option>)}
              </select>
            </label>
            <Button variant="secondary" disabled={catalogRefreshing} onClick={() => void loadCatalog(true)}>{catalogRefreshing ? "Refreshing voices…" : "Refresh provider voices"}</Button>
            {catalogError && <p role="alert" className="text-xs text-red-400">{catalogError}</p>}
          </div>
          <div role="region" aria-label="Available model voices" tabIndex={0} className="grid max-h-96 overflow-y-auto gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {currentModelInventory.map((v, index) => ({ ...v, number: index + 1 })).filter((voice) => !voiceCategory || voice.category === voiceCategory).map((v) => {
              const isPlaying = playingVoiceId === v.id;
              const isLoading = previewLoadingId === v.id;
              const available = currentVoices.some((voice) => voice.id === v.id);
              return (
                <div
                  key={v.id}
                  className={`flex items-center justify-between rounded-xl border p-3 transition-colors ${
                    isPlaying
                      ? "border-emerald-500/40 bg-emerald-500/10"
                      : "border-surface-border bg-surface-panel hover:bg-surface-raised/60"
                  }`}
                >
                  <div className="space-y-0.5 min-w-0 pr-2">
                    <p className="text-xs font-medium text-text truncate">{v.label || `Voice ${v.number}`}</p>
                    <p className="text-[10px] text-text-muted break-all">{v.providerVoiceId}</p>
                    <p className="text-[10px] text-text-muted">{v.category || ""} · {(v.languages.length ? v.languages : v.preferredLanguages || []).join(", ")}</p>
                    {!available && <p className="text-[10px] text-amber-300">
                      {v.unavailableReason || "Enable one of this voice's supported languages to audition it."}
                    </p>}
                    {(v.gender || v.tone) && (
                      <p className="text-[10px] text-text-subtle truncate">
                        {v.gender ? `${v.gender} · ` : ""}{v.tone || ""}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    disabled={isLoading || !available}
                    aria-label={`Preview ${v.label || v.providerVoiceId}`}
                    onClick={() => void handlePlayVoicePreview(v.id)}
                    className={`shrink-0 flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
                      isPlaying
                        ? "bg-emerald-500 text-white shadow-sm"
                        : "bg-surface-raised text-text hover:bg-accent-primary hover:text-white"
                    }`}
                  >
                    {isLoading ? (
                      <span>Loading…</span>
                    ) : isPlaying ? (
                      <span>Stop</span>
                    ) : (
                      <span>Play</span>
                    )}
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {/* Supported Languages */}
        <div className="mt-6 rounded-xl border border-surface-border-subtle bg-surface-raised/30 p-4">
          <h4 className="text-xs font-semibold text-text mb-1">Supported Languages & Dialects</h4>
          <p className="text-xs text-text-muted mb-2">
            Languages verified for recognition, translation, and speech generation in this tier.
          </p>
          <div className="flex flex-wrap gap-2">
            {draft.supportedLanguages.map((lang) => (
              <span
                key={lang}
                className="rounded-lg border border-surface-border bg-surface-panel px-2.5 py-1 font-mono text-xs text-text"
              >
                {lang}
              </span>
            ))}
          </div>
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-surface-border p-4">
          <p className="max-w-xl text-xs text-text-muted">
            {isNativeRealtimeLlm
              ? "Checks the saved provider, live model and voices against the approved runtime. Native audio has no separate stages to probe; confirm call quality with a Test Studio session."
              : "Verifies the saved model, speech, tools, credentials and media path with synthetic provider requests. No phone call is placed. Capacity is a concurrency smoke check, not a peak-load certification."}
            {dirty ? " Save or discard your changes first: verification runs on the saved revision." : ""}
          </p>
          <Button type="button" variant="secondary" disabled={busy || dirty || !selectedRow?.composedProfile}
            onClick={() => void handleVerifyReadiness()} data-testid="verify-profile-readiness">
            {busy ? "Working…" : isNativeRealtimeLlm ? "Run static check" : "Verify saved setup"}
          </Button>
        </div>
        {verification && <ul className="mt-3 space-y-2 text-xs" aria-label="Verification results">
          {Object.entries(verification).map(([key, check]) => <li key={key} className={check.notApplicable ? "text-text-muted" : check.passed ? "text-emerald-300" : "text-amber-300"}>
            {check.notApplicable ? "Not applicable" : check.passed ? "Passed" : "Needs attention"}: {check.detail}
          </li>)}
        </ul>}


        {/* Save / discard footer */}
        <div className="sticky bottom-0 mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-border bg-surface-card/95 pt-4 pb-2 backdrop-blur">
          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              disabled={busy || !dirty}
              onClick={requestSave}
              className="px-5 py-2.5"
              data-testid="save-tier"
            >
              {busy ? "Saving…" : isEnabled ? "Save and apply" : "Save"}
            </Button>
            <Button type="button" variant="secondary" disabled={busy || !dirty} onClick={discardChanges} data-testid="discard-tier">
              Discard changes
            </Button>
            <span className={`text-xs font-medium ${dirty ? "text-amber-300" : "text-text-subtle"}`} aria-live="polite">
              {dirty ? "Unsaved changes" : `All changes saved (revision ${selectedRow?.profileRevision ?? 0})`}
            </span>
          </div>
          <Button type="button" variant="secondary" disabled={busy} onClick={() => void handleLoadRecommended()}>
            Load recommended setup
          </Button>
        </div>
      </DevCard>
      </div>

      <div
        role="tabpanel"
        id="pstn-section-panel-pricing"
        aria-labelledby="pstn-section-tab-pricing"
        hidden={activeSection !== "pricing"}
      >
        <PlatformPricesPanel rows={rows} onSaved={() => loadProfiles(false)} />
      </div>

      <div
        role="tabpanel"
        id="pstn-section-panel-telephony"
        aria-labelledby="pstn-section-tab-telephony"
        hidden={activeSection !== "telephony"}
      >
        <TelephonyTrunkPanel />
      </div>

      <div
        role="tabpanel"
        id="pstn-section-panel-transcription"
        aria-labelledby="pstn-section-tab-transcription"
        hidden={activeSection !== "transcription"}
      >
        <TranscriptionPanel />
      </div>

      <ConfirmDialog
        open={pendingSave !== null}
        busy={busy}
        title={pendingSave?.kind === "offline" ? `Take ${selectedName} offline?` : `Apply changes to ${selectedName}?`}
        description={pendingSave?.kind === "offline"
          ? `These speech, conversation or voice changes need fresh verification. Saving takes ${selectedName} offline until it is verified and enabled again. ${agentPhrase} cannot place calls on it until then.${pendingSave.blockers?.length ? ` Blocking: ${pendingSave.blockers.join("; ")}.` : ""}`
          : `${selectedName} is live. ${agentPhrase} will use the new settings on their next call.`}
        confirmLabel={pendingSave?.kind === "offline" ? "Save and take offline" : "Save and apply"}
        cancelLabel="Keep editing"
        onCancel={() => setPendingSave(null)}
        onConfirm={() => {
          if (pendingSave) void commitSave(pendingSave.payload, pendingSave.tier, pendingSave.kind === "offline");
        }}
      />

      <ConfirmDialog
        open={pendingDisable}
        busy={busy}
        title={`Disable ${selectedName}?`}
        description={`${selectedName} will be hidden from tenants. ${agentPhrase} cannot place calls on it until it is enabled again.`}
        confirmLabel="Disable tier"
        cancelLabel="Cancel"
        onCancel={() => setPendingDisable(false)}
        onConfirm={() => void handleToggleActivation(false)}
      />

      {/* Duplicate Stack Modal */}
      {showDuplicateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-surface-border bg-surface-card p-6 shadow-2xl space-y-4">
            <h3 className="text-base font-semibold text-text">Duplicate Stack as Brand New Tier</h3>
            <p className="text-xs text-text-muted">
              Creates a new, independent tier from the <strong>saved</strong> setup of <strong>{selectedName}</strong>
              (unsaved edits are not copied). The new tier starts disabled; the source tier is unchanged.
            </p>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-text-muted mb-1">
                  Source Stack (Selected)
                </label>
                <div className="rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-xs font-mono text-text-subtle">
                  {selectedName} ({selected})
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-text-muted mb-1">
                  New Stack Name (Display Label)
                </label>
                <input
                  type="text"
                  value={duplicateLabel}
                  onChange={(e) => setDuplicateLabel(e.target.value)}
                  placeholder="e.g. Economical Tier (Copy 1)"
                  className="w-full rounded-xl border border-surface-border bg-surface-panel px-3 py-2 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-text-muted mb-1">
                  New Tier Identifier / Slug (Max 20 chars, lowercase alphanumeric &amp; underscore)
                </label>
                <input
                  type="text"
                  maxLength={20}
                  value={duplicateNewSlug}
                  onChange={(e) => setDuplicateNewSlug(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_").slice(0, 20))}
                  placeholder="e.g. low_copy_1"
                  className="w-full rounded-xl border border-surface-border bg-surface-panel px-3 py-2 text-sm font-mono text-text focus:outline-none focus:ring-2 focus:ring-accent-primary/40"
                />
                <span className="mt-1 block text-[11px] text-text-subtle">
                  Slug: <code className="font-mono text-text">{duplicateNewSlug || "none"}</code>
                </span>
              </div>
            </div>

            <div className="flex justify-end gap-2.5 pt-2 border-t border-surface-border-subtle">
              <Button
                type="button"
                variant="secondary"
                disabled={busy}
                onClick={() => setShowDuplicateModal(false)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                disabled={busy}
                onClick={() => void handleConfirmDuplicate()}
              >
                {busy ? "Duplicating…" : "Create Duplicated Stack"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
