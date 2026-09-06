import { StreamingTextChunker } from "@/lib/voice/text-chunker";
import { billingCharCount } from "@/lib/billing-chars";
import { StreamingTtsClient } from "@/lib/voice/streaming-tts-client";
import { StreamingAudioPlayback } from "@/lib/voice/streaming-audio-playback";
import { fetchTtsConfig } from "@/lib/voice/tts-config";
import { expandSpokenNumbers } from "@/lib/voice/spoken-numbers";
import { VOICE_PIPELINE_LIMITS, type VoiceTraceFn } from "@/lib/voice/types";

export type TurnTtsPipelineOptions = {
  turnId: string;
  turnGen: number;
  isTurnActive: () => boolean;
  sessionId: string;
  callId: string | null;
  languageCode: string;
  playback: StreamingAudioPlayback;
  ttsClient: StreamingTtsClient;
  trace: VoiceTraceFn;
  onSpeakingStart: () => void;
  onSpeakingEnd: () => void;
};

/**
 * Per-turn coordinator: LLM deltas → TextChunker → WS TTS → ordered PCM playback.
 */
export class TurnTtsPipeline {
  private readonly opts: TurnTtsPipelineOptions;
  private readonly chunker: StreamingTextChunker;
  private cancelled = false;
  private speaking = false;
  private llmFirstToken = false;
  private playbackDone: Promise<void> = Promise.resolve();
  private audioSeq = 0;
  private textQueue: Promise<void> = Promise.resolve();
  private ttsAudioBytes = 0;

  constructor(opts: TurnTtsPipelineOptions) {
    this.opts = opts;
    this.chunker = new StreamingTextChunker(opts.turnId);
  }

  private trace(kind: string, detail: string) {
    this.opts.trace(kind, `${detail} turnId=${this.opts.turnId}`);
  }

  isActive(): boolean {
    return !this.cancelled && this.opts.isTurnActive();
  }

  async start(): Promise<void> {
    this.trace("turn:start", `gen=${this.opts.turnGen}`);
    const cfg = await fetchTtsConfig(this.opts.sessionId, this.opts.languageCode, this.opts.callId);
    this.opts.playback.setSampleRate(cfg.sample_rate || 24000);
    this.opts.playback.userGesture();

    this.opts.playback.attachTurn(this.opts.turnId, () => this.isActive(), () => this.cancel());

    await this.opts.ttsClient.refreshConfigForTurn();

    this.opts.ttsClient.beginTurn({
      turnId: this.opts.turnId,
      isActive: () => this.isActive(),
      onAudio: (pcm) => {
        if (!this.isActive()) return;
        this.ttsAudioBytes += pcm.byteLength;
        const seq = this.audioSeq++;
        this.markSpeaking();
        this.opts.playback.enqueuePcm(this.opts.turnId, seq, pcm);
        if (seq === 0) {
          this.trace("tts:first_audio", "");
        }
      },
      onFirstAudio: () => this.markSpeaking(),
      onComplete: () => {
        this.trace("turn:tts_complete", "");
      },
      onError: (err) => {
        if (this.cancelled) return;
        this.trace("tts:error", `${err.message}`);
      },
    });
  }

  onLlmDelta(delta: string): void {
    if (!delta || !this.isActive()) return;
    if (!this.llmFirstToken) {
      this.llmFirstToken = true;
      this.trace("llm:first_token", "");
    }

    const chunks = this.chunker.append(expandSpokenNumbers(delta));
    for (const chunk of chunks) {
      this.enqueueTextChunk(chunk.text, chunk.sequenceNumber);
    }
  }

  private enqueueTextChunk(text: string, sequenceNumber: number) {
    if (!this.isActive()) return;
    this.trace("text:chunk_ready", `seq=${sequenceNumber} chars=${text.length}`);
    this.textQueue = this.textQueue.then(() => {
      if (!this.isActive()) return;
      this.opts.ttsClient.sendText(text, sequenceNumber);
    });
  }

  async finishLlm(): Promise<void> {
    if (!this.isActive()) return;

    const finalChunks = this.chunker.flush();
    for (const chunk of finalChunks) {
      this.enqueueTextChunk(chunk.text, chunk.sequenceNumber);
    }

    await this.textQueue;

    if (!this.isActive()) return;

    await this.opts.ttsClient.flushTurn();

    if (!this.isActive()) return;

    this.playbackDone = this.opts.playback.waitUntilIdle();
    await this.playbackDone;

    if (this.isActive()) {
      this.opts.onSpeakingEnd();
      this.trace("turn:complete", `text=${this.chunker.getFullText().length}c`);
    }
  }

  cancel(): void {
    if (this.cancelled) return;
    this.cancelled = true;
    this.opts.ttsClient.cancelTurn();
    this.trace("tts:cancel", "pipeline");
    this.opts.onSpeakingEnd();
  }

  private markSpeaking() {
    if (this.speaking) return;
    this.speaking = true;
    this.opts.onSpeakingStart();
  }

  getFullText(): string {
    return this.chunker.getFullText();
  }

  getMetrics(): { ttsChars: number; ttsAudioBytes: number } {
    return { ttsChars: billingCharCount(this.chunker.getFullText()), ttsAudioBytes: this.ttsAudioBytes };
  }
}

export { VOICE_PIPELINE_LIMITS };
