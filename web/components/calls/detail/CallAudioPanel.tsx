"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { cn } from "@/lib/cn";
import { callAudioUrl } from "@/lib/pstn-trace-metrics";

type AudioKind = "mix" | "user" | "agent" | "mix_clear" | "user_clear" | "agent_clear";
type RecordingSource = "master" | "local" | "none";

const KIND_LABEL: Record<AudioKind, string> = {
  mix: "Mix (both)",
  mix_clear: "Clear mix",
  user: "Caller",
  user_clear: "Clear caller",
  agent: "Agent",
  agent_clear: "Clear agent",
};

const PLAYBACK_SPEEDS = [0.75, 1, 1.25, 1.5, 2];

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function CallAudioPanel({
  callId,
  title = "Recording playout",
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
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [recordingSource, setRecordingSource] = useState<RecordingSource>("none");

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const prevSource = useRef<RecordingSource>("none");
  const base = callAudioUrl(callId, kind);
  const src = `${base}${base.includes("?") ? "&" : "?"}r=${retry}`;

  const resolvedDescription =
    description ??
    (conversationOnly
      ? recordingSource === "master"
        ? "Enterprise Voice Network synchronized recording (caller and agent dual-channel mix)."
        : recordingSource === "local"
          ? "Playing high-fidelity local session mix while master trunk recording finalizes."
          : "Complete conversation recording. Master audio stream syncs automatically upon completion."
      : "Caller on the left channel, agent on the right channel. Peak-normalized clear mix.");

  useEffect(() => {
    setKind(preferClearAudio ? "mix_clear" : "mix");
  }, [callId, preferClearAudio]);

  useEffect(() => {
    setFailed(false);
    setRetry(0);
    setPlaying(false);
    setPaused(false);
    setCurrentTime(0);
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
          body.source === "telnyx" || body.source === "master"
            ? "master"
            : body.source === "local"
              ? "local"
              : "none";
        if (cancelled) return;
        setRecordingSource(next);
        if (next === "master") return;
      } catch {
        /* keep polling — master trunk recording finalizes shortly after hangup */
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
    if (recordingSource === "master" && prevSource.current !== "master") {
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
      el.volume = muted ? 0 : volume;
      el.playbackRate = playbackRate;
      await el.play();
      setPlaying(true);
      setPaused(false);
    } catch {
      setPlaying(false);
    }
  }, [failed, muted, volume, playbackRate]);

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
    setCurrentTime(0);
    setPlaying(false);
    setPaused(false);
  }

  function skip(deltaSeconds: number) {
    const el = audioRef.current;
    if (!el) return;
    const next = Math.max(0, Math.min(duration || 9999, el.currentTime + deltaSeconds));
    el.currentTime = next;
    setCurrentTime(next);
  }

  function handleSeek(targetSeconds: number) {
    const el = audioRef.current;
    if (!el) return;
    el.currentTime = targetSeconds;
    setCurrentTime(targetSeconds);
  }

  function handleRateChange(rate: number) {
    setPlaybackRate(rate);
    if (audioRef.current) {
      audioRef.current.playbackRate = rate;
    }
  }

  function handleVolumeChange(vol: number) {
    setVolume(vol);
    setMuted(vol === 0);
    if (audioRef.current) {
      audioRef.current.volume = vol;
      audioRef.current.muted = vol === 0;
    }
  }

  function toggleMute() {
    const nextMuted = !muted;
    setMuted(nextMuted);
    if (audioRef.current) {
      audioRef.current.muted = nextMuted;
      if (!nextMuted && volume === 0) {
        setVolume(1);
        audioRef.current.volume = 1;
      }
    }
  }

  function switchKind(next: AudioKind) {
    stopRecording();
    setKind(next);
    setFailed(false);
    setRetry(0);
  }

  const downloadRecording = useCallback(async () => {
    const downloadKind = conversationOnly ? "mix" : kind;
    const url = callAudioUrl(callId, downloadKind, true);
    try {
      const response = await fetch(url, { credentials: "include", cache: "no-store" });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = `${callId}-conversation.mp3`;
      anchor.rel = "noopener";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
    } catch {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  }, [callId, conversationOnly, kind]);

  const sourceLabel =
    recordingSource === "master"
      ? "Direct Voice Trunk"
      : recordingSource === "local"
        ? "Local session mix"
        : "Recording pending";

  const progressPercent = duration > 0 ? Math.min(100, (currentTime / duration) * 100) : 0;

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

      {/* Main Transport & Actions Toolbar */}
      <div className={conversationOnly ? "flex flex-wrap items-center gap-2" : "mt-4 flex flex-wrap items-center gap-2"}>
        <SkeuoButton
          type="button"
          variant="primary"
          size="sm"
          disabled={failed}
          onClick={() => void (playing ? pauseRecording() : playRecording())}
          className="min-w-[80px]"
        >
          {playing ? "Pause" : paused ? "Resume" : "Play"}
        </SkeuoButton>

        <SkeuoButton
          type="button"
          variant="secondary"
          size="sm"
          disabled={failed || (!playing && !paused && currentTime === 0)}
          onClick={stopRecording}
        >
          Stop
        </SkeuoButton>

        {/* Skip controls */}
        <button
          type="button"
          onClick={() => skip(-10)}
          disabled={failed || duration === 0}
          title="Rewind 10 seconds"
          className="rounded-skeuo-sm border border-surface-border-subtle bg-surface px-2.5 py-1 text-xs font-mono font-medium text-text-muted hover:text-text disabled:opacity-40"
        >
          -10s
        </button>

        <button
          type="button"
          onClick={() => skip(10)}
          disabled={failed || duration === 0}
          title="Fast forward 10 seconds"
          className="rounded-skeuo-sm border border-surface-border-subtle bg-surface px-2.5 py-1 text-xs font-mono font-medium text-text-muted hover:text-text disabled:opacity-40"
        >
          +10s
        </button>

        {/* Playback speed selector */}
        <div className="flex items-center gap-1 rounded-skeuo-sm border border-surface-border-subtle bg-surface-base/80 p-0.5">
          {PLAYBACK_SPEEDS.map((rate) => (
            <button
              key={rate}
              type="button"
              onClick={() => handleRateChange(rate)}
              className={cn(
                "rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold transition-all",
                playbackRate === rate
                  ? "bg-accent-primary text-white shadow-sm"
                  : "text-text-muted hover:text-text"
              )}
            >
              {rate}x
            </button>
          ))}
        </div>

        <SkeuoButton
          type="button"
          variant="secondary"
          size="sm"
          disabled={failed}
          onClick={() => void downloadRecording()}
        >
          {conversationOnly ? "Download MP3" : "Download track"}
        </SkeuoButton>

        {!conversationOnly ? (
          <SkeuoButton
            type="button"
            variant="secondary"
            size="sm"
            disabled={failed}
            onClick={() => {
              const clearKind = kind.endsWith("_clear") ? kind : (`${kind}_clear` as AudioKind);
              void (async () => {
                const url = callAudioUrl(callId, clearKind, true);
                const response = await fetch(url, { credentials: "include", cache: "no-store" });
                if (!response.ok) return;
                const blob = await response.blob();
                const objectUrl = URL.createObjectURL(blob);
                const anchor = document.createElement("a");
                anchor.href = objectUrl;
                anchor.download = `${callId}-${clearKind}.wav`;
                anchor.click();
                URL.revokeObjectURL(objectUrl);
              })();
            }}
          >
            Download clear WAV
          </SkeuoButton>
        ) : null}

        <span
          className={cn(
            "ml-auto rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider",
            recordingSource === "master"
              ? "bg-emerald-500/15 text-emerald-600 border border-emerald-500/30"
              : recordingSource === "local"
                ? "bg-amber-500/15 text-amber-600 border border-amber-500/30"
                : "bg-surface-raised text-text-muted border border-surface-border-subtle"
          )}
        >
          {sourceLabel}
        </span>
      </div>

      {/* Interactive Playout Scrubber Box */}
      <div className="mt-4 skeuo-inset rounded-skeuo-md p-4">
        {!failed ? (
          <div className="space-y-3">
            {/* Native hidden audio element for precise control */}
            <audio
              ref={audioRef}
              key={src}
              preload="metadata"
              src={src}
              onTimeUpdate={() => {
                if (audioRef.current) {
                  setCurrentTime(audioRef.current.currentTime);
                }
              }}
              onDurationChange={() => {
                if (audioRef.current && Number.isFinite(audioRef.current.duration)) {
                  setDuration(audioRef.current.duration);
                }
              }}
              onLoadedMetadata={() => {
                if (audioRef.current && Number.isFinite(audioRef.current.duration)) {
                  setDuration(audioRef.current.duration);
                  audioRef.current.playbackRate = playbackRate;
                }
              }}
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
                setCurrentTime(0);
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

            {/* Custom Interactive Scrubber Range Slider */}
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs text-text-subtle min-w-[38px] text-right">
                {formatTime(currentTime)}
              </span>

              <div className="relative flex-1 flex items-center">
                <input
                  type="range"
                  min={0}
                  max={duration || 100}
                  step={0.1}
                  value={currentTime}
                  onChange={(e) => handleSeek(parseFloat(e.target.value))}
                  disabled={duration === 0}
                  className="w-full h-2 bg-surface-raised rounded-lg appearance-none cursor-pointer accent-accent-primary focus:outline-none"
                  aria-label="Seek audio playback"
                />
              </div>

              <span className="font-mono text-xs text-text-subtle min-w-[38px]">
                {formatTime(duration)}
              </span>

              {/* Volume / Mute button */}
              <div className="flex items-center gap-1.5 pl-2 border-l border-surface-border-subtle">
                <button
                  type="button"
                  onClick={toggleMute}
                  title={muted ? "Unmute" : "Mute"}
                  className="text-text-muted hover:text-text transition-colors p-1"
                >
                  {muted || volume === 0 ? (
                    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M11 5L6 9H2v6h4l5 4V5zM23 9l-6 6M17 9l6 6" />
                    </svg>
                  ) : (
                    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M11 5L6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07" />
                    </svg>
                  )}
                </button>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={muted ? 0 : volume}
                  onChange={(e) => handleVolumeChange(parseFloat(e.target.value))}
                  className="w-16 h-1.5 bg-surface-raised rounded appearance-none cursor-pointer accent-accent-primary"
                  aria-label="Volume slider"
                />
              </div>
            </div>

            {/* Audio Waveform progress meter */}
            <div className="h-1.5 w-full bg-surface-raised/80 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-accent-primary/80 to-accent-primary transition-all duration-100 rounded-full"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>
        ) : (
          <p className="text-sm text-text-muted">
            {KIND_LABEL[kind]} archive recording is processing — please allow a few seconds for the trunk archive to synchronize.
          </p>
        )}
      </div>

      <p className="mt-2 font-mono text-[10px] text-text-subtle">
        {conversationOnly
          ? "Synchronized conversation playout with noise-cleared voice normalization · updates in real-time"
          : "Caller Left / Agent Right channel separation · master audio stream"}
      </p>
    </SkeuoPanel>
  );
}
