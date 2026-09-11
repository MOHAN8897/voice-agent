"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { parseSseDataLines, wordCount } from "@/lib/early-tts";
import { StreamingAudioPlayback } from "@/lib/voice/streaming-audio-playback";
import { BackchannelController, type BackchannelLang } from "@/lib/voice/backchannel-controller";
import { StreamingTtsClient } from "@/lib/voice/streaming-tts-client";
import { TurnTtsPipeline } from "@/lib/voice/turn-tts-pipeline";
import { isLikelyEcho, isLikelyEchoPartial } from "@/lib/echo-guard";
import { shouldBargeWhileSpeaking, shouldThinkCancel, type BargeState } from "@/lib/live-guards";
import {
  micGateConfig,
  pcmRms16,
  rmsAllowsSpeakBarge,
  shouldAllowBargeIn,
  shouldSendMicToStt,
} from "@/lib/voice/mic-gate";
import { isMobileLikeDevice, mobileModeFromPreset, profileSummary, resolveVoiceAudioProfile, type VoiceAudioProfile } from "@/lib/voice/mobile-audio";
import { isSubstantiveTranscript, looksIncompleteReply } from "@/lib/voice/transcript-gate";
import { detectHeadphones, headphonesFromStream } from "@/lib/voice/headphone-detect";
import { warmupBrowserAec } from "@/lib/voice/aec-warmup";
import { apiOrigin, wsUrl } from "@/lib/api";
import { billingCharCount } from "@/lib/billing-chars";

function isAbortError(e: unknown): boolean {
  return (
    (e instanceof DOMException && e.name === "AbortError") ||
    (e instanceof Error && e.name === "AbortError")
  );
}

export type Bubble = { role: "user" | "assistant"; text: string; interrupted?: boolean; ts?: number };

export type SessionTraceEvent = { at: number; kind: string; detail: string };

export type TurnCompleteEvent = {
  turn: number;
  userText: string;
  assistantText: string;
  at: number;
  /** Mic on (speech start) until turn complete */
  micDurationMs?: number;
  usage?: {
    input_tokens?: number;
    output_tokens?: number;
    cached_tokens?: number;
    cache_write_tokens?: number;
    /** STT: transcript character count (billing proxy) */
    stt_chars?: number;
    /** STT: billed audio seconds (speech start → final, or provider audio_duration_s) */
    stt_audio_sec?: number;
    /** TTS: synthesized character count */
    tts_chars?: number;
    /** TTS: PCM audio bytes received */
    tts_audio_bytes?: number;
  };
  memoryUpdate?: { operations?: unknown[] };
};

export type LiveVoiceSessionHandle = {
  startListening: () => void;
  pauseListening: () => void;
  stopListening: () => void;
  endCall: () => void;
};

function nestedSttText(data: unknown): string {
  if (typeof data === "string") return data;
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    if (typeof d.text === "string") return d.text;
    if (typeof d.transcript === "string") return d.transcript;
  }
  return "";
}

function parseSttPayload(raw: string): {
  event: string;
  text: string;
  fatal: boolean;
  message: string;
  audioDurationSec?: number;
} {
  try {
    const m = JSON.parse(raw) as Record<string, unknown>;
    const event = String(m.event || m.type || "");
    const rootText = typeof m.text === "string" ? m.text : "";
    const transcript = typeof m.transcript === "string" ? m.transcript : "";
    const text = (rootText || nestedSttText(m.data) || transcript).trim();
    const nested = m.data && typeof m.data === "object" ? (m.data as Record<string, unknown>) : {};
    const durationRaw = m.audio_duration_s ?? m.audio_duration ?? nested.audio_duration_s ?? nested.audio_duration;
    const audioDurationSec = typeof durationRaw === "number" ? durationRaw : Number(durationRaw);
    return {
      event,
      text,
      fatal: Boolean(m.is_fatal),
      message: String(m.message || m.code || ""),
      audioDurationSec: Number.isFinite(audioDurationSec) && audioDurationSec > 0 ? audioDurationSec : undefined,
    };
  } catch {
    return { event: "", text: "", fatal: false, message: "" };
  }
}

export type VoiceRuntimeConfig = {
  sttSilenceMs?: number;
  sttThreshold?: number;
  sttStreamType?: string;
  bargeMinWords?: number;
  bargeRequireVad?: boolean;
  voicePresetId?: string;
  mobileAudioMode?: "handset" | "speakerphone";
};

export const LiveVoiceSession = forwardRef<LiveVoiceSessionHandle, {
  agentId?: string;
  tier?: string;
  languageCode?: string;
  stackOverride?: Record<string, unknown>;
  sessionId?: string;
  voiceConfig?: VoiceRuntimeConfig;
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
  voiceConfig,
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
  const backchannelRef = useRef(new BackchannelController());
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
    vadStartedAt: 0,
    bargeCooldownUntil: 0,
    turnN: 0,
  });
  const brainAbortRef = useRef<AbortController | null>(null);
  const pendingFinalsRef = useRef<string[]>([]);
  const pendingDuringSpeechRef = useRef<string[]>([]);
  const sttPcmBufferRef = useRef<ArrayBuffer[]>([]);
  const STT_PCM_BUFFER_MAX = 32;
  const awaitingBargeRef = useRef(false);
  const pendingAgentHangupRef = useRef(false);
  const speakCooldownUntilRef = useRef(0);
  const lastAssistantTextRef = useRef("");
  const lastAcceptedFinalRef = useRef<{ text: string; at: number }>({ text: "", at: 0 });
  const turnGenRef = useRef(0);
  const lastSpeechStartAtRef = useRef<number | null>(null);
  const lastSttAudioSecRef = useRef<number>(0);
  const speakStartedAtRef = useRef(0);
  const thinkingSinceRef = useRef(0);
  const lastMicRmsRef = useRef(0);
  const audioProfileRef = useRef<VoiceAudioProfile>(resolveVoiceAudioProfile());
  const gateConfigRef = useRef(micGateConfig(audioProfileRef.current));
  const voiceConfigRef = useRef(voiceConfig);
  voiceConfigRef.current = voiceConfig;

  const assistantEchoText = useCallback((): string => {
    const live = activePipelineRef.current?.getFullText()?.trim();
    if (live) return live;
    return lastAssistantTextRef.current;
  }, []);

  const effectiveVoiceConfig = useCallback(() => {
    const cfg = voiceConfigRef.current || {};
    const profile = audioProfileRef.current;
    return {
      ...cfg,
      sttSilenceMs: cfg.sttSilenceMs ?? profile.defaultSttSilenceMs,
      sttThreshold: cfg.sttThreshold ?? profile.defaultSttThreshold,
      bargeMinWords: (cfg.bargeMinWords ?? 3) + profile.bargeMinWordsBonus,
      bargeRequireVad:
        profile.ignoreVadDuringAgentSpeech && cfg.bargeRequireVad === undefined
          ? false
          : cfg.bargeRequireVad ?? true,
      bargeHoldMs: profile.bargeHoldMs,
      thinkCancelMinWords: profile.thinkCancelMinWords,
    };
  }, []);

  const trace = useCallback(
    (kind: string, detail: string) => {
      onTrace?.({ at: Date.now(), kind, detail });
    },
    [onTrace]
  );

  const applyAudioProfile = useCallback(
    (headphones: boolean) => {
      const cfg = voiceConfigRef.current || {};
      const mobileMode =
        cfg.mobileAudioMode ?? mobileModeFromPreset(cfg.voicePresetId);
      audioProfileRef.current = resolveVoiceAudioProfile({
        headphones,
        mobileMode: isMobileLikeDevice() ? mobileMode : undefined,
      });
      gateConfigRef.current = micGateConfig(audioProfileRef.current);
      trace("stt", `audio profile: ${profileSummary(audioProfileRef.current)}`);
    },
    [trace]
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
      ttsClientRef.current?.dispose();
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
    const rt = j.realtime as { status?: string; error?: string } | undefined;
    if (rt?.status === "failed") {
      trace("call", `realtime boot failed: ${rt.error || "unknown"}`);
      throw new Error(rt.error || "Realtime session failed to start");
    }
    if (!ttsClientRef.current) {
      ttsClientRef.current = new StreamingTtsClient({
        sessionId: sessionId || "default",
        callId: j.call_id as string,
        languageCode,
        trace: (kind, detail) => trace(kind, detail),
      });
    } else {
      ttsClientRef.current.syncCallId(j.call_id as string);
    }
    try {
      await ttsClientRef.current.preconnect();
      trace("tts", "preconnected at call start");
    } catch (e) {
      trace("tts", `preconnect failed: ${e instanceof Error ? e.message : "unknown"}`);
    }
    trace("call", `started ${j.call_id} realtime=${rt?.status || "n/a"}`);
    onCallStart?.(j.call_id);
    return j.call_id as string;
  }, [agentId, tier, languageCode, sessionId, stackOverride, trace, onCallStart]);

  const endCall = useCallback(async (reason = "user_stop") => {
    if (!callIdRef.current) return;
    const id = callIdRef.current;
    pendingAgentHangupRef.current = false;
    await fetch("/api/call/end", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ callId: id, reason }),
    });
    trace("call", `ended ${id} ${reason}`);
    onCallEnd?.(id);
    callIdRef.current = null;
    setSessionStatus("ended");
  }, [trace, onCallEnd]);

  const runBrainTurnRef = useRef<(text: string) => void>(() => {});

  const flushPendingDuringSpeech = useCallback(() => {
    const queued = pendingDuringSpeechRef.current;
    if (!queued.length) return;
    pendingDuringSpeechRef.current = [];
    for (const next of queued) {
      if (!isSubstantiveTranscript(next, { fromSpeechQueue: true })) {
        trace("stt", `dropped thin fragment after speech: ${next.slice(0, 48)}`);
        continue;
      }
      if (isLikelyEcho(next, assistantEchoText())) {
        trace("stt", "dropped queued echo (during speech)");
        continue;
      }
      const st = bargeRef.current;
      if (st.busy || st.brainStreaming) {
        pendingFinalsRef.current.push(next);
        trace("stt", `re-queued after speech (${pendingFinalsRef.current.length})`);
        continue;
      }
      runBrainTurnRef.current(next);
      return;
    }
  }, [trace, assistantEchoText]);

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
      pendingAgentHangupRef.current = false;
      pendingFinalsRef.current = [];
      pendingDuringSpeechRef.current = [];
      turnGenRef.current += 1;

      brainAbortRef.current?.abort();
      brainAbortRef.current = null;
      const heardText = activePipelineRef.current?.getFullText() || lastAssistantTextRef.current;
      activePipelineRef.current?.cancel();
      activePipelineRef.current = null;
      playbackRef.current?.stop();
      markLastAssistantInterrupted();
      trace("vad", `barge-in ${reason}`);

      fetch(`${apiOrigin()}/api/session/interrupt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          sessionId: sessionId || "default",
          callId: callIdRef.current,
          heardText,
        }),
      }).catch(() => {});
      setSessionStatus(listeningRef.current ? "listening" : "idle");
    },
    [markLastAssistantInterrupted, sessionId, setSessionStatus, trace]
  );

  const runBrainTurn = useCallback(
    async (text: string, retryCount = 0) => {
      const qs = callIdRef.current ? `?callId=${encodeURIComponent(callIdRef.current)}` : "";
      const turnGen = ++turnGenRef.current;
      brainAbortRef.current?.abort();
      const abort = new AbortController();
      brainAbortRef.current = abort;

      bargeRef.current.turnN += 1;
      bargeRef.current.brainStreaming = true;
      bargeRef.current.busy = true;
      bargeRef.current.sawVadStart = false;
      bargeRef.current.vadStartedAt = 0;
      thinkingSinceRef.current = Date.now();
      awaitingBargeRef.current = false;
      pendingAgentHangupRef.current = false;
      setSessionStatus("thinking");
      trace("brain", "stream start");
      // Retries must not duplicate the user row (STT already showed the utterance once).
      if (retryCount === 0) {
        addBubble("user", text);
      }

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
          const now = Date.now();
          const gate = gateConfigRef.current;
          setSessionStatus("speaking");
          bargeRef.current.agentSpeaking = true;
          speakStartedAtRef.current = now;
          bargeRef.current.bargeCooldownUntil = now + gate.bargeMinAfterSpeakMs;
          const spoken = pipeline.getFullText().trim();
          if (spoken) lastAssistantTextRef.current = spoken;
        },
        onSpeakingEnd: () => {
          if (turnGen !== turnGenRef.current) return;
          bargeRef.current.agentSpeaking = false;
          speakStartedAtRef.current = 0;
          speakCooldownUntilRef.current = Date.now() + gateConfigRef.current.playbackTailMs;
          flushPendingDuringSpeech();
        },
      });
      activePipelineRef.current = pipeline;

      let r: Response;
      try {
        const [, response] = await Promise.all([
          pipeline.start(),
          fetch(`/api/brain/stream${qs}`, {
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
          }),
        ]);
        r = response;
      } catch (e) {
        if (abort.signal.aborted || turnGen !== turnGenRef.current || isAbortError(e)) {
          pipeline.cancel();
          trace("brain", "stream aborted");
          return;
        }
        pipeline.cancel();
        const msg = e instanceof Error ? e.message : "unknown";
        trace("brain", `turn setup error ${msg}`);
        addBubble(
          "assistant",
          msg.toLowerCase().includes("tts")
            ? "Sorry — voice playback failed to connect. Please try again."
            : "Sorry — the agent could not respond. Check the diagnostics panel."
        );
        bargeRef.current.brainStreaming = false;
        bargeRef.current.busy = false;
        activePipelineRef.current = null;
        setSessionStatus(listeningRef.current ? "listening" : "idle");
        return;
      }

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
      let brainFailed = false;
      let brainCancelled = false;

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
            const streamed = pipeline.getFullText().trim();
            if (streamed) lastAssistantTextRef.current = streamed;
          }
          if (ev.done) {
            // Always prefer final text — including "" after crumb/cancel cleanup.
            if ("text" in ev) out = String(ev.text ?? "");
            brainFailed = Boolean(ev.failed);
            brainCancelled = Boolean(ev.cancelled);
            streamUsage = ev.usage as TurnCompleteEvent["usage"];
            memoryUpdate = ev.memory_update as TurnCompleteEvent["memoryUpdate"];
            const endCallEv = ev.end_call as { should_end?: boolean } | undefined;
            pendingAgentHangupRef.current = Boolean(endCallEv?.should_end);
          } else if (ev.text && !ev.delta) {
            out = String(ev.text);
          }
        }
      } catch (e) {
        if (abort.signal.aborted || turnGen !== turnGenRef.current || isAbortError(e)) {
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

      if (
        !out &&
        !brainCancelled &&
        !abort.signal.aborted &&
        turnGen === turnGenRef.current &&
        retryCount < 1
      ) {
        trace("brain", "empty reply — retrying once");
        if (assistantStarted) {
          setBubbles((prev) => {
            const idx = prev.map((b, i) => (b.role === "assistant" ? i : -1)).filter((i) => i >= 0).pop();
            if (idx == null) return prev;
            return prev.filter((_, i) => i !== idx);
          });
        }
        bargeRef.current.brainStreaming = false;
        bargeRef.current.busy = false;
        activePipelineRef.current = null;
        await new Promise((r) => setTimeout(r, 450));
        if (turnGen === turnGenRef.current) {
          return runBrainTurn(text, retryCount + 1);
        }
        return;
      }

      if (
        out &&
        looksIncompleteReply(out) &&
        !brainCancelled &&
        retryCount < 1 &&
        turnGen === turnGenRef.current
      ) {
        trace("brain", `incomplete reply (${out.length}c) — retrying once`);
        if (assistantStarted) {
          setBubbles((prev) => {
            const idx = prev.map((b, i) => (b.role === "assistant" ? i : -1)).filter((i) => i >= 0).pop();
            if (idx == null) return prev;
            return prev.filter((_, i) => i !== idx);
          });
        }
        bargeRef.current.brainStreaming = false;
        bargeRef.current.busy = false;
        activePipelineRef.current = null;
        await new Promise((r) => setTimeout(r, 300));
        if (turnGen === turnGenRef.current) {
          return runBrainTurn(text, retryCount + 1);
        }
        return;
      }

      if (out) {
        lastAssistantTextRef.current = out;
        turnCounterRef.current += 1;
        const ttsMetrics = pipeline.getMetrics();
        const micStart = lastSpeechStartAtRef.current;
        const micDurationMs = micStart ? Math.max(0, Date.now() - micStart) : undefined;
        lastSpeechStartAtRef.current = null;
        const sttAudioSec =
          lastSttAudioSecRef.current > 0
            ? lastSttAudioSecRef.current
            : micDurationMs
              ? Math.round((micDurationMs / 1000) * 10) / 10
              : 0;
        lastSttAudioSecRef.current = 0;
        const mergedUsage = {
          ...streamUsage,
          stt_chars: billingCharCount(text),
          stt_audio_sec: sttAudioSec,
          tts_chars: ttsMetrics.ttsChars || billingCharCount(out),
          tts_audio_bytes: ttsMetrics.ttsAudioBytes,
        };
        trace(
          "tokens",
          `stt=${mergedUsage.stt_chars}c llm in=${mergedUsage.input_tokens ?? 0} out=${mergedUsage.output_tokens ?? 0} tts=${mergedUsage.tts_chars}c`
        );
        onTurnCompleteRef.current?.({
          turn: turnCounterRef.current,
          userText: text,
          assistantText: out,
          at: Date.now(),
          micDurationMs,
          usage: mergedUsage,
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
            const msg = e instanceof Error ? e.message : "TTS failed";
            trace("tts:error", msg);
            addBubble("assistant", "Sorry — I could not play the response. Please try again.");
          }
        }
        if (
          turnGen === turnGenRef.current &&
          pendingAgentHangupRef.current &&
          !awaitingBargeRef.current
        ) {
          pendingAgentHangupRef.current = false;
          await endCall("agent_hangup");
          return;
        }
        if (turnGen === turnGenRef.current) {
          speakCooldownUntilRef.current = Date.now() + gateConfigRef.current.playbackTailMs;
        }
      } else if (
        !assistantStarted &&
        turnGen === turnGenRef.current &&
        !abort.signal.aborted &&
        !brainCancelled
      ) {
        addBubble(
          "assistant",
          brainFailed
            ? "Sorry — I lost that turn. Please say that again."
            : "Sorry — I did not get a response. Please try again."
        );
      } else if (assistantStarted && !out && turnGen === turnGenRef.current) {
        // Drop streamed crumb that was cleared on done (cancel / incomplete).
        setBubbles((prev) => {
          const idx = prev.map((b, i) => (b.role === "assistant" ? i : -1)).filter((i) => i >= 0).pop();
          if (idx == null) return prev;
          return prev.filter((_, i) => i !== idx);
        });
        trace("brain", "cleared empty/cancelled assistant crumb");
      } else if (!assistantStarted) {
        trace("brain", "empty response skipped (interrupted, cancelled, or stale turn)");
      }

      if (turnGen === turnGenRef.current) {
        activePipelineRef.current = null;
        bargeRef.current.busy = false;
        while (pendingFinalsRef.current.length) {
          const next = pendingFinalsRef.current.shift()!;
          if (isLikelyEcho(next, assistantEchoText())) {
            trace("stt", "dropped queued echo");
            continue;
          }
          lastAcceptedFinalRef.current = {
            text: next.toLowerCase().replace(/\s+/g, " "),
            at: Date.now(),
          };
          runBrainTurnRef.current(next);
          return;
        }
        setSessionStatus(listeningRef.current ? "listening" : "idle");
      }
    },
    [addBubble, trace, setSessionStatus, languageCode, sessionId, endCall, flushPendingDuringSpeech]
  );

  runBrainTurnRef.current = (text: string) => {
    void runBrainTurn(text).catch((e) => {
      if (isAbortError(e)) return;
      trace("brain", `turn error ${e instanceof Error ? e.message : "unknown"}`);
    });
  };

  const handleSttFinal = useCallback(
    (text: string, opts?: { afterBarge?: boolean; fromSpeechQueue?: boolean }) => {
      const trimmed = text.trim();
      if (!trimmed || wordCount(trimmed) < 1) return;
      if (!isSubstantiveTranscript(trimmed, opts)) {
        trace("stt", `ignored thin final: ${trimmed.slice(0, 48)}`);
        return;
      }
      const st = bargeRef.current;
      const now = Date.now();
      const norm = trimmed.toLowerCase().replace(/\s+/g, " ");
      const lastFinal = lastAcceptedFinalRef.current;
      if (norm === lastFinal.text && now - lastFinal.at < 2200) {
        trace("stt", "deduped identical final");
        return;
      }

      if (awaitingBargeRef.current) {
        awaitingBargeRef.current = false;
        pendingFinalsRef.current = [];
        pendingDuringSpeechRef.current = [];
        st.busy = false;
        st.brainStreaming = false;
        if (!isSubstantiveTranscript(trimmed, { afterBarge: true })) {
          trace("stt", `ignored thin barge final: ${trimmed.slice(0, 48)}`);
          return;
        }
        lastAcceptedFinalRef.current = { text: norm, at: now };
        runBrainTurnRef.current(trimmed);
        return;
      }

      if (st.agentSpeaking) {
        if (isLikelyEcho(trimmed, assistantEchoText())) {
          trace("stt", "ignored echo final during agent speech");
          return;
        }
        const queued = pendingDuringSpeechRef.current;
        if (queued.length && queued[queued.length - 1].toLowerCase().replace(/\s+/g, " ") === norm) {
          trace("stt", "deduped queued final during agent speech");
          return;
        }
        pendingDuringSpeechRef.current.push(trimmed);
        trace("stt", `queued final during agent speech (${pendingDuringSpeechRef.current.length})`);
        return;
      }

      if (now < speakCooldownUntilRef.current && isLikelyEcho(trimmed, assistantEchoText())) {
        trace("stt", "ignored echo during cooldown");
        return;
      }

      if (st.busy || st.brainStreaming) {
        if (isLikelyEcho(trimmed, assistantEchoText())) {
          trace("stt", "dropped queued echo");
          return;
        }
        const queued = pendingFinalsRef.current;
        if (queued.length && queued[queued.length - 1].toLowerCase().replace(/\s+/g, " ") === norm) {
          trace("stt", "deduped queued final");
          return;
        }
        pendingFinalsRef.current.push(trimmed);
        trace("stt", `queued final (${pendingFinalsRef.current.length})`);
        return;
      }

      lastAcceptedFinalRef.current = { text: norm, at: now };
      runBrainTurnRef.current(trimmed);
    },
    [trace, assistantEchoText]
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
    stopMicMeter();
    setListening(false);
    setPartial("");
  }, [stopMicMeter]);

  const releaseAudioContext = useCallback(() => {
    playbackRef.current?.setSharedContext(null);
    const ctx = ctxRef.current;
    ctxRef.current = null;
    if (ctx && ctx.state !== "closed") {
      ctx.close().catch(() => {});
    }
  }, []);

  const cleanupLive = useCallback(() => {
    teardownMic();
    playbackRef.current?.stop();
    releaseAudioContext();
    setSessionStatus("idle");
  }, [setSessionStatus, teardownMic, releaseAudioContext]);

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
    playbackRef.current?.stop();
    releaseAudioContext();
    await endCall();
    setSessionStatus("ended");
  }, [pauseListening, endCall, setSessionStatus, releaseAudioContext]);

  const attachSttSocket = useCallback(() => {
    const cfg = effectiveVoiceConfig();
    const q = new URLSearchParams({
      language_code: languageCode,
      stream_type: cfg.sttStreamType || "fast",
      mode: "transcribe",
      sample_rate: "16000",
    });
    if (cfg.sttSilenceMs) q.set("silence_duration_ms", String(cfg.sttSilenceMs));
    if (cfg.sttThreshold != null) q.set("threshold", String(cfg.sttThreshold));
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
      const buffered = sttPcmBufferRef.current.splice(0);
      for (const buf of buffered) {
        try {
          sock.send(buf);
        } catch {
          /* ignore */
        }
      }
      if (buffered.length) {
        trace("stt", `flushed ${buffered.length} buffered pcm chunks`);
      }
    };
    sock.onmessage = (ev) => {
      const { event, text, fatal, message, audioDurationSec } = parseSttPayload(String(ev.data));
      if (!event && !text) return;

      if (event === "session.begin") {
        setPartial("…speak now — live transcript appears here…");
        trace("stt", "session begin");
        return;
      }
      if (event === "partial" || event === "transcript.partial") {
        if (text) {
          const st = bargeRef.current;
          const now = Date.now();
          const echoText = assistantEchoText();
          if (st.agentSpeaking && !awaitingBargeRef.current) {
            if (isLikelyEchoPartial(text, echoText)) {
              trace("stt", "ignored partial echo");
              return;
            }
          }
          if (!st.agentSpeaking) {
            setPartial(text);
          }
          trace("stt", `partial ${text.slice(0, 48)}`);
          backchannelRef.current.onPartial(text, {
            agentSpeaking: st.agentSpeaking,
            brainStreaming: st.brainStreaming,
            listening: listeningRef.current,
          }, languageCode as BackchannelLang);
          st.words = wordCount(text);
          st.elapsedMs = thinkingSinceRef.current > 0 ? now - thinkingSinceRef.current : 0;
          const gate = gateConfigRef.current;
          const gateState = {
            agentSpeaking: st.agentSpeaking,
            brainStreaming: st.brainStreaming,
            awaitingUserAfterBarge: awaitingBargeRef.current,
            speakCooldownUntil: speakCooldownUntilRef.current,
            speakStartedAt: speakStartedAtRef.current,
          };
          if (
            shouldAllowBargeIn(gateState, now, gate) &&
            (!st.agentSpeaking || rmsAllowsSpeakBarge(lastMicRmsRef.current, gate)) &&
            shouldBargeWhileSpeaking(
              {
                ...st,
                minWords: cfg.bargeMinWords,
                requireVad: cfg.bargeRequireVad,
                holdMs: cfg.bargeHoldMs,
              },
              now
            )
          ) {
            doBargeIn("vad+partial");
          } else if (
            shouldThinkCancel(
              {
                ...st,
                elapsedMs: st.elapsedMs,
              },
              cfg.thinkCancelMinWords
            )
          ) {
            doBargeIn("think-cancel");
          }
        }
        return;
      }
      if (event === "speech_start" || event === "vad.speech_start") {
        if (
          bargeRef.current.agentSpeaking &&
          audioProfileRef.current.ignoreVadDuringAgentSpeech &&
          !awaitingBargeRef.current
        ) {
          trace("vad", "ignored speech start during agent (mobile echo guard)");
          return;
        }
        bargeRef.current.sawVadStart = true;
        bargeRef.current.vadStartedAt = Date.now();
        lastSpeechStartAtRef.current = Date.now();
        trace("vad", "speech start");
        return;
      }
      if (event === "final" || event === "transcript.final" || event === "transcript") {
        if (!text) return;
        const started = lastSpeechStartAtRef.current;
        lastSttAudioSecRef.current =
          audioDurationSec ??
          (started ? Math.round(((Date.now() - started) / 1000) * 10) / 10 : lastSttAudioSecRef.current);
        setPartial("");
        backchannelRef.current.onFinal();
        trace("stt", `final ${text.slice(0, 80)}`);
        handleSttFinal(text, { fromSpeechQueue: false });
        return;
      }
      if (event === "session.end" && audioDurationSec) {
        lastSttAudioSecRef.current = audioDurationSec;
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
  }, [languageCode, sessionId, handleSttFinal, doBargeIn, setSessionStatus, trace, assistantEchoText, effectiveVoiceConfig]);

  const waitSttSocketOpen = useCallback((timeoutMs = 15000): Promise<void> => {
    const sock = socketRef.current;
    if (!sock) return Promise.reject(new Error("STT socket missing"));
    if (sock.readyState === WebSocket.OPEN) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const timer = window.setTimeout(() => reject(new Error("STT connection timeout")), timeoutMs);
      sock.addEventListener(
        "open",
        () => {
          clearTimeout(timer);
          resolve();
        },
        { once: true }
      );
      sock.addEventListener(
        "error",
        () => {
          clearTimeout(timer);
          reject(new Error("STT websocket error"));
        },
        { once: true }
      );
    });
  }, []);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      const ctx = ctxRef.current;
      if (ctx && ctx.state === "suspended") {
        ctx.resume().catch(() => {});
      }
      playbackRef.current?.userGesture();
      if (listeningRef.current) {
        const sock = socketRef.current;
        if (!sock || sock.readyState !== WebSocket.OPEN) {
          trace("stt", "reconnect after visibility resume");
          attachSttSocket();
        }
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [attachSttSocket]);

  const startListening = useCallback(async () => {
    if (listeningRef.current || startingRef.current) return;
    startingRef.current = true;
    intentionalStopRef.current = false;
    playbackRef.current?.userGesture();
    setSessionStatus("connecting");
    try {
      const sid = sessionId || "default";
      try {
        const instrRes = await fetch(`/api/instructions?sessionId=${encodeURIComponent(sid)}`, {
          credentials: "include",
        });
        if (instrRes.ok) {
          const instr = (await instrRes.json()) as Record<string, unknown>;
          const script = String(instr.agentScript || instr.brainPrompt || "").trim();
          if (!script) {
            setSessionStatus("Save agent brief first (Fine-tune tab)");
            trace("call", "blocked — no agent script saved");
            return;
          }
        }
      } catch {
        setSessionStatus("Could not verify agent brief — check connection");
        trace("call", "blocked — instructions check failed");
        return;
      }

      if (!callIdRef.current) {
        await startCall();
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: { ideal: 16000 },
        },
      });
      streamRef.current = stream;
      const headphones =
        headphonesFromStream(stream) || (await detectHeadphones());
      applyAudioProfile(headphones);

      let ctx = ctxRef.current;
      if (!ctx || ctx.state === "closed") {
        ctx = new AudioContext({ latencyHint: "interactive" });
        ctxRef.current = ctx;
      }
      playbackRef.current?.setSharedContext(ctx);
      if (ctx.state === "suspended") {
        await ctx.resume();
      }
      if (!headphones && audioProfileRef.current.mobileMode === "speakerphone") {
        try {
          await warmupBrowserAec(ctx);
          trace("stt", "AEC warmup played (mobile speakerphone)");
        } catch {
          /* non-fatal */
        }
      }
      trace("stt", `audio context ${ctx.sampleRate}Hz → stt 16000Hz state=${ctx.state}`);

      attachSttSocket();
      await waitSttSocketOpen();

      await ctx.audioWorklet.addModule("/pcm-worklet.js?v=16k-mix-2");
      const src = ctx.createMediaStreamSource(stream);
      startMicMeter(ctx, src);
      const worklet = new AudioWorkletNode(ctx, "pcm-processor", {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        channelCount: 1,
        channelCountMode: "explicit",
        channelInterpretation: "speakers",
      });
      workletRef.current = worklet;
      let pcmChunks = 0;
      let pcmPeak = 0;
      let silenceWarned = false;
      worklet.port.onmessage = (ev) => {
        const sock = socketRef.current;
        let samples: Int16Array;
        if (ev.data instanceof ArrayBuffer) {
          samples = new Int16Array(ev.data);
        } else if (ev.data instanceof Int16Array) {
          samples = ev.data;
        } else {
          return;
        }
        if (!samples.length) return;
        for (let i = 0; i < samples.length; i += 1) {
          const a = samples[i] < 0 ? -samples[i] : samples[i];
          if (a > pcmPeak) pcmPeak = a;
        }
        pcmChunks += 1;
        if (pcmChunks === 16 && !silenceWarned) {
          if (pcmPeak < 64) {
            silenceWarned = true;
            trace("stt", "mic audio is silent — check browser mic permission and input device");
            setPartial("Mic is silent — allow microphone access and pick the correct input");
          } else {
            trace("stt", `mic audio ok peak=${pcmPeak}`);
          }
        }

        const st = bargeRef.current;
        const now = Date.now();
        const rms = pcmRms16(samples);
        lastMicRmsRef.current = rms;
        const gate = gateConfigRef.current;
        const gateState = {
          agentSpeaking: st.agentSpeaking,
          brainStreaming: st.brainStreaming,
          awaitingUserAfterBarge: awaitingBargeRef.current,
          speakCooldownUntil: speakCooldownUntilRef.current,
          speakStartedAt: speakStartedAtRef.current,
        };
        if (!shouldSendMicToStt(gateState, now, rms, gate)) {
          return;
        }

        const pcmBuf = samples.buffer.slice(
          samples.byteOffset,
          samples.byteOffset + samples.byteLength
        ) as ArrayBuffer;
        if (!sock || sock.readyState !== WebSocket.OPEN) {
          const q = sttPcmBufferRef.current;
          if (q.length < STT_PCM_BUFFER_MAX) q.push(pcmBuf);
          return;
        }
        sock.send(pcmBuf);
        st.words = wordCount(partialRef.current);
      };
      src.connect(worklet);
      const silentGain = ctx.createGain();
      silentGain.gain.value = 0;
      worklet.connect(silentGain);
      silentGain.connect(ctx.destination);
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
  }, [attachSttSocket, waitSttSocketOpen, teardownMic, endCall, startCall, startMicMeter, trace, setSessionStatus, sessionId, applyAudioProfile]);

  useImperativeHandle(ref, () => ({
    startListening,
    pauseListening,
    stopListening,
    endCall: async () => {
      pauseListening();
      playbackRef.current?.stop();
      releaseAudioContext();
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
          <SkeuoButton variant="ghost" onClick={() => { void endCall(); }}>End call</SkeuoButton>
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
