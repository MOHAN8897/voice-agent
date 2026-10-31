import { VOICE_PIPELINE_LIMITS } from "@/lib/voice/types";
import type { TtsTextChunk } from "@/lib/voice/types";

const STRONG_END = /[.!?।…\n]/;

function wordCount(text: string): number {
  return (text.trim().match(/\S+/g) || []).length;
}

function lastWordBoundary(text: string, maxIndex: number): number {
  const slice = text.slice(0, maxIndex);
  const sp = slice.lastIndexOf(" ");
  return sp > 0 ? sp : maxIndex;
}

/**
 * Streaming text chunker — sentence boundaries only (. ? ! ।).
 * First sentence flushes immediately; tiny complete replies still emit as one chunk on flush.
 */
export class StreamingTextChunker {
  private fullText = "";
  private sentEnd = 0;
  private sequence = 0;
  private readonly turnId: string;

  constructor(turnId: string) {
    this.turnId = turnId;
  }

  getFullText(): string {
    return this.fullText;
  }

  getSentEnd(): number {
    return this.sentEnd;
  }

  append(delta: string): TtsTextChunk[] {
    if (!delta) return [];
    this.fullText += delta;
    return this.extract(false);
  }

  flush(): TtsTextChunk[] {
    return this.extract(true);
  }

  private extract(streamDone: boolean): TtsTextChunk[] {
    const chunks: TtsTextChunk[] = [];
    const { smallResponseMaxChars, minChunkChars, maxChunkChars } = VOICE_PIPELINE_LIMITS;

    if (streamDone && this.sentEnd === 0 && this.fullText.trim().length <= smallResponseMaxChars) {
      const text = this.fullText.trim();
      if (text) {
        chunks.push(this.makeChunk(text));
        this.sentEnd = this.fullText.length;
      }
      return chunks;
    }

    while (this.sentEnd < this.fullText.length) {
      const unsent = this.fullText.slice(this.sentEnd);
      const boundary = this.findBoundary(unsent, streamDone);
      if (boundary < 0) break;

      const piece = unsent.slice(0, boundary).trim();
      if (!piece) {
        this.sentEnd += boundary;
        continue;
      }
      if (!streamDone && piece.length < minChunkChars && unsent.length < maxChunkChars) {
        break;
      }
      if (!streamDone && wordCount(piece) < 2 && unsent.length < maxChunkChars) {
        break;
      }

      chunks.push(this.makeChunk(piece));
      this.sentEnd += boundary;
    }

    if (streamDone) {
      const tail = this.fullText.slice(this.sentEnd).trim();
      if (tail) {
        chunks.push(this.makeChunk(tail));
        this.sentEnd = this.fullText.length;
      }
    }

    return chunks;
  }

  private findBoundary(unsent: string, streamDone: boolean): number {
    const { minChunkChars, maxChunkChars, forceFlushAt } =
      VOICE_PIPELINE_LIMITS;

    if (streamDone) return unsent.length;

    for (let i = 0; i < unsent.length; i++) {
      // Keep decimals like 80.5 intact — only treat "." as sentence end when not before a digit.
      if (STRONG_END.test(unsent[i]) && i + 1 >= minChunkChars) {
        const next = unsent[i + 1];
        if (unsent[i] === "." && next && /\d/.test(next)) continue;
        return i + 1;
      }
    }

    if (unsent.length >= forceFlushAt) {
      return lastWordBoundary(unsent, maxChunkChars);
    }

    if (unsent.length >= maxChunkChars) {
      return lastWordBoundary(unsent, maxChunkChars);
    }

    return -1;
  }

  private makeChunk(text: string): TtsTextChunk {
    const chunk: TtsTextChunk = {
      turnId: this.turnId,
      sequenceNumber: this.sequence,
      text,
    };
    this.sequence += 1;
    return chunk;
  }
}
