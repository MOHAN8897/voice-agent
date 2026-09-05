"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { persistTestStudioVoice } from "@/lib/persist-test-studio-voice";
import { DEFAULT_CARTESIA_VOICE_ID, isCartesiaVoiceId } from "@/lib/voice/tts-config";

export type CartesiaVoice = {
  id: string;
  name: string;
  gender?: string;
  languages?: string[];
  accent?: string;
  description?: string;
  region?: string;
};

type VoiceGroups = {
  telugu: CartesiaVoice[];
  hindi: CartesiaVoice[];
  indian_english: CartesiaVoice[];
  english: CartesiaVoice[];
  labels?: Record<string, string>;
  source?: string;
  studio_count?: number;
  total_pulled?: number;
};

const GROUP_ORDER = ["telugu", "hindi", "indian_english", "english"] as const;

const GROUP_LABELS: Record<string, string> = {
  telugu: "Telugu",
  hindi: "Hindi",
  indian_english: "Indian English",
  english: "English (US/UK)",
};

/** Always-visible fallbacks so the dropdown never renders empty. */
const FALLBACK_VOICES: CartesiaVoice[] = [
  {
    id: DEFAULT_CARTESIA_VOICE_ID,
    name: "Skylar",
    gender: "feminine",
    languages: ["en"],
    region: "english",
    description: "American English female (default)",
  },
  {
    id: "79a125e8-cd45-4c13-8a67-0491c5ad1b8a",
    name: "Maya",
    gender: "feminine",
    languages: ["en", "te", "hi"],
    region: "indian_english",
  },
  {
    id: "2ee87190-8f84-4925-97da-e756ad7d262d",
    name: "Devansh",
    gender: "masculine",
    languages: ["en", "te", "hi"],
    region: "indian_english",
  },
];

function voiceLabel(v: CartesiaVoice): string {
  const parts = [v.name];
  if (v.gender) parts.push(v.gender);
  if (v.accent) parts.push(v.accent);
  else if (v.languages?.length) parts.push(v.languages.join(", "));
  return parts.join(" · ");
}

function flattenGroups(g: VoiceGroups | null): CartesiaVoice[] {
  if (!g) return [];
  return GROUP_ORDER.flatMap((k) => g[k] || []);
}

function mergeIntoGroups(base: VoiceGroups | null, extras: CartesiaVoice[]): VoiceGroups {
  const groups: VoiceGroups = {
    telugu: [...(base?.telugu || [])],
    hindi: [...(base?.hindi || [])],
    indian_english: [...(base?.indian_english || [])],
    english: [...(base?.english || [])],
    labels: base?.labels,
    source: base?.source,
    studio_count: base?.studio_count,
    total_pulled: base?.total_pulled,
  };
  const seen = new Set(flattenGroups(groups).map((v) => v.id));
  for (const v of extras) {
    if (!v?.id || seen.has(v.id)) continue;
    seen.add(v.id);
    const region = (v.region || "english") as (typeof GROUP_ORDER)[number];
    const bucket = GROUP_ORDER.includes(region) ? region : "english";
    groups[bucket] = [...(groups[bucket] || []), v];
  }
  return groups;
}

export function CartesiaVoiceSelect({
  value,
  onChange,
  disabled,
  className,
  showMeta = true,
  ttsModel = "sonic-3.5",
  autoSave = true,
  defaultVoiceId = DEFAULT_CARTESIA_VOICE_ID,
  initialVoices,
}: {
  value: string;
  onChange: (voiceId: string) => void;
  disabled?: boolean;
  className?: string;
  showMeta?: boolean;
  ttsModel?: string;
  autoSave?: boolean;
  defaultVoiceId?: string;
  initialVoices?: CartesiaVoice[];
}) {
  const [groups, setGroups] = useState<VoiceGroups | null>(null);
  const [flat, setFlat] = useState<CartesiaVoice[]>(() =>
    initialVoices?.length ? initialVoices : FALLBACK_VOICES
  );
  const [loading, setLoading] = useState(!initialVoices?.length);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveHint, setSaveHint] = useState<string | null>(null);
  const autoAppliedRef = useRef("");
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const load = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const url = refresh
        ? "/api/settings/cartesia-voices?refresh=true"
        : "/api/settings/cartesia-voices";
      const r = await fetch(url, { credentials: "include" });
      if (!r.ok) throw new Error(`Could not load Cartesia voices (${r.status})`);
      const j = await r.json();
      const g = (j?.groups || null) as VoiceGroups | null;
      const fromApi: CartesiaVoice[] = Array.isArray(j?.voices) ? j.voices : flattenGroups(g);
      const next = fromApi.length ? fromApi : FALLBACK_VOICES;
      setGroups(mergeIntoGroups(g, [...FALLBACK_VOICES, ...next]));
      setFlat(next.length ? next : FALLBACK_VOICES);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load voices");
      setFlat((prev) => (prev.length ? prev : FALLBACK_VOICES));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load(false);
  }, [load]);

  const displayGroups = mergeIntoGroups(groups, [...FALLBACK_VOICES, ...flat]);
  const displayFlat = flattenGroups(displayGroups);
  const ids = new Set(displayFlat.map((v) => v.id));
  const fallback =
    (defaultVoiceId && ids.has(defaultVoiceId) ? defaultVoiceId : "") ||
    (ids.has(DEFAULT_CARTESIA_VOICE_ID) ? DEFAULT_CARTESIA_VOICE_ID : "") ||
    displayFlat[0]?.id ||
    DEFAULT_CARTESIA_VOICE_ID;
  const resolvedValue = value && ids.has(value) ? value : fallback;

  useEffect(() => {
    if (loading || !displayFlat.length || !fallback) return;
    const known = new Set(displayFlat.map((v) => v.id));
    if (value && known.has(value)) return;
    if (autoAppliedRef.current === fallback) return;
    autoAppliedRef.current = fallback;
    onChangeRef.current(fallback);
    if (!autoSave) return;
    void persistTestStudioVoice({ ttsSpeaker: fallback, ttsModel }).then((result) => {
      setSaveHint(result.ok ? "Default Cartesia voice applied" : result.error || "Save failed");
    });
  }, [loading, displayFlat.length, value, fallback, autoSave, ttsModel]);

  async function handleChange(voiceId: string) {
    autoAppliedRef.current = voiceId;
    onChange(voiceId);
    if (!autoSave) return;
    setSaveHint(null);
    const result = await persistTestStudioVoice({ ttsSpeaker: voiceId, ttsModel });
    setSaveHint(result.ok ? "Voice saved — applies on next spoken turn" : result.error || "Save failed");
  }

  if (loading && !flat.length) {
    return <p className="text-xs text-text-muted">Loading Cartesia voices…</p>;
  }

  const hasGroups = GROUP_ORDER.some((k) => (displayGroups[k]?.length ?? 0) > 0);
  const unmatched = Boolean(value && !isCartesiaVoiceId(value));

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <select
          disabled={disabled || refreshing}
          className={cn(
            "flex-1 min-w-[12rem] rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-3 py-2 text-sm disabled:opacity-50",
            className
          )}
          value={resolvedValue}
          onChange={(e) => void handleChange(e.target.value)}
        >
          {hasGroups
            ? GROUP_ORDER.map((key) => {
                const list = displayGroups[key] || [];
                if (!list.length) return null;
                const label = displayGroups.labels?.[key] || GROUP_LABELS[key] || key;
                return (
                  <optgroup key={key} label={`${label} (${list.length})`}>
                    {list.map((v) => (
                      <option key={v.id} value={v.id}>
                        {voiceLabel(v)}
                      </option>
                    ))}
                  </optgroup>
                );
              })
            : displayFlat.map((v) => (
                <option key={v.id} value={v.id}>
                  {voiceLabel(v)}
                </option>
              ))}
        </select>
        <button
          type="button"
          disabled={disabled || refreshing}
          onClick={() => void load(true)}
          className="rounded-skeuo-sm border border-surface-border-subtle px-2.5 py-2 text-[11px] font-medium text-text-muted hover:bg-surface-raised disabled:opacity-50"
          title="Re-pull from Cartesia API"
        >
          {refreshing ? "…" : "Refresh"}
        </button>
      </div>
      {unmatched && (
        <p className="text-[11px] text-status-warning">
          Previous voice was not a Cartesia voice. Default <span className="font-mono">Skylar</span> is selected.
        </p>
      )}
      {showMeta && (
        <p className="text-[10px] text-text-subtle">
          {displayGroups?.studio_count ?? displayFlat.length} voices · Telugu {displayGroups?.telugu?.length ?? 0} · Hindi{" "}
          {displayGroups?.hindi?.length ?? 0} · Indian English {displayGroups?.indian_english?.length ?? 0} · English{" "}
          {displayGroups?.english?.length ?? 0}
          {displayGroups?.source === "api" && displayGroups.total_pulled
            ? ` · ${displayGroups.total_pulled} pulled from Cartesia`
            : displayGroups?.source === "static"
              ? " · offline fallback (set CARTESIA_API_KEY)"
              : ""}
          {saveHint ? ` · ${saveHint}` : ""}
        </p>
      )}
      {error && <p className="text-[11px] text-status-warning">{error}</p>}
    </div>
  );
}
