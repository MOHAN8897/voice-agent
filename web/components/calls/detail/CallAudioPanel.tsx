"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { cn } from "@/lib/cn";
import { callAudioUrl } from "@/lib/pstn-trace-metrics";

type AudioKind = "mix" | "user" | "agent" | "mix_clear" | "user_clear" | "agent_clear";
type RecordingSource = "telnyx" | "local" | "none";

const KIND_LABEL: Record<AudioKind, string> = {
  mix: "Mix (both)",
  mix_clear: "Clear mix",
  user: "Caller",
  user_clear: "Clear caller",
  agent: "Agent",
  agent_clear: "Clear agent",
};

export function CallAudioPanel({
  callId,
  title = "Play recording",
  description,
  preferClearAudio = true,
  conversationOnly = true,
}: {
  callId: string;
  title?: string;
  description?: string;
  /** Prefer peak-normalized WAV when available (generated at hangup). */
  preferClearAudio?: boolean;
  /** History/review: one complete conversation mix, no per-track downloads. */
  conversationOnly?: boolean;
}) {
  const [kind, setKind] = useState<AudioKind>(preferClearAudio ? "mix_clear" : "mix");
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [paused, setPaused] = useState(false);
  const [recordingSource, setRecordingSource] = useState<RecordingSource>("none");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const prevSource = useRef<RecordingSource>("none");
  const base = callAudioUrl(callId, kind);
  const src = `${base}${base.includes("?") ? "&" : "?"}r=${retry}`;

  const resolvedDescription =
    description ??
    (conversationOnly
      ? recordingSource === "telnyx"
        ? "Telnyx call recording (both speakers). Caller and agent are mixed onto both channels."
        : recordingSource === "local"
          ? "Waiting for the Telnyx recording. Playing the local mix until Telnyx saves the call."
          : "Complete conversation. Telnyx recording is used as soon as Telnyx saves it."
      : "Caller on the left, agent on the right. Clear mix is peak-normalized at hangup.");

  useEffect(() => {
    setKind(preferClearAudio ? "mix_clear" : "mix");
  }, [callId, preferClearAudio]);

  useEffect(() => {
    setFailed(false);
    setRetry(0);
    setPlaying(false);
    setPaused(false);
  }, [callId, kind]);

  useEffect(() => {
    setRecordingSource("none");
    prevSource.current = "none";
  }, [callId]);

  useEffect(() => {
    if (!callId) return;
    let cancelled = false;
    let attempts = 0;
    let timer = 0;

    const tick = async () => {
      try {
        const response = await fetch(`/api/call/${encodeURIComponent(callId)}/audio-status`, {
          cache: "no-store",
        });
        if (!response.ok || cancelled) return;
        const body = (await response.json()) as { source?: string };
        const next: RecordingSource =
          body.source === "telnyx" ? "telnyx" : body.source === "local" ? "local" : "none";
        if (cancelled) return;
        setRecordingSource(next);
        if (next === "telnyx") return;
      } catch {
        /* keep polling — Telnyx save often arrives ~10s after hangup */
      }
      attempts += 1;
      if (!cancelled && attempts < 24) {
        timer = window.setTimeout(() => void tick(), 1500);
      }
    };

    void tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [callId]);

  useEffect(() => {
    if (recordingSource === "telnyx" && prevSource.current !== "telnyx") {
      setRetry((n) => n + 1);
      setFailed(false);
      setPlaying(false);
      setPaused(false);
    }
    prevSource.current = recordingSource;
  }, [recordingSource]);

  useEffect(() => {
    if (!failed || retry >= 8) return;
    const timer = window.setTimeout(() => {
      setFailed(false);
      setRetry((n) => n + 1);
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [failed, retry]);

  const playRecording = useCallback(async () => {
    const el = audioRef.current;
    if (!el || failed) return;
    try {
      el.volume = 1;
      await el.play();
      setPlaying(true);
      setPaused(false);
    } catch {
      setPlaying(false);
    }
  }, [failed]);

  function pauseRecording() {
    const el = audioRef.current;
    if (!el) return;
    el.pause();
    setPlaying(false);
    setPaused(el.currentTime > 0);
  }

  function stopRecording() {
    const el = audioRef.current;
    if (!el) return;
    el.pause();
    el.currentTime = 0;
    setPlaying(false);
    setPaused(false);
  }

  function switchKind(next: AudioKind) {
    stopRecording();
    setKind(next);
    setFailed(false);
    setRetry(0);
  }

  const sourceLabel =
    recordingSource === "telnyx"
      ? "Telnyx recording"
      : recordingSource === "local"
        ? "Local mix · waiting for Telnyx"
        : "Recording pending";

  return (
    <SkeuoPanel title={title} description={resolvedDescription} padding="md">
      {!conversationOnly ? (
        <div className="flex flex-wrap gap-2">
          {(preferClearAudio
            ? (["mix_clear", "user_clear", "agent_clear", "mix"] as AudioKind[])
            : (["mix", "user", "agent"] as AudioKind[])
          ).map((k) => (
            <SkeuoButton
              key={k}
              variant={kind === k ? "primary" : "secondary"}
              size="sm"
              onClick={() => switchKind(k)}
            >
              {KIND_LABEL[k]}
            </SkeuoButton>
          ))}
        </div>
      ) : null}

      <div className={conversationOnly ? "flex flex-wrap items-center gap-2" : "mt-4 flex flex-wrap items-center gap-2"}>
        <SkeuoButton
          type="button"
          variant="primary"
          size="sm"
          disabled={failed}
          onClick={() => void (playing ? pauseRecording() : playRecording())}
        >
          {playing ? "Pause" : paused ? "Resume" : "Play"}
        </SkeuoButton>
        <SkeuoButton type="button" variant="secondary" size="sm" disabled={failed || (!playing && !paused)} onClick={stopRecording}>
          Stop
        </SkeuoButton>
        <Link
          href={callAudioUrl(callId, kind, true)}
          className="inline-flex items-center rounded-lg border border-surface-border px-3 py-2 text-xs font-medium hover:bg-surface-raised"
        >
          {conversationOnly ? "Download conversation" : "Download this track"}
        </Link>
        {!conversationOnly ? (
          <Link
            href={callAudioUrl(callId, kind.endsWith("_clear") ? kind : (`${kind}_clear` as AudioKind), true)}
            className="inline-flex items-center rounded-lg border border-surface-border px-3 py-2 text-xs font-medium hover:bg-surface-raised"
          >
            Download clear WAV
          </Link>
        ) : null}
        <span
          className={cn(
            "rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-wide",
            recordingSource === "telnyx"
              ? "bg-emerald-500/15 text-emerald-700"
              : "bg-surface-raised text-text-muted"
          )}
        >
          {sourceLabel}
        </span>
      </div>

      <div className="mt-4 skeuo-inset rounded-skeuo-md p-4">
        {!failed ? (
          <audio
            ref={audioRef}
            key={src}
            controls
            preload="metadata"
            src={src}
            className="w-full"
            onPlay={() => {
              const el = audioRef.current;
              if (el) el.volume = 1;
              setPlaying(true);
              setPaused(false);
            }}
            onPause={() => {
              setPlaying(false);
              const t = audioRef.current?.currentTime || 0;
              setPaused(t > 0.05);
            }}
            onEnded={() => {
              setPlaying(false);
              setPaused(false);
            }}
            onError={() => {
              if (kind.endsWith("_clear")) {
                switchKind(kind.replace("_clear", "") as AudioKind);
                return;
              }
              setFailed(true);
              setPlaying(false);
            }}
          />
        ) : (
          <p className="text-sm text-text-muted">
            {KIND_LABEL[kind]} archive not available yet — hang up and wait a few seconds for the Telnyx recording.
          </p>
        )}
      </div>

      <p className={cn("mt-2 font-mono text-[10px] text-text-subtle")}>
        {conversationOnly
          ? "History plays the Telnyx-saved conversation (not the local overlapped mix) · reloads when Telnyx finishes saving"
          : "Caller L / agent R · Telnyx recording is used when present"}
      </p>
    </SkeuoPanel>
  );
}
