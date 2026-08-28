"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { parseSseDataLines, wordCount } from "@/lib/early-tts";
import { StreamingAudioPlayback } from "@/lib/voice/streaming-audio-playback";
import { StreamingTtsClient } from "@/lib/voice/streaming-tts-client";
import { TurnTtsPipeline } from "@/lib/voice/turn-tts-pipeline";
import { isLikelyEcho, POST_SPEAK_COOLDOWN_MS } from "@/lib/echo-guard";
import { shouldBargeWhileSpeaking, type BargeState } from "@/lib/live-guards";
import { apiOrigin, wsUrl } from "@/lib/api";

export type Bubble = { role: "user" | "assistant"; text: string; interrupted?: boolean; ts?: number };

export type SessionTraceEvent = { at: number; kind: string; detail: string };

export type TurnCompleteEvent = {
  turn: number;
  userText: string;
  assistantText: string;
  at: number;
  usage?: {
    input_tokens?: number;
    output_tokens?: number;
    cached_tokens?: number;
    cache_write_tokens?: number;
  };
  memoryUpdate?: { operations?: unknown[] };
};

export type LiveVoiceSessionHandle = {
  startListening: () => void;
  pauseListening: () => void;
  stopListening: () => void;
  endCall: () => void;
};

function parseSttPayload(raw: string): {
  event: string;
  text: string;
  fatal: boolean;
  message: string;
} {
  try {
    const m = JSON.parse(raw) as Record<string, unknown>;
    const data = m.data as Record<string, unknown> | undefined;
    const event = String(m.event || m.type || "");
    const text = String(m.text ?? data?.text ?? m.transcript ?? "").trim();
    return {
      event,
      text,
      fatal: Boolean(m.is_fatal),
      message: String(m.message || m.code || ""),
    };
  } catch {
    return { event: "", text: "", fatal: false, message: "" };
  }
}

export const LiveVoiceSession = forwardRef<LiveVoiceSessionHandle, {
  agentId?: string;
  tier?: string;
  languageCode?: string;
  stackOverride?: Record<string, unknown>;
  sessionId?: string;
  variant?: "default" | "dev" | "lab";
  onTrace?: (event: SessionTraceEvent) => void;
  onCallStart?: (callId: string) => void;
  onCallEnd?: (callId: string) => void;
  onStatusChange?: (status: string) => void;
  onMicLevel?: (level: number) => void;
  onTranscriptChange?: (bubbles: Bubble[], partial: string) => void;
  onTurnComplete?: (event: TurnCompleteEvent) => void;
}>(function LiveVoiceSession({
  agentId,
  tier,
  languageCode = "te-IN",
  stackOverride,
  sessionId,
  variant = "default",
  onTrace,
  onCallStart,
  onCallEnd,
  onStatusChange,
  onMicLevel,
  onTranscriptChange,
  onTurnComplete,
}, ref) {
  const [status, setStatus] = useState("idle");
  const [listening, setListening] = useState(false);
  const [partial, setPartial] = useState("");
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const callIdRef = useRef<string | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const playbackRef = useRef<StreamingAudioPlayback | null>(null);
  const ttsClientRef = useRef<StreamingTtsClient | null>(null);
  const activePipelineRef = useRef<TurnTtsPipeline | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const workletRef = useRef<AudioWorkletNode | null>(null);
  const listeningRef = useRef(false);
  const startingRef = useRef(false);
  const intentionalStopRef = useRef(false);
  const partialRef = useRef("");
  const turnCounterRef = useRef(0);
  const onTurnCompleteRef = useRef(onTurnComplete);
  onTurnCompleteRef.current = onTurnComplete;
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
  const brainAbortRef = useRef<AbortController | null>(null);
  const pendingFinalsRef = useRef<string[]>([]);
  const awaitingBargeRef = useRef(false);
  const speakCooldownUntilRef = useRef(0);
  const lastAssistantTextRef = useRef("");
  const turnGenRef = useRef(0);

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
    if (!playbackRef.current) {
      playbackRef.current = new StreamingAudioPlayback();
    }
    if (!ttsClientRef.current) {
      ttsClientRef.current = new StreamingTtsClient({
        sessionId: sessionId || "default",
        callId: callIdRef.current,
        languageCode,
        trace: (kind, detail) => trace(kind, detail),
      });
    }
    playbackRef.current.setTrace((kind, detail) => trace(kind, detail));
    return () => {
      activePipelineRef.current?.cancel();
      ttsClientRef.current?.close();
      playbackRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const addBubble = useCallback((role: Bubble["role"], text: string) => {
    setBubbles((prev) => [...prev, { role, text, ts: Date.now() }]);
  }, []);

  const markLastAssistantInterrupted = useCallback(() => {
    setBubbles((prev) => {
      const idx = prev.map((b, i) => (b.role === "assistant" ? i : -1)).filter((i) => i >= 0).pop();
      if (idx == null) return prev;
      return prev.map((b, i) => (i === idx ? { ...b, interrupted: true } : b));
    });
  }, []);

  const onTranscriptChangeRef = useRef(onTranscriptChange);
  onTranscriptChangeRef.current = onTranscriptChange;

  useEffect(() => {
    partialRef.current = partial;
  }, [partial]);

  useEffect(() => {
    onTranscriptChangeRef.current?.(bubbles, partial);
  }, [bubbles, partial]);

  const startCall = useCallback(async () => {
    const r = await fetch("/api/call/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        agentId,
        tier,
        channel: "browser",
        direction: "inbound",
        language: languageCode,
        sessionId,
        stackOverride,
      }),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail?.error?.message || "Call start failed");
    callIdRef.current = j.call_id;
    trace("call", `started ${j.call_id}`);
    onCallStart?.(j.call_id);
    return j.call_id as string;
  }, [agentId, tier, languageCode, sessionId, stackOverride, trace, onCallStart]);

  const endCall = useCallback(async () => {
    if (!callIdRef.current) return;
    const id = callIdRef.current;
    await fetch("/api/call/end", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ callId: id, reason: "user_stop" }),
    });
    trace("call", `ended ${id}`);
    onCallEnd?.(id);
    callIdRef.current = null;
    setSessionStatus("ended");
  }, [trace, onCallEnd]);

  const runBrainTurnRef = useRef<(text: string) => void>(() => {});

  const doBargeIn = useCallback(
    (reason: string) => {
      const st = bargeRef.current;
      const now = Date.now();
      if (!st.agentSpeaking && !st.busy && !st.brainStreaming) return;
      if (st.bargeHandledTurn === st.turnN && now - st.lastBargeInAt < 800) return;

      st.lastBargeInAt = now;
      st.bargeHandledTurn = st.turnN;
      st.agentSpeaking = false;
      st.brainStreaming = false;
      st.busy = false;
      st.bargeCooldownUntil = now + 250;
      awaitingBargeRef.current = true;
      pendingFinalsRef.current = [];
      turnGenRef.current += 1;

      brainAbortRef.current?.abort();
      brainAbortRef.current = null;
      playbackRef.current?.stop();
      markLastAssistantInterrupted();
      trace("vad", `barge-in ${reason}`);

      fetch(`${apiOrigin()}/api/session/interrupt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ sessionId: sessionId || "default" }),
      }).catch(() => {});
      setSessionStatus(listeningRef.current ? "listening" : "idle");
    },
    [markLastAssistantInterrupted, sessionId, setSessionStatus, trace]
  );

  const runBrainTurn = useCallback(
    async (text: string) => {
      const qs = callIdRef.current ? `?callId=${encodeURIComponent(callIdRef.current)}` : "";
      const turnGen = ++turnGenRef.current;
      brainAbortRef.current?.abort();
      const abort = new AbortController();
      brainAbortRef.current = abort;

      bargeRef.current.turnN += 1;
      bargeRef.current.brainStreaming = true;
      bargeRef.current.busy = true;
      bargeRef.current.sawVadStart = false;
      awaitingBargeRef.current = false;
      setSessionStatus("thinking");
      trace("brain", "stream start");
      addBubble("user", text);

      const turnId = `turn-${bargeRef.current.turnN}`;
      if (!playbackRef.current) {
        playbackRef.current = new StreamingAudioPlayback();
      }
      if (!ttsClientRef.current) {
        ttsClientRef.current = new StreamingTtsClient({
          sessionId: sessionId || "default",
          callId: callIdRef.current,
          languageCode,
          trace: (kind, detail) => trace(kind, detail),
        });
      }
      ttsClientRef.current.syncCallId(callIdRef.current);
      const playback = playbackRef.current;
      const ttsClient = ttsClientRef.current;

      const pipeline = new TurnTtsPipeline({
        turnId,
        turnGen,
        isTurnActive: () => turnGen === turnGenRef.current,
        sessionId: sessionId || "default",
        callId: callIdRef.current,
        languageCode,
        playback,
        ttsClient,
        trace: (kind, detail) => trace(kind, detail),
        onSpeakingStart: () => {
          if (turnGen !== turnGenRef.current) return;
          setSessionStatus("speaking");
          bargeRef.current.agentSpeaking = true;
        },
        onSpeakingEnd: () => {
          if (turnGen !== turnGenRef.current) return;
          bargeRef.current.agentSpeaking = false;
        },
      });
      activePipelineRef.current = pipeline;

      try {
        await pipeline.start();
      } catch (e) {
        if (!abort.signal.aborted && turnGen === turnGenRef.current) {
          trace("tts:error", e instanceof Error ? e.message : "TTS start failed");
        }
      }

      const r = await fetch(`/api/brain/stream${qs}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        signal: abort.signal,
        body: JSON.stringify({
          transcript: text,
          language_code: languageCode,
          sessionId: sessionId || "default",
          callId: callIdRef.current,
        }),
      });

      let out = "";
      if (!r.ok || !r.body) {
        const errBody = await r.text().catch(() => "");
        trace("brain", `failed ${r.status} ${errBody.slice(0, 120)}`);
        pipeline.cancel();
        addBubble("assistant", "Sorry — the agent could not respond. Check the diagnostics panel.");
        bargeRef.current.brainStreaming = false;
        bargeRef.current.busy = false;
        setSessionStatus(listeningRef.current ? "listening" : "idle");
        return;
      }

      let assistantStarted = false;
      let streamUsage: TurnCompleteEvent["usage"];
      let memoryUpdate: TurnCompleteEvent["memoryUpdate"];

      try {
        for await (const payload of parseSseDataLines(r.body)) {
          if (turnGen !== turnGenRef.current) break;
          let ev: Record<string, unknown>;
          try {
            ev = JSON.parse(payload) as Record<string, unknown>;
          } catch {
            continue;
          }
          if (ev.delta) {
            out += String(ev.delta);
            if (!assistantStarted) {
              assistantStarted = true;
              setBubbles((prev) => [...prev, { role: "assistant", text: out, ts: Date.now() }]);
            } else {
              const chunk = out;
              setBubbles((prev) => {
                const idx = prev.map((b, i) => (b.role === "assistant" ? i : -1)).filter((i) => i >= 0).pop();
                if (idx == null) return prev;
                return prev.map((b, i) => (i === idx ? { ...b, text: chunk } : b));
              });
            }
            pipeline.onLlmDelta(String(ev.delta));
          }
          if (ev.done && ev.text) {
            out = String(ev.text);
            streamUsage = ev.usage as TurnCompleteEvent["usage"];
            memoryUpdate = ev.memory_update as TurnCompleteEvent["memoryUpdate"];
          } else if (ev.text && !ev.delta) {
            out = String(ev.text);
          }
        }
      } catch (e) {
        if (abort.signal.aborted || turnGen !== turnGenRef.current) {
          pipeline.cancel();
          trace("brain", "stream aborted");
          return;
        }
        trace("brain", `stream read error ${e instanceof Error ? e.message : "unknown"}`);
      }

      if (turnGen !== turnGenRef.current) {
        pipeline.cancel();
        trace("brain", "stale turn discarded");
        return;
      }

      bargeRef.current.brainStreaming = false;
      trace("brain", `stream done ${out.length} chars`);

      if (out) {
        lastAssistantTextRef.current = out;
        turnCounterRef.current += 1;
        const cached = Number(streamUsage?.cached_tokens || 0);
        trace(
          "tokens",
          `in=${streamUsage?.input_tokens ?? 0} out=${streamUsage?.output_tokens ?? 0} cached=${cached}`
        );
        onTurnCompleteRef.current?.({
          turn: turnCounterRef.current,
          userText: text,
          assistantText: out,
          at: Date.now(),
          usage: streamUsage,
          memoryUpdate,
        });
        if (!assistantStarted) {
          addBubble("assistant", out);
        } else {
          setBubbles((prev) => {
            const idx = prev.map((b, i) => (b.role === "assistant" ? i : -1)).filter((i) => i >= 0).pop();
            if (idx == null) return [...prev, { role: "assistant", text: out, ts: Date.now() }];
            return prev.map((b, i) => (i === idx ? { ...b, text: out } : b));
          });
        }

        try {
          if (turnGen === turnGenRef.current) {
            await pipeline.finishLlm();
          }
        } catch (e) {
          if (!abort.signal.aborted && turnGen === turnGenRef.current) {
            trace("tts:error", e instanceof Error ? e.message : "unknown");
          }
        }
        if (turnGen === turnGenRef.current) {
          speakCooldownUntilRef.current = Date.now() + POST_SPEAK_COOLDOWN_MS;
        }
      } else if (!assistantStarted) {
        addBubble("assistant", "Sorry — I did not get a response from the brain.");
      }

      if (turnGen === turnGenRef.current) {
        activePipelineRef.current = null;
        bargeRef.current.busy = false;
        while (pendingFinalsRef.current.length) {
          const next = pendingFinalsRef.current.shift()!;
          if (isLikelyEcho(next, lastAssistantTextRef.current)) {
            trace("stt", "dropped queued echo");
            continue;
          }
          runBrainTurnRef.current(next);
          return;
        }
        setSessionStatus(listeningRef.current ? "listening" : "idle");
      }
    },
    [addBubble, trace, setSessionStatus, languageCode, sessionId]
  );

  runBrainTurnRef.current = runBrainTurn;

  const handleSttFinal = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || wordCount(trimmed) < 1) return;
      const st = bargeRef.current;
      const now = Date.now();

      if (awaitingBargeRef.current) {
        awaitingBargeRef.current = false;
        pendingFinalsRef.current = [];
        st.busy = false;
        st.brainStreaming = false;
        runBrainTurnRef.current(trimmed);
        return;
      }

      if (st.agentSpeaking) {
        trace("stt", "ignored final during agent speech");
        return;
      }

      if (now < speakCooldownUntilRef.current && isLikelyEcho(trimmed, lastAssistantTextRef.current)) {
        trace("stt", "ignored echo during cooldown");
        return;
      }

      if (st.busy || st.brainStreaming) {
        pendingFinalsRef.current.push(trimmed);
        trace("stt", `queued final (${pendingFinalsRef.current.length})`);
        return;
      }

      runBrainTurnRef.current(trimmed);
    },
    [trace]
  );

  const teardownMic = useCallback(() => {
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
  }, [stopMicMeter]);

  const cleanupLive = useCallback(() => {
    teardownMic();
    setSessionStatus("idle");
  }, [setSessionStatus, teardownMic]);

  useEffect(() => {
    const cleanup = cleanupLive;
    return () => {
      cleanup();
    };
    // Unmount only — do not tie to cleanupLive identity
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pauseListening = useCallback(() => {
    intentionalStopRef.current = true;
    try {
      socketRef.current?.send(JSON.stringify({ event: "end" }));
    } catch {
      /* ignore */
    }
    teardownMic();
    setSessionStatus(callIdRef.current ? "paused" : "idle");
  }, [setSessionStatus, teardownMic]);

  const stopListening = useCallback(async () => {
    intentionalStopRef.current = true;
    pauseListening();
    await endCall();
    setSessionStatus("ended");
  }, [pauseListening, endCall, setSessionStatus]);

  const attachSttSocket = useCallback(() => {
    const q = new URLSearchParams({
      language_code: languageCode,
      stream_type: "fast",
      mode: "transcribe",
    });
    if (callIdRef.current) q.set("call_id", callIdRef.current);
    if (sessionId) q.set("sessionId", sessionId);

    const prev = socketRef.current;
    if (prev) {
      prev.onclose = null;
      try {
        if (prev.readyState === WebSocket.OPEN) prev.close(1000);
      } catch {
        /* ignore */
      }
    }

    const sock = new WebSocket(`${wsUrl("/ws/stt-realtime")}?${q}`);
    socketRef.current = sock;
    sock.binaryType = "arraybuffer";
    sock.onopen = () => {
      listeningRef.current = true;
      setListening(true);
      setSessionStatus("listening");
      trace("stt", `websocket open call=${callIdRef.current || "none"}`);
    };
    sock.onmessage = (ev) => {
      const { event, text, fatal, message } = parseSttPayload(String(ev.data));
      if (!event && !text) return;

      if (event === "session.begin") {
        setPartial("…speak now — live transcript appears here…");
        trace("stt", "session begin");
        return;
      }
      if (event === "partial" || event === "transcript.partial") {
        if (text) {
          setPartial(text);
          trace("stt", `partial ${text.slice(0, 48)}`);
        }
        return;
      }
      if (event === "speech_start" || event === "vad.speech_start") {
        bargeRef.current.sawVadStart = true;
        trace("vad", "speech start");
        if (bargeRef.current.agentSpeaking || bargeRef.current.brainStreaming) {
          doBargeIn("vad-start");
        }
        return;
      }
      if (event === "final" || event === "transcript.final" || event === "transcript") {
        if (!text) return;
        setPartial("");
        trace("stt", `final ${text.slice(0, 80)}`);
        handleSttFinal(text);
        return;
      }
      if (event === "error" || fatal) {
        trace("stt", `error ${message || event}`);
        if (fatal) setSessionStatus(`STT error: ${message || "fatal"}`);
      }
    };
    sock.onclose = () => {
      trace("stt", "websocket closed");
      if (intentionalStopRef.current || !listeningRef.current) return;
      trace("stt", "reconnecting…");
      window.setTimeout(() => {
        if (listeningRef.current && !intentionalStopRef.current && streamRef.current) {
          attachSttSocket();
        }
      }, 500);
    };
  }, [languageCode, sessionId, handleSttFinal, doBargeIn, setSessionStatus, trace]);

  const startListening = useCallback(async () => {
    if (listeningRef.current || startingRef.current) return;
    startingRef.current = true;
    intentionalStopRef.current = false;
    playbackRef.current?.userGesture();
    setSessionStatus("connecting");
    try {
      if (!callIdRef.current) {
        await startCall();
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
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
        const buf = ev.data instanceof ArrayBuffer ? ev.data : (ev.data as Int16Array).buffer;
        sock.send(buf);
        const st = bargeRef.current;
        st.words = wordCount(partialRef.current);
        if (shouldBargeWhileSpeaking(st, Date.now())) {
          doBargeIn("vad+partial");
        }
      };
      src.connect(worklet);
      attachSttSocket();
    } catch (e) {
      const msg =
        e instanceof DOMException && e.name === "AbortError"
          ? "Microphone setup was interrupted"
          : e instanceof Error
            ? e.message
            : "Mic error";
      setSessionStatus(msg);
      trace("stt", `mic setup failed: ${msg}`);
      teardownMic();
      if (!callIdRef.current) {
        await endCall();
      } else {
        setSessionStatus("paused");
      }
    } finally {
      startingRef.current = false;
    }
  }, [attachSttSocket, teardownMic, endCall, doBargeIn, startCall, startMicMeter, trace, setSessionStatus]);

  useImperativeHandle(ref, () => ({
    startListening,
    pauseListening,
    stopListening,
    endCall: async () => {
      pauseListening();
      await endCall();
      setSessionStatus("ended");
    },
  }));

  const isLab = variant === "lab";
  const isDev = variant === "dev";

  return (
    <div>
      {!isDev && !isLab && (
        <div className="flex items-center justify-between">
          <h2 className="font-medium text-text">Live voice session</h2>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-surface-border px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-text-muted">
            {status === "listening" && <span className="h-1.5 w-1.5 rounded-full bg-agent-online animate-pulse-dot" />}
            {status}
          </span>
        </div>
      )}
      {!isLab && (
        <div className={`flex flex-wrap gap-2 ${isDev ? "" : "mt-4"}`}>
          {!listening ? (
            <SkeuoButton variant="primary" onClick={startListening}>Start listening</SkeuoButton>
          ) : (
            <SkeuoButton variant="secondary" onClick={stopListening} className="border-status-error/40 text-status-error">
              Stop listening
            </SkeuoButton>
          )}
          <SkeuoButton variant="ghost" onClick={endCall}>End call</SkeuoButton>
        </div>
      )}

      {!isLab && (
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
      )}

      <audio
        ref={audioRef}
        className={isLab ? "sr-only" : `w-full ${isDev ? "mt-3" : "mt-4"}`}
        controls={!isLab}
        aria-label="Agent audio playback"
      />
      {!isDev && !isLab && (
        <p className="mt-2 text-xs text-text-muted">
          WS STT · WS TTS stream · pcm-worklet · live-guards barge-in · SSE brain
        </p>
      )}
    </div>
  );
});
