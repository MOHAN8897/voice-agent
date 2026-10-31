"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AdminPageHeader } from "@/components/admin/AdminNav";
import { DevCard } from "@/components/dev/DevCard";
import { SkeuoButton } from "@/components/ui/skeuo";
import { cn } from "@/lib/cn";
import { adminAction, devFetch } from "@/lib/useAdminResource";

type OutageConfig = {
  enabled: boolean;
  promiseCallback: boolean;
  version: number;
  updatedAt: string | null;
  updatedBy: string | null;
};

type Coverage = Record<string, Record<string, string[]>>;
type Variant = { id: string; label: string };

type Payload = {
  global: OutageConfig;
  coverage: Coverage;
  variants: Variant[];
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
    "Used only after a pending callback task is saved. The caller hears “we will call you again”.",
  call_back:
    "The safe line, used when no callback task can be created. The caller is asked to call back.",
  disclosure:
    "Prepended when the recording disclosure has not yet been spoken on the call.",
};

function languageLabel(code: string) {
  return LANGUAGE_LABELS[code] || code;
}

function formatWhen(value: string | null | undefined) {
  if (!value) return "never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown";
  return date.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

export function SpeechOutagePanel() {
  const [data, setData] = useState<Payload | null>(null);
  const [enabled, setEnabled] = useState(true);
  const [promiseCallback, setPromiseCallback] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const apply = useCallback((payload: Payload) => {
    setData(payload);
    setEnabled(payload.global.enabled);
    setPromiseCallback(payload.global.promiseCallback);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const payload = (await devFetch("/api/dev/admin/speech-outage", {
        cache: "no-store",
      })) as Payload;
      apply(payload);
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the speech outage settings.");
      return false;
    } finally {
      setLoading(false);
    }
  }, [apply]);

  useEffect(() => {
    void load();
  }, [load]);

  const dirty = Boolean(
    data && (enabled !== data.global.enabled || promiseCallback !== data.global.promiseCallback)
  );

  const save = async () => {
    if (saving) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const payload = await adminAction<{ global: OutageConfig }>("/api/dev/admin/speech-outage", {
        method: "PATCH",
        body: { enabled, promiseCallback },
      });
      setData((current) =>
        current
          ? {
              ...current,
              global: payload.global,
            }
          : current
      );
      setEnabled(payload.global.enabled);
      setPromiseCallback(payload.global.promiseCallback);
      setNotice("Platform speech outage settings saved. New calls pick them up immediately.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the speech outage settings.");
    } finally {
      setSaving(false);
    }
  };

  const languages = useMemo(() => {
    const codes = new Set<string>();
    for (const gender of Object.values(data?.coverage || {})) {
      for (const list of Object.values(gender)) {
        for (const code of list) codes.add(code);
      }
    }
    return [...codes].sort();
  }, [data?.coverage]);

  const variants = data?.variants || [];
  const working = loading || saving;

  return (
    <div className="space-y-5">
      <AdminPageHeader
        title="Speech outage announcements"
        description="Platform-wide control for what a caller hears when the configured speech service fails mid-call. Applies to every PSTN call that runs through the voice stack."
        actions={
          <SkeuoButton type="button" variant="ghost" onClick={() => void load()} disabled={working}>
            Reload
          </SkeuoButton>
        }
      />

      {error && (
        <p role="alert" className="rounded-skeuo-md border border-status-error/30 bg-status-error/10 px-4 py-3 text-sm text-status-error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="rounded-skeuo-md border border-success/30 bg-success/5 px-4 py-3 text-sm text-success">
          {notice}
        </p>
      )}

      <DevCard
        title="Universal outage switch"
        description="When enabled, a call that loses its speech service hears the recorded apology in the call language and then ends cleanly. When disabled, no outage recording is played on any call."
      >
        <div className="space-y-3">
          <div
            className={cn(
              "flex flex-col gap-3 rounded-xl border p-4 sm:flex-row sm:items-start sm:justify-between",
              enabled ? "border-success/30 bg-success/5" : "border-status-error/30 bg-status-error/5"
            )}
          >
            <div className="max-w-2xl">
              <p className="text-sm font-semibold text-text">Play the outage announcement</p>
              <p className="mt-1 text-xs leading-relaxed text-text-muted">
                {enabled
                  ? "Active everywhere. The platform recording (or the agent’s uploaded clip) plays only after speech actually fails; a delivered reply is never replaced."
                  : "Off everywhere. Failed calls end without the apology recording, and no callback is promised."}
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={enabled}
              aria-label="Play the outage announcement"
              disabled={working}
              onClick={() => setEnabled((value) => !value)}
              className={cn(
                "relative inline-flex h-7 w-12 shrink-0 items-center rounded-full border transition-colors disabled:opacity-50",
                enabled ? "border-success bg-success" : "border-surface-border bg-surface-panel-raised"
              )}
            >
              <span
                className={cn(
                  "inline-block h-5 w-5 rounded-full bg-white shadow transition-transform",
                  enabled ? "translate-x-6" : "translate-x-1"
                )}
              />
            </button>
          </div>

          <div className="flex flex-col gap-3 rounded-xl border border-surface-border-subtle p-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="max-w-2xl">
              <p className="text-sm font-semibold text-text">Promise a callback</p>
              <p className="mt-1 text-xs leading-relaxed text-text-muted">
                {promiseCallback
                  ? "Agents that allow it use the callback-promise recording, but only after a pending callback task is saved. If it cannot be saved, the safe call-back request plays instead."
                  : "Every agent uses the safe call-back request. No callback task is promised to the caller."}
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={promiseCallback}
              aria-label="Promise a callback"
              disabled={working || !enabled}
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
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <p className="text-[11px] text-text-subtle">
            Version {data?.global.version ?? 0} · updated {formatWhen(data?.global.updatedAt)}
            {data?.global.updatedBy ? ` by ${data.global.updatedBy}` : ""}
          </p>
          <div className="flex items-center gap-2">
            <SkeuoButton
              type="button"
              variant="ghost"
              disabled={working || !dirty}
              onClick={() => {
                if (!data) return;
                setEnabled(data.global.enabled);
                setPromiseCallback(data.global.promiseCallback);
                setNotice("");
              }}
            >
              Discard changes
            </SkeuoButton>
            <SkeuoButton
              type="button"
              variant="primary"
              disabled={!dirty || working}
              loading={saving}
              onClick={() => void save()}
            >
              Save platform settings
            </SkeuoButton>
          </div>
        </div>
      </DevCard>

      <DevCard
        title="Platform recordings"
        description="Shipped clips cover every supported Indian language. Per-agent recordings, where uploaded, take precedence over these platform clips."
      >
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-xs">
            <thead>
              <tr className="border-b border-surface-border-subtle text-[10px] uppercase tracking-wider text-text-subtle">
                <th className="px-3 py-2 font-semibold">Language</th>
                {variants.map((variant) => (
                  <th key={variant.id} className="px-3 py-2 font-semibold">
                    {variant.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {languages.map((code) => (
                <tr key={code} className="border-b border-surface-border-subtle last:border-0">
                  <td className="px-3 py-2 text-text">
                    {languageLabel(code)} <span className="font-mono text-[10px] text-text-subtle">{code}</span>
                  </td>
                  {variants.map((variant) => {
                    const coverage = data?.coverage?.[variant.id] || {};
                    const available = Boolean(
                      coverage.male?.includes(code) || coverage.female?.includes(code)
                    );
                    return (
                      <td key={variant.id} className="px-3 py-2">
                        <span
                          className={cn(
                            "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-semibold",
                            available
                              ? "bg-success/10 text-success"
                              : "bg-status-error/10 text-status-error"
                          )}
                        >
                          <span className={cn("size-1.5 rounded-full", available ? "bg-success" : "bg-status-error")} />
                          {available ? "Ready" : "Missing"}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-3 space-y-1 rounded-xl border border-surface-border-subtle bg-surface-panel-raised px-4 py-3">
          {variants.map((variant) => (
            <p key={variant.id} className="text-[11px] text-text-muted">
              <span className="font-semibold text-text">{variant.label}:</span>{" "}
              {VARIANT_HELP[variant.id] || "Recorded announcement used during a speech outage."}
            </p>
          ))}
        </div>
      </DevCard>

      <DevCard
        title="Per-agent recordings"
        description="An agent can use its own voice and wording instead of the platform recordings. The universal switch above still applies."
      >
        <p className="text-xs leading-relaxed text-text-muted">
          Open an agent workspace and choose <span className="font-semibold text-text">Outage Announcement</span> to
          upload clips per language and message, or to turn off callback promises for that agent only.
        </p>
        <div className="mt-3">
          <Link href="/dev/agents" className="text-xs font-semibold text-accent underline">
            Open agents →
          </Link>
        </div>
      </DevCard>
    </div>
  );
}
