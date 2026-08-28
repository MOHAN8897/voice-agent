export type VoiceTraceFn = (kind: string, detail: string) => void;

export type TtsTextChunk = {
  turnId: string;
  sequenceNumber: number;
  text: string;
};

export type TtsAudioChunk = {
  turnId: string;
  /** Monotonic within turn; audio from WS is FIFO when text is sent in order. */
  sequenceNumber: number;
  pcm: ArrayBuffer;
};

export type TtsConfig = {
  provider?: "sarvam" | "cartesia" | string;
  model: string;
  speaker?: string;
  pace?: number;
  language_code: string;
  min_buffer_size?: number;
  max_chunk_length?: number;
  output_audio_codec?: string;
  output_audio_bitrate?: string;
  temperature?: number;
  sample_rate?: number;
};

export const VOICE_PIPELINE_LIMITS = {
  maxTextChunksQueued: 24,
  maxAudioChunksBuffered: 256,
  smallResponseMaxChars: 140,
  minChunkChars: 14,
  maxChunkChars: 220,
  flushTimeoutMs: 45_000,
} as const;
