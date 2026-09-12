"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { cn } from "@/lib/cn";
import { callAudioUrl } from "@/lib/pstn-trace-metrics";

type AudioKind = "mix" | "user" | "agent" | "mix_clear" | "user_clear" | "agent_clear";

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
  description = "Clear mix is peak-normalized for dev review — louder and easier to hear on laptop speakers",
  preferClearAudio = false,
}: {
  callId: string;
  title?: string;
  description?: string;
  /** Prefer peak-normalized WAV when available (generated at hangup). */
  preferClearAudio?: boolean;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [kind, setKind] = useState<AudioKind>(preferClearAudio ? "mix_clear" : "mix");
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [paused, setPaused] = useState(false);
  const base = callAudioUrl(callId, kind);
  const src = `${base}${base.includes("?") ? "&" : "?"}r=${retry}`;

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
    if (!failed || retry >= 8) return;
    const timer = window.setTimeout(() => {
      setFailed(false);
      setRetry((n) => n + 1);
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [failed, retry]);

  async function playRecording() {
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
  }

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

  return (
    <SkeuoPanel title={title} description={description} padding="md">
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

      <div className="mt-4 flex flex-wrap gap-2">
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
          Download this track
        </Link>
        <Link
          href={callAudioUrl(callId, kind.endsWith("_clear") ? kind : (`${kind}_clear` as AudioKind), true)}
          className="inline-flex items-center rounded-lg border border-surface-border px-3 py-2 text-xs font-medium hover:bg-surface-raised"
        >
          Download clear WAV
        </Link>
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
            {KIND_LABEL[kind]} archive not available yet — hang up and wait a few seconds for mix.wav.
          </p>
        )}
      </div>

      <p className={cn("mt-2 font-mono text-[10px] text-text-subtle")}>
        Clear tracks boost quiet PSTN audio up to 4× toward ~90% peak · Play / Pause / Stop or native controls · Mix stereo L=caller R=agent
      </p>
    </SkeuoPanel>
  );
}
