"use client";

import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/cn";
import { persistTestStudioVoice } from "@/lib/persist-test-studio-voice";

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

function voiceLabel(v: CartesiaVoice): string {
  const parts = [v.name];
  if (v.gender) parts.push(v.gender);
  if (v.accent) parts.push(v.accent);
  else if (v.languages?.length) parts.push(v.languages.join(", "));
  return parts.join(" · ");
}

export function CartesiaVoiceSelect({
  value,
  onChange,
  disabled,
  className,
  showMeta = true,
  ttsModel = "sonic-3.5",
  autoSave = true,
}: {
  value: string;
  onChange: (voiceId: string) => void;
  disabled?: boolean;
  className?: string;
  showMeta?: boolean;
  ttsModel?: string;
  autoSave?: boolean;
}) {
  const [groups, setGroups] = useState<VoiceGroups | null>(null);
  const [flat, setFlat] = useState<CartesiaVoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveHint, setSaveHint] = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const url = refresh
        ? "/api/settings/cartesia-voices?refresh=true"
        : "/api/settings/cartesia-voices";
      const r = await fetch(url, { credentials: "include" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      const g = (j?.groups || null) as VoiceGroups | null;
      setGroups(g);
      setFlat(Array.isArray(j?.voices) ? j.voices : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load voices");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load(false);
  }, [load]);

  const resolvedValue = value || flat[0]?.id || "";

  async function handleChange(voiceId: string) {
    onChange(voiceId);
    if (!autoSave) return;
    setSaveHint(null);
    const result = await persistTestStudioVoice({ ttsSpeaker: voiceId, ttsModel });
    setSaveHint(result.ok ? "Voice saved — applies on next spoken turn" : result.error || "Save failed");
  }

  if (loading && !flat.length) {
    return <p className="text-xs text-text-muted">Loading Cartesia voices…</p>;
  }

  const hasGroups =
    groups &&
    GROUP_ORDER.some((k) => (groups[k]?.length ?? 0) > 0);

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
                const list = groups![key] || [];
                if (!list.length) return null;
                const label = groups!.labels?.[key] || GROUP_LABELS[key] || key;
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
            : flat.map((v) => (
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
      {showMeta && groups && (
        <p className="text-[10px] text-text-subtle">
          {groups.studio_count ?? flat.length} voices · Telugu {groups.telugu?.length ?? 0} · Hindi{" "}
          {groups.hindi?.length ?? 0} · Indian English {groups.indian_english?.length ?? 0} · English{" "}
          {groups.english?.length ?? 0}
          {groups.source === "api" && groups.total_pulled
            ? ` · ${groups.total_pulled} pulled from Cartesia`
            : groups.source === "static"
              ? " · offline fallback (set CARTESIA_API_KEY)"
              : ""}
          {saveHint ? ` · ${saveHint}` : ""}
        </p>
      )}
      {error && <p className="text-[11px] text-status-warning">{error}</p>}
    </div>
  );
}
