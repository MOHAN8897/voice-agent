"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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

type BoostGraph = { ctx: AudioContext };

function AudioContextCtor(): typeof AudioContext {
  const w = window as Window & { webkitAudioContext?: typeof AudioContext };
  return w.AudioContext || w.webkitAudioContext || AudioContext;
}

async function connectPlaybackBoost(el: HTMLAudioElement, existing: BoostGraph | null): Promise<BoostGraph> {
  if (existing) {
    if (existing.ctx.state === "suspended") await existing.ctx.resume();
    return existing;
  }
  const ctx = new (AudioContextCtor())();
  const source = ctx.createMediaElementSource(el);
  const splitter = ctx.createChannelSplitter(2);
  const merger = ctx.createChannelMerger(2);
  const compressor = ctx.createDynamicsCompressor();
  compressor.threshold.value = -34;
  compressor.knee.value = 20;
  compressor.ratio.value = 12;
  compressor.attack.value = 0.003;
  compressor.release.value = 0.12;
  const makeup = ctx.createGain();
  makeup.gain.value = 4.2;
  source.connect(splitter);
  splitter.connect(merger, 0, 0);
  splitter.connect(merger, 0, 1);
  splitter.connect(merger, 1, 0);
  splitter.connect(merger, 1, 1);
  merger.connect(compressor);
  compressor.connect(makeup);
  makeup.connect(ctx.destination);
  if (ctx.state === "suspended") await ctx.resume();
  return { ctx };
}

export function CallAudioPanel({
  callId,
  title = "Play recording",
  description = "Clear mix is boosted and folded to both speakers so caller and agent are audible on a laptop",
  preferClearAudio = true,
}: {
  callId: string;
  title?: string;
  description?: string;
  /** Prefer peak-normalized WAV when available (generated at hangup). */
  preferClearAudio?: boolean;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const boostRef = useRef<BoostGraph | null>(null);
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
    return () => {
      const boost = boostRef.current;
      boostRef.current = null;
      if (boost) void boost.ctx.close();
    };
  }, [src]);

  useEffect(() => {
    if (!failed || retry >= 8) return;
    const timer = window.setTimeout(() => {
      setFailed(false);
      setRetry((n) => n + 1);
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [failed, retry]);

  const attachBoost = useCallback(async (el: HTMLAudioElement) => {
    boostRef.current = await connectPlaybackBoost(el, boostRef.current);
  }, []);

  async function playRecording() {
    const el = audioRef.current;
    if (!el || failed) return;
    try {
      el.volume = 1;
      await attachBoost(el);
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
              const el = audioRef.current;
              if (el) {
                el.volume = 1;
                void attachBoost(el);
              }
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
        Playback folds L/R to both speakers and applies ~4× review gain · Clear WAV is speech-normalized at hangup · Mix stereo L=caller R=agent
      </p>
    </SkeuoPanel>
  );
}
