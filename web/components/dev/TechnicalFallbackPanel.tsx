"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { DevCard } from "@/components/dev/DevCard";
import { SkeuoButton } from "@/components/ui/skeuo";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";
import { cn } from "@/lib/cn";
import { devFetch } from "@/lib/useAdminResource";

type Clip = {
  language: string;
  variant: string;
  durationMs: number;
  updatedAt: string | null;
};

type Variant = { id: string; label: string };

type FallbackPayload = {
  agentId: string;
  tenantId: string;
  name: string;
  spokenLanguages: string[];
  languages: string[];
  promiseCallback: boolean;
  transcript: string;
  variants: Variant[];
  defaults: Record<string, Record<string, string>>;
  clips: Clip[];
};

const LANGUAGE_LABELS: Record<string, string> = {
  "en-IN": "English (India)",
  "hi-IN": "Hindi",
  "te-IN": "Telugu",
  "ta-IN": "Tamil",
  "kn-IN": "Kannada",
  "ml-IN": "Malayalam",
  "mr-IN": "Marathi",
  "bn-IN": "Bengali",
  "gu-IN": "Gujarati",
  "pa-IN": "Punjabi",
};

const VARIANT_HELP: Record<string, string> = {
  callback_promise:
    "Played only after a callback task is saved. The caller hears “we will call you again”.",
  call_back:
    "The safe line. Played when no callback task can be created, so the caller is asked to call back.",
  disclosure:
    "Prepended if the recording disclosure has not yet been spoken in the conversation.",
};

function languageLabel(code: string) {
  return LANGUAGE_LABELS[code] || code;
}

export function TechnicalFallbackPanel({ agentId }: { agentId: string }) {
  const [data, setData] = useState<FallbackPayload | null>(null);
  const [promiseCallback, setPromiseCallback] = useState(true);
  const [transcript, setTranscript] = useState("");
  const [language, setLanguage] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyKey, setBusyKey] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const endpoint = `/api/dev/admin/agents/${encodeURIComponent(agentId)}/technical-fallback`;

  const apply = useCallback((payload: FallbackPayload, keepDraft = false) => {
    setData(payload);
    if (!keepDraft) {
      setPromiseCallback(payload.promiseCallback);
      setTranscript(payload.transcript || "");
    }
    setLanguage((current) => payload.languages.includes(current) ? current : payload.languages[0] || "");
  }, []);

  const load = useCallback(async (keepDraft = false) => {
    setLoading(true);
    setError("");
    try {
      let response = await portalFetch("dev", endpoint, { cache: "no-store" });
      if (response.status === 401 && (await refreshPortalSession("dev"))) {
        response = await portalFetch("dev", endpoint, { cache: "no-store" });
      }
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(
          payload?.detail?.error?.message ||
          (typeof payload?.detail === "string" ? payload.detail : "Could not load the outage announcement settings.")
        );
      }
      apply(payload as FallbackPayload, keepDraft);
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the outage announcement settings.");
      return false;
    } finally {
      setLoading(false);
    }
  }, [apply, endpoint]);

  useEffect(() => {
    void load();
  }, [load]);

  const dirty = Boolean(
    data && (promiseCallback !== data.promiseCallback || transcript.trim() !== (data.transcript || ""))
  );

  const clipMap = useMemo(() => {
    const map = new Map<string, Clip>();
    for (const clip of data?.clips || []) {
      map.set(`${clip.language}:${clip.variant}`, clip);
    }
    return map;
  }, [data?.clips]);

  const save = async () => {
    if (saving || busyKey) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await devFetch(endpoint, {
        method: "PATCH",
        body: JSON.stringify({ promiseCallback, transcript: transcript.trim() }),
      });
      if (await load()) setNotice("Outage announcement settings saved.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the outage announcement settings.");
    } finally {
      setSaving(false);
    }
  };

  const upload = async (targetLanguage: string, variant: string, file: File | undefined) => {
    if (!file || saving || busyKey) return;
    const key = `${targetLanguage}:${variant}`;
    setBusyKey(key);
    setError("");
    setNotice("");
    try {
      const body = new FormData();
      body.append("file", file);
      await devFetch(
        `${endpoint}/clips/${encodeURIComponent(targetLanguage)}/${encodeURIComponent(variant)}`,
        { method: "PUT", body }
      );
      if (await load(true)) setNotice(`Recording saved for ${languageLabel(targetLanguage)}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not upload that recording.");
    } finally {
      setBusyKey("");
    }
  };

  const remove = async (targetLanguage: string, variant: string) => {
    if (saving || busyKey) return;
    const key = `${targetLanguage}:${variant}`;
    setBusyKey(key);
    setError("");
    setNotice("");
    try {
      await devFetch(
        `${endpoint}/clips/${encodeURIComponent(targetLanguage)}/${encodeURIComponent(variant)}`,
        { method: "DELETE" }
      );
      if (await load(true)) {
        setNotice(`Custom recording removed — the platform recording is used for ${languageLabel(targetLanguage)}.`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove that recording.");
    } finally {
      setBusyKey("");
    }
  };

  if (loading && !data) {
    return (
      <DevCard title="TTS outage announcement" description="Loading platform configuration…">
        <div className="h-24 animate-pulse rounded-xl bg-surface-panel-raised" />
      </DevCard>
    );
  }

  if (!data) {
    return (
      <DevCard title="TTS outage announcement">
        <p role="alert" className="text-sm text-status-error">{error || "This agent could not be loaded."}</p>
        <SkeuoButton type="button" className="mt-4" onClick={() => void load()}>
          Try again
        </SkeuoButton>
      </DevCard>
    );
  }

  const selectedLanguage = language || data.languages[0] || "en-IN";
  const variants = data.variants;
  const customCount = data.clips.filter((clip) => clip.language === selectedLanguage).length;
  const working = saving || loading || Boolean(busyKey);

  return (
    <div className="space-y-5">
      <DevCard
        title="TTS outage announcement"
        description="Choose the recorded apology and callback policy used if speech becomes unavailable during this agent’s calls."
      >
        <div className="rounded-xl border border-surface-border-subtle bg-surface-panel-raised px-4 py-3">
          <p className="text-xs font-semibold text-text">
            Agent: {data.name} · {data.spokenLanguages.map(languageLabel).join(", ") || "No spoken language"}
          </p>
          <p className="mt-1 font-mono text-[10px] text-text-subtle">
            Tenant {data.tenantId} · Agent {data.agentId}
          </p>
        </div>

        <div className="mt-4 flex flex-col gap-3 rounded-xl border border-surface-border-subtle p-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-text">Promise the caller a callback</p>
            <p className="mt-1 max-w-2xl text-xs leading-relaxed text-text-muted">
              {promiseCallback
                ? "The callback-promise recording is used, but only after a pending callback task is saved. If it cannot be saved, the safe call-back request is played instead."
                : "The safe call-back request is always used. No callback task is promised."}
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={promiseCallback}
            aria-label="Promise the caller a callback"
            disabled={working}
            onClick={() => setPromiseCallback((value) => !value)}
            className={cn(
              "relative inline-flex h-7 w-12 shrink-0 items-center rounded-full border transition-colors disabled:opacity-50",
              promiseCallback ? "border-accent bg-accent" : "border-surface-border bg-surface-panel-raised"
            )}
          >
            <span
              className={cn(
                "inline-block h-5 w-5 rounded-full bg-white shadow transition-transform",
                promiseCallback ? "translate-x-6" : "translate-x-1"
              )}
            />
          </button>
        </div>

        <label className="mt-4 block">
          <span className="text-xs font-semibold text-text">Internal transcript note</span>
          <textarea
            name="outageTranscript"
            value={transcript}
            onChange={(event) => setTranscript(event.target.value)}
            rows={2}
            maxLength={255}
            disabled={working}
            placeholder="What the recorded message says — for operators and call review."
            className="mt-1 w-full rounded-skeuo-sm border border-surface-border bg-surface-panel-raised px-3 py-2 text-xs max-sm:text-base text-text"
          />
          <span className="mt-1 block text-right text-[10px] text-text-subtle">{transcript.length}/255</span>
        </label>
        <p className="text-[11px] text-text-subtle">
          This note is never synthesized during an outage. Callers hear a recording only.
        </p>

        {error && (
          <p role="alert" className="mt-3 rounded-lg border border-status-error bg-surface-panel-raised px-3 py-2 text-xs text-status-error">
            {error}
          </p>
        )}
        {notice && (
          <p role="status" className="mt-3 rounded-lg border border-success/30 bg-success/5 px-3 py-2 text-xs text-success">
            {notice}
          </p>
        )}

        <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
          <SkeuoButton type="button" variant="ghost" onClick={() => { setNotice(""); void load(); }} disabled={working || dirty}>
            Reload
          </SkeuoButton>
          <SkeuoButton type="button" variant="ghost" onClick={() => apply(data)} disabled={working || !dirty}>
            Discard changes
          </SkeuoButton>
          <SkeuoButton type="button" variant="primary" onClick={() => void save()} disabled={!dirty || working} loading={saving}>
            Save announcement settings
          </SkeuoButton>
        </div>
      </DevCard>

      <DevCard
        title="Recorded messages"
        description="Upload a 16-bit PCM WAV (mono or stereo, up to 2 MB and 30 seconds) for each language and message."
      >
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs font-semibold text-text" htmlFor="fallback-language">
            Language
          </label>
          <select
            id="fallback-language"
            name="fallbackLanguage"
            value={selectedLanguage}
            disabled={working}
            onChange={(event) => setLanguage(event.target.value)}
            className="rounded-skeuo-sm border border-surface-border bg-surface-panel-raised px-3 py-1.5 text-xs max-sm:text-base text-text"
          >
            {data.languages.map((code) => {
              const count = data.clips.filter((clip) => clip.language === code).length;
              return (
                <option key={code} value={code}>
                  {languageLabel(code)} — {count}/{variants.length} custom
                </option>
              );
            })}
          </select>
          <span className="text-[11px] text-text-subtle">
            {customCount === 0
              ? `All ${variants.length} messages use the platform recordings.`
              : `${customCount} of ${variants.length} lines use a custom recording.`}
          </span>
        </div>

        <div className="mt-4 space-y-3">
          {variants.map((variant) => {
            const key = `${selectedLanguage}:${variant.id}`;
            const clip = clipMap.get(key);
            const busy = busyKey === key;
            const platformText = data.defaults[selectedLanguage]?.[variant.id] || "";
            return (
              <div key={variant.id} className="rounded-xl border border-surface-border-subtle p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-text">{variant.label}</p>
                    <p className="mt-1 text-[11px] text-text-muted">{VARIANT_HELP[variant.id] || ""}</p>
                    <p className="mt-2 text-xs text-text">
                      <span className="text-text-subtle">Platform recording: </span>
                      “{platformText}”
                    </p>
                    <p className="mt-1 text-[11px] text-text-subtle">
                      {clip
                        ? `Custom recording · ${Math.max(1, Math.round(clip.durationMs / 1000))}s`
                        : "Custom recording not uploaded — the platform recording is used."}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    <label
                      className={cn(
                        "cursor-pointer rounded-skeuo-sm border border-surface-border bg-surface-panel-raised px-3 py-1.5 text-xs font-semibold text-text hover:border-accent/50 focus-within:ring-2 focus-within:ring-accent-primary/40",
                        working && "pointer-events-none opacity-50"
                      )}
                    >
                      {busy ? "Saving…" : clip ? "Replace WAV" : "Upload WAV"}
                      <input
                        type="file"
                        name={`${variant.id}Recording`}
                        accept="audio/wav,audio/x-wav,.wav"
                        className="sr-only"
                        aria-label={`${clip ? "Replace" : "Upload"} ${variant.label} WAV for ${languageLabel(selectedLanguage)}`}
                        disabled={working}
                        onChange={(event) => {
                          const file = event.target.files?.[0];
                          event.target.value = "";
                          void upload(selectedLanguage, variant.id, file);
                        }}
                      />
                    </label>
                    {clip && (
                      <SkeuoButton
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={working}
                        onClick={() => void remove(selectedLanguage, variant.id)}
                      >
                        Remove
                      </SkeuoButton>
                    )}
                  </div>
                </div>
                {clip && (
                  <audio
                    className="mt-3 w-full max-w-md"
                    controls
                    preload="none"
                    src={`${endpoint}/clips/${encodeURIComponent(selectedLanguage)}/${encodeURIComponent(
                      variant.id
                    )}/audio?v=${encodeURIComponent(clip.updatedAt || "")}`}
                  />
                )}
              </div>
            );
          })}
        </div>
      </DevCard>

      <DevCard title="How playback behaves">
        <ul className="list-disc space-y-2 pl-5 text-xs leading-relaxed text-text-muted">
          <li>The recording is chosen for the call language, with Indian English used if a matching recording is unavailable.</li>
          <li>The recording disclosure is prepended only if it has not already been said in the conversation.</li>
          <li>Playback is protected from interruption. The call ends after the announcement finishes.</li>
          <li>Startup and mid-call speech failures both use these recorded messages.</li>
        </ul>
      </DevCard>
    </div>
  );
}
