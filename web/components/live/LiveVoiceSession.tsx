"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AudioPlaybackManager } from "@/lib/audio-playback";
import { shouldBargeWhileSpeaking, type BargeState } from "@/lib/live-guards";
import { wsUrl } from "@/lib/api";

type Bubble = { role: "user" | "assistant"; text: string };

export type SessionTraceEvent = { at: number; kind: string; detail: string };

function wordCount(t: string): number {
  return (t.trim().match(/\S+/g) || []).length;
}

export function LiveVoiceSession({
  agentId,
  tier,
  variant = "default",
  onTrace,
  onCallStart,
  onCallEnd,
  onStatusChange,
  onMicLevel,
}: {
  agentId?: string;
  tier?: string;
  variant?: "default" | "dev";
  onTrace?: (event: SessionTraceEvent) => void;
  onCallStart?: (callId: string) => void;
  onCallEnd?: (callId: string) => void;
  onStatusChange?: (status: string) => void;
  onMicLevel?: (level: number) => void;
}) {
  const [status, setStatus] = useState("idle");
  const [listening, setListening] = useState(false);
  const [partial, setPartial] = useState("");
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const callIdRef = useRef<string | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const playbackRef = useRef<AudioPlaybackManager | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const workletRef = useRef<AudioWorkletNode | null>(null);
  const listeningRef = useRef(false);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const levelTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const bargeRef = useRef<BargeState>({
    bargeHandledTurn: 0,
    lastBargeInAt: 0,
    busy: false,
    brainStreaming: false,
    agentSpeaking: false,
    elapsedMs: 0,
    words: 0,
    sawVadStart: false,
    bargeCooldownUntil: 0,
    turnN: 0,
  });

  const trace = useCallback(
    (kind: string, detail: string) => {
      onTrace?.({ at: Date.now(), kind, detail });
    },
    [onTrace]
  );

  const setSessionStatus = useCallback(
    (next: string) => {
      setStatus(next);
      onStatusChange?.(next);
    },
    [onStatusChange]
  );

  const stopMicMeter = useCallback(() => {
    if (levelTimerRef.current) {
      clearInterval(levelTimerRef.current);
      levelTimerRef.current = null;
    }
    analyserRef.current = null;
    onMicLevel?.(0);
  }, [onMicLevel]);

  const startMicMeter = useCallback(
    (ctx: AudioContext, src: MediaStreamAudioSourceNode) => {
      if (!onMicLevel) return;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      src.connect(analyser);
      analyserRef.current = analyser;
      const buf = new Uint8Array(analyser.frequencyBinCount);
      levelTimerRef.current = setInterval(() => {
        analyser.getByteFrequencyData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i += 1) sum += buf[i];
        onMicLevel(Math.min(1, sum / (buf.length * 255) * 2.5));
      }, 60);
    },
    [onMicLevel]
  );

  useEffect(() => {
    if (audioRef.current && !playbackRef.current) {
      playbackRef.current = new AudioPlaybackManager(audioRef.current);
    }
  }, []);

  const addBubble = useCallback((role: Bubble["role"], text: string) => {
    setBubbles((prev) => [...prev, { role, text }]);
  }, []);

  const startCall = useCallback(async () => {
    const r = await fetch("/api/call/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agentId, tier, channel: "browser", direction: "inbound" }),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail?.error?.message || "Call start failed");
    callIdRef.current = j.call_id;
    trace("call", `started ${j.call_id}`);
    onCallStart?.(j.call_id);
    return j.call_id as string;
  }, [agentId, tier, trace, onCallStart]);

  const endCall = useCallback(async () => {
    if (!callIdRef.current) return;
    const id = callIdRef.current;
    await fetch("/api/call/end", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ callId: id, reason: "user_stop" }),
    });
    trace("call", `ended ${id}`);
    onCallEnd?.(id);
    callIdRef.current = null;
  }, [trace, onCallEnd]);

  const runBrainTurn = useCallback(
    async (text: string) => {
      const qs = callIdRef.current ? `?callId=${encodeURIComponent(callIdRef.current)}` : "";
      bargeRef.current.brainStreaming = true;
      bargeRef.current.busy = true;
      setSessionStatus("thinking");
      trace("brain", "stream start");
      addBubble("user", text);
      const r = await fetch(`/api/brain/stream${qs}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript: text, language_code: "te-IN" }),
      });
      let out = "";
      const raw = await r.text();
      for (const line of raw.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6);
        if (payload === "[DONE]") break;
        try {
          const ev = JSON.parse(payload);
          if (ev.delta) out += ev.delta;
          if (ev.text) out = ev.text;
        } catch {
          /* skip */
        }
      }
      bargeRef.current.brainStreaming = false;
      bargeRef.current.busy = false;
      trace("brain", `stream done ${out.length} chars`);
      if (out) {
        addBubble("assistant", out);
        setSessionStatus("speaking");
        bargeRef.current.agentSpeaking = true;
        try {
          trace("tts", "request");
          const ttsR = await fetch("/api/tts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: out, language_code: "te-IN" }),
          });
          const ttsJ = await ttsR.json();
          if (ttsJ.audio_base64 && playbackRef.current) {
            playbackRef.current.userGesture();
            await playbackRef.current.enqueueBase64(ttsJ.audio_base64, ttsJ.content_type || "audio/wav");
            trace("tts", "playback queued");
          }
        } catch {
          /* TTS optional */
        }
        bargeRef.current.agentSpeaking = false;
      }
      setSessionStatus(listening ? "listening" : "idle");
    },
    [addBubble, listening, trace, setSessionStatus]
  );

  const cleanupLive = useCallback(() => {
    listeningRef.current = false;
    const sock = socketRef.current;
    socketRef.current = null;
    if (sock && sock.readyState === WebSocket.OPEN) {
      try {
        sock.close();
      } catch {
        /* ignore */
      }
    }
    if (workletRef.current) {
      try {
        workletRef.current.disconnect();
      } catch {
        /* ignore */
      }
      workletRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => {
        try {
          t.stop();
        } catch {
          /* ignore */
        }
      });
      streamRef.current = null;
    }
    const ctx = ctxRef.current;
    ctxRef.current = null;
    if (ctx && ctx.state !== "closed") {
      ctx.close().catch(() => {});
    }
    playbackRef.current?.stop();
    stopMicMeter();
    setListening(false);
    setPartial("");
    setSessionStatus("idle");
  }, [setSessionStatus, stopMicMeter]);

  useEffect(() => {
    const cleanup = cleanupLive;
    return () => {
      cleanup();
    };
    // Unmount only — do not tie to cleanupLive identity
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stopListening = useCallback(async () => {
    try {
      socketRef.current?.send(JSON.stringify({ event: "end" }));
    } catch {
      /* ignore */
    }
    cleanupLive();
    await endCall();
  }, [cleanupLive, endCall]);

  const startListening = useCallback(async () => {
    playbackRef.current?.userGesture();
    setSessionStatus("connecting");
    try {
      await startCall();
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;
      const ctx = new AudioContext({ sampleRate: 16000 });
      ctxRef.current = ctx;
      await ctx.audioWorklet.addModule("/pcm-worklet.js");
      const src = ctx.createMediaStreamSource(stream);
      startMicMeter(ctx, src);
      const worklet = new AudioWorkletNode(ctx, "pcm-processor");
      workletRef.current = worklet;
      worklet.port.onmessage = (ev) => {
        const sock = socketRef.current;
        if (!sock || sock.readyState !== WebSocket.OPEN) return;
        const int16 = ev.data as Int16Array;
        sock.send(int16.buffer);
        const st = bargeRef.current;
        st.words = wordCount(partial);
        if (shouldBargeWhileSpeaking(st, Date.now()) && playbackRef.current) {
          playbackRef.current.stop();
          st.agentSpeaking = false;
        }
      };
      src.connect(worklet);

      const q = new URLSearchParams({
        language_code: "te-IN",
        stream_type: "fast",
        mode: "transcribe",
      });
      if (callIdRef.current) q.set("call_id", callIdRef.current);
      const sock = new WebSocket(`${wsUrl("/ws/stt-realtime")}?${q}`);
      socketRef.current = sock;
      sock.binaryType = "arraybuffer";
      sock.onopen = () => {
        listeningRef.current = true;
        setListening(true);
        setSessionStatus("listening");
        trace("stt", "websocket open");
      };
      sock.onmessage = (ev) => {
        let m: { type?: string; text?: string; transcript?: string };
        try {
          m = JSON.parse(ev.data as string);
        } catch {
          return;
        }
        const text = (m.text || m.transcript || "").trim();
        if (!text) return;
        if (m.type === "partial" || m.type === "speech_start") {
          setPartial(text);
          if (m.type === "speech_start") {
            bargeRef.current.sawVadStart = true;
            trace("vad", "speech start");
          }
          return;
        }
        if (m.type === "final" || m.type === "transcript") {
          setPartial("");
          trace("stt", `final ${text.slice(0, 40)}`);
          runBrainTurn(text);
        }
      };
      sock.onclose = () => {
        if (listeningRef.current) stopListening();
      };
    } catch (e) {
      const msg =
        e instanceof DOMException && e.name === "AbortError"
          ? "Microphone setup was interrupted"
          : e instanceof Error
            ? e.message
            : "Mic error";
      setSessionStatus(msg);
      cleanupLive();
      await endCall();
    }
  }, [cleanupLive, endCall, partial, runBrainTurn, startCall, stopListening, listening, trace, setSessionStatus, startMicMeter]);

  const isDev = variant === "dev";

  return (
    <div>
      {!isDev && (
        <div className="flex items-center justify-between">
          <h2 className="font-medium text-text">Live voice session</h2>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-surface-border px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-text-muted">
            {status === "listening" && <span className="h-1.5 w-1.5 rounded-full bg-agent-online animate-pulse-dot" />}
            {status}
          </span>
        </div>
      )}
      <div className={`flex flex-wrap gap-2 ${isDev ? "" : "mt-4"}`}>
        {!listening ? (
          <button
            type="button"
            onClick={startListening}
            className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white"
          >
            Start listening
          </button>
        ) : (
          <button
            type="button"
            onClick={stopListening}
            className="rounded-xl border border-red-500/50 px-4 py-2 text-sm text-red-300"
          >
            Stop listening
          </button>
        )}
        <button type="button" onClick={endCall} className="rounded-xl border border-surface-border px-4 py-2 text-sm text-text">
          End call
        </button>
      </div>

      <section
        className="mt-4 max-h-64 overflow-y-auto rounded-xl border border-surface-border-subtle bg-surface p-3"
        aria-label="Live transcript"
        role="region"
      >
        {bubbles.length === 0 && !partial ? (
          <p className="text-sm text-text-muted">Start listening — your speech and agent replies appear here.</p>
        ) : (
          <div className="space-y-2">
            {bubbles.map((b, i) => (
              <div
                key={`${b.role}-${i}`}
                className={`rounded-lg px-3 py-2 text-sm ${
                  b.role === "user" ? "bg-surface-raised" : "border border-accent/20 bg-accent-dim/40"
                }`}
              >
                <span className="text-xs font-medium text-text-muted">{b.role === "user" ? "You" : "Agent"}</span>
                <p>{b.text}</p>
              </div>
            ))}
            {partial && (
              <div className="rounded px-3 py-2 text-sm text-text-muted opacity-80">
                <span className="text-xs font-medium">You (live)</span>
                <p>{partial}</p>
              </div>
            )}
          </div>
        )}
      </section>

      <audio ref={audioRef} className={`w-full ${isDev ? "mt-3" : "mt-4"}`} controls aria-label="Agent audio playback" />
      {!isDev && (
        <p className="mt-2 text-xs text-text-muted">
          WS STT · pcm-worklet · live-guards barge-in · SSE brain stream
        </p>
      )}
    </div>
  );
}
