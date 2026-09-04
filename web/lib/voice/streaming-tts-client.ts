import { wsUrl } from "@/lib/api";
import { buildWsTtsConfig, fetchTtsConfig, invalidateTtsConfigCache } from "@/lib/voice/tts-config";
import { onTestStudioVoiceSaved } from "@/lib/voice/voice-runtime-events";
import { VOICE_PIPELINE_LIMITS, type TtsConfig, type VoiceTraceFn } from "@/lib/voice/types";

export type StreamingTtsClientOptions = {
  sessionId: string;
  callId: string | null;
  languageCode: string;
  trace?: VoiceTraceFn;
};

type TurnHandlers = {
  turnId: string;
  isActive: () => boolean;
  onAudio: (pcm: ArrayBuffer, sequenceNumber: number) => void;
  onFirstAudio?: () => void;
  onComplete: () => void;
  onError: (err: Error) => void;
};

/**
 * Session-scoped /ws/tts client — one browser WebSocket, config+text+flush per turn.
 * Protocol matches server/routes/ws.py and client/app.js.
 */
export class StreamingTtsClient {
  private sock: WebSocket | null = null;
  private ready = false;
  private connectPromise: Promise<void> | null = null;
  private model = "bulbul:v3";
  private cfg: TtsConfig | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private activeTurn: TurnHandlers | null = null;
  private flushTimer: ReturnType<typeof setTimeout> | null = null;
  private audioSeq = 0;
  private textChunksSent = 0;
  private callId: string | null;
  private readonly opts: Omit<StreamingTtsClientOptions, "callId"> & { callId?: string | null };
  private readonly voiceUnsub: () => void;

  constructor(opts: StreamingTtsClientOptions) {
    this.opts = opts;
    this.callId = opts.callId;
    this.voiceUnsub = onTestStudioVoiceSaved(() => {
      this.close();
    });
  }

  /** Reconnect WS when call id is assigned after session start. */
  syncCallId(callId: string | null) {
    if (this.callId === callId) return;
    this.callId = callId;
    this.close();
  }

  private trace(kind: string, detail: string) {
    this.opts.trace?.(kind, detail);
  }

  async ensureConnected(): Promise<void> {
    if (this.sock?.readyState === WebSocket.OPEN && this.ready) return;
    if (this.connectPromise) return this.connectPromise;

    this.connectPromise = this.openSocket().finally(() => {
      this.connectPromise = null;
    });
    return this.connectPromise;
  }

  /** Re-fetch runtime TTS config and push it upstream before each spoken turn. */
  async refreshConfigForTurn(): Promise<void> {
    invalidateTtsConfigCache();
    const cfg = await fetchTtsConfig(this.opts.sessionId, this.opts.languageCode, this.callId);
    this.cfg = cfg;
    this.model = cfg.model || "bulbul:v3";
    if (this.sock?.readyState === WebSocket.OPEN) {
      await this.sendConfig(this.sock, cfg);
      this.ready = true;
      return;
    }
    await this.ensureConnected();
  }

  private async openSocket(): Promise<void> {
    invalidateTtsConfigCache();
    const cfg = await fetchTtsConfig(this.opts.sessionId, this.opts.languageCode, this.callId);
    this.cfg = cfg;
    this.model = cfg.model || "bulbul:v3";

    const q = new URLSearchParams({
      model: this.model,
      sessionId: this.opts.sessionId,
    });
    if (this.callId) q.set("call_id", this.callId);

    if (this.sock) {
      try {
        this.sock.close();
      } catch {
        /* ignore */
      }
      this.sock = null;
    }

    await new Promise<void>((resolve, reject) => {
      const sock = new WebSocket(wsUrl(`/ws/tts?${q}`));
      this.sock = sock;
      let settled = false;

      const fail = (err: Error) => {
        if (settled) return;
        settled = true;
        this.ready = false;
        try {
          sock.close();
        } catch {
          /* ignore */
        }
        if (this.sock === sock) this.sock = null;
        reject(err);
      };

      sock.onopen = () => {
        this.sendConfig(sock, cfg)
          .then(() => {
            this.startPing(sock);
            this.ready = true;
            if (!settled) {
              settled = true;
              this.trace("tts:connect", `model=${this.model}`);
              resolve();
            }
          })
          .catch(fail);
      };
      sock.onerror = () => fail(new Error("TTS WebSocket connection failed"));
      sock.onclose = () => {
        this.ready = false;
        this.stopPing();
        if (this.sock === sock) this.sock = null;
      };
      sock.onmessage = (ev) => this.handleMessage(String(ev.data));
    });
  }

  private sendConfig(sock: WebSocket, cfg: TtsConfig): Promise<void> {
    return new Promise((resolve, reject) => {
      if (sock.readyState !== WebSocket.OPEN) {
        reject(new Error("TTS socket not open"));
        return;
      }
      try {
        sock.send(JSON.stringify({ type: "config", data: buildWsTtsConfig(cfg) }));
        resolve();
      } catch (e) {
        reject(e instanceof Error ? e : new Error(String(e)));
      }
    });
  }

  private startPing(sock: WebSocket) {
    this.stopPing();
    this.pingTimer = setInterval(() => {
      if (sock.readyState === WebSocket.OPEN) {
        try {
          sock.send(JSON.stringify({ type: "ping" }));
        } catch {
          /* ignore */
        }
      }
    }, 20_000);
  }

  private stopPing() {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  private handleMessage(raw: string) {
    let m: Record<string, unknown>;
    try {
      m = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return;
    }

    const type = String(m.type || m.event || "");

    if (type === "upstream_reset") {
      this.ready = false;
      this.trace("tts:upstream_reset", String(m.reason || ""));
      if (this.sock?.readyState === WebSocket.OPEN && this.cfg) {
        void this.sendConfig(this.sock, this.cfg).then(() => {
          this.ready = true;
        });
      }
      return;
    }

    const turn = this.activeTurn;
    if (!turn || !turn.isActive()) return;

    if (type === "error") {
      const msg = String(m.message || "TTS provider error");
      turn.onError(new Error(msg));
      return;
    }

    const data = m.data as Record<string, unknown> | string | undefined;
    let b64: string | null = null;
    if (type === "chunk" && typeof data === "string") {
      b64 = data;
    } else if (data && typeof data === "object") {
      b64 =
        (data.audio as string) ||
        (typeof data === "string" ? data : null) ||
        null;
    }
    if (!b64) {
      b64 = (m.audio as string | undefined) || null;
    }

    if (b64) {
      const bin = atob(b64);
      const buf = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
      const seq = this.audioSeq++;
      turn.onFirstAudio?.();
      turn.onAudio(buf.buffer, seq);
      this.trace("tts:audio_chunk", `turn=${turn.turnId} seq=${seq} bytes=${buf.byteLength}`);
      return;
    }

    const eventType = data && typeof data === "object" ? data.event_type : undefined;
    if (type === "end_of_stream" || type === "done" || eventType === "final") {
      this.clearFlushTimer();
      this.trace("tts:complete", `turn=${turn.turnId} chunks=${this.audioSeq}`);
      turn.onComplete();
      this.activeTurn = null;
    }
  }

  beginTurn(handlers: TurnHandlers): void {
    this.activeTurn = handlers;
    this.audioSeq = 0;
    this.textChunksSent = 0;
  }

  sendText(text: string, sequenceNumber: number): void {
    const turn = this.activeTurn;
    if (!turn || !turn.isActive() || !text.trim()) return;
    const sock = this.sock;
    if (!sock || sock.readyState !== WebSocket.OPEN) {
      this.trace("tts:send_blocked", `turn=${turn.turnId} ready=${sock?.readyState ?? "null"}`);
      return;
    }

    if (this.textChunksSent >= VOICE_PIPELINE_LIMITS.maxTextChunksQueued) {
      this.trace("tts:backpressure", `turn=${turn.turnId} text queue full`);
      return;
    }

    try {
      sock.send(JSON.stringify({ type: "text", data: { text } }));
      this.textChunksSent += 1;
      this.trace("tts:send", `turn=${turn.turnId} seq=${sequenceNumber} chars=${text.length}`);
    } catch (e) {
      turn.onError(e instanceof Error ? e : new Error(String(e)));
    }
  }

  flushTurn(): Promise<void> {
    const turn = this.activeTurn;
    if (!turn || !turn.isActive()) return Promise.resolve();

    const sock = this.sock;
    if (!sock || sock.readyState !== WebSocket.OPEN) {
      this.trace("tts:flush_blocked", `turn=${turn.turnId} ready=${sock?.readyState ?? "null"}`);
      turn.onComplete();
      this.activeTurn = null;
      return Promise.resolve();
    }

    return new Promise((resolve) => {
      const prevComplete = turn.onComplete;
      turn.onComplete = () => {
        prevComplete();
        this.clearFlushTimer();
        resolve();
      };

      try {
        sock.send(JSON.stringify({ type: "flush" }));
        this.trace("tts:flush", `turn=${turn.turnId}`);
      } catch {
        turn.onComplete();
        return;
      }

      this.flushTimer = setTimeout(() => {
        this.trace("tts:flush_timeout", `turn=${turn.turnId}`);
        if (this.activeTurn === turn) {
          this.activeTurn = null;
        }
        resolve();
      }, VOICE_PIPELINE_LIMITS.flushTimeoutMs);
    });
  }

  cancelTurn(): void {
    this.clearFlushTimer();
    this.activeTurn = null;
    this.audioSeq = 0;
    this.textChunksSent = 0;
    this.trace("tts:cancel", "turn cancelled");
  }

  close(): void {
    this.cancelTurn();
    this.stopPing();
    if (this.sock) {
      try {
        this.sock.close(1000);
      } catch {
        /* ignore */
      }
      this.sock = null;
    }
    this.ready = false;
  }

  dispose(): void {
    this.voiceUnsub();
    this.close();
  }

  private clearFlushTimer() {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
  }
}
