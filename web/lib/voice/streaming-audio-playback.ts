import { createPcmStreamPlayer, type PcmStreamPlayer } from "@/lib/voice/pcm-stream-player";
import { VOICE_PIPELINE_LIMITS, type VoiceTraceFn } from "@/lib/voice/types";

type OrderedAudio = {
  turnId: string;
  sequenceNumber: number;
  pcm: ArrayBuffer;
};

/**
 * Ordered streaming audio playback — Web Audio PCM scheduling with sequence guard.
 * Implements stop()/userGesture() compatible with existing barge-in (playbackRef.stop()).
 */
export class StreamingAudioPlayback {
  unlocked = false;
  private ctx: AudioContext | null = null;
  private sharedCtx: AudioContext | null = null;
  private player: PcmStreamPlayer | null = null;
  private sampleRate = 24000;
  private cancelTurn: (() => void) | null = null;
  private activeTurnId: string | null = null;
  private isActiveFn: (() => boolean) | null = null;
  private nextExpectedSeq = 0;
  private pending = new Map<number, OrderedAudio>();
  private bufferedCount = 0;
  private trace?: VoiceTraceFn;
  private firstPlaybackFired = false;

  setTrace(fn: VoiceTraceFn) {
    this.trace = fn;
  }

  /** Route TTS through the mic capture context so browser AEC can cancel speaker playback. */
  setSharedContext(ctx: AudioContext | null) {
    if (this.sharedCtx === ctx) return;
    this.sharedCtx = ctx;
    this.player = null;
  }

  setSampleRate(rate: number) {
    if (this.sampleRate === rate) return;
    this.sampleRate = rate;
    this.player = null;
  }

  attachTurn(turnId: string, isActive: () => boolean, onCancel: () => void) {
    this.activeTurnId = turnId;
    this.isActiveFn = isActive;
    this.cancelTurn = onCancel;
    this.nextExpectedSeq = 0;
    this.pending.clear();
    this.bufferedCount = 0;
    this.firstPlaybackFired = false;
  }

  userGesture() {
    this.unlocked = true;
    void this.ensureContext();
  }

  async ensureContext(): Promise<AudioContext> {
    const target = this.sharedCtx || this.ctx;
    if (!target || target.state === "closed") {
      if (this.sharedCtx) {
        throw new Error("Shared audio context is closed");
      }
      this.ctx = new AudioContext({ sampleRate: this.sampleRate, latencyHint: "interactive" });
    }
    const ctx = this.sharedCtx || this.ctx!;
    if (ctx.state === "suspended") {
      try {
        await ctx.resume();
      } catch {
        /* gesture may be required */
      }
    }
    return ctx;
  }

  enqueuePcm(turnId: string, sequenceNumber: number, pcm: ArrayBuffer) {
    if (!this.unlocked) {
      this.trace?.("playback:blocked", `turn=${turnId} audio locked (no user gesture)`);
      return;
    }
    if (!this.isActiveFn?.() || this.activeTurnId !== turnId) return;
    if (this.bufferedCount >= VOICE_PIPELINE_LIMITS.maxAudioChunksBuffered) {
      this.trace?.("playback:buffer", `drop turn=${turnId} backpressure`);
      return;
    }

    this.pending.set(sequenceNumber, { turnId, sequenceNumber, pcm });
    this.bufferedCount += 1;
    this.trace?.("playback:buffer", `turn=${turnId} seq=${sequenceNumber} pending=${this.pending.size}`);
    this.drainOrdered();
  }

  private async drainOrdered() {
    if (!this.unlocked || !this.isActiveFn?.()) return;
    const ctx = await this.ensureContext();
    if (!this.player) {
      this.player = createPcmStreamPlayer(ctx, this.sampleRate);
    }

    while (this.pending.has(this.nextExpectedSeq)) {
      const item = this.pending.get(this.nextExpectedSeq)!;
      this.pending.delete(this.nextExpectedSeq);
      this.bufferedCount = Math.max(0, this.bufferedCount - 1);
      if (!this.isActiveFn() || this.activeTurnId !== item.turnId) return;

      if (!this.firstPlaybackFired) {
        this.firstPlaybackFired = true;
        this.trace?.("playback:start", `turn=${item.turnId}`);
      }
      this.player.appendPcm16(item.pcm);
      this.nextExpectedSeq += 1;
    }
  }

  async waitUntilIdle(timeoutMs = 120_000): Promise<void> {
    if (!this.player) return;
    await this.player.waitUntilIdle(timeoutMs);
    this.trace?.("playback:finish", `turn=${this.activeTurnId || "none"}`);
  }

  /** Called by existing doBargeIn via playbackRef.stop() — do not change barge-in. */
  stop() {
    this.cancelTurn?.();
    this.cancelTurn = null;
    this.activeTurnId = null;
    this.isActiveFn = null;
    this.pending.clear();
    this.bufferedCount = 0;
    this.nextExpectedSeq = 0;
    this.player?.reset();
    this.firstPlaybackFired = false;
  }

  close() {
    this.stop();
    if (!this.sharedCtx && this.ctx && this.ctx.state !== "closed") {
      void this.ctx.close();
    }
    this.ctx = null;
    this.sharedCtx = null;
    this.player = null;
  }
}
