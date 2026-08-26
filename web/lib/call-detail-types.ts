export type TranscriptLine = {
  seq?: number;
  role?: string;
  text?: string;
  ts?: string;
  stt_latency_ms?: number;
  brain_latency_ms?: number;
  tts_first_byte_ms?: number;
  partial?: boolean;
};

export type TraceTurn = {
  turn?: number;
  stt_final_ms?: number;
  llm_ttft_ms?: number;
  tts_first_audio_ms?: number;
  e2e_ms?: number;
  memory_ops_applied?: number;
  memory_merge_ms?: number;
  errors?: string[];
};

export type TracePayload = {
  call_id?: string;
  combination_id?: string;
  compiled_brain_version?: string;
  turns?: TraceTurn[];
};

export type MemoryEvent = {
  turn_seq?: number;
  source?: string;
  operations?: unknown[];
  at?: string;
};

export type CallMeta = {
  call_id?: string;
  agent_id?: string;
  channel?: string;
  tier?: string;
  disposition?: string;
  duration_sec?: number;
  started_at?: string;
  ended_at?: string;
  combination_id?: string;
  compiled_brain_version?: string;
  finalization_status?: string;
  environment?: string;
  direction?: string;
  end_reason?: string;
  resolved_stack?: Record<string, unknown>;
  finalization?: Record<string, unknown>;
  status?: string;
};

export type MemorySnapshot = {
  facts?: Record<string, string>;
  preferences?: Record<string, string>;
  important_context?: string;
  summary?: string;
};

export type OutcomePayload = {
  disposition?: string;
  disposition_confidence?: number;
  summary_te?: string;
  summary_en?: string;
  next_action?: string | null;
  extracted_fields?: Record<string, string>;
  objections?: string[];
  notes?: string | null;
};

export type CallDetailData = {
  meta: CallMeta;
  transcript: TranscriptLine[];
  memory: MemorySnapshot;
  outcome: OutcomePayload | null;
  trace: TracePayload;
  memoryEvents: MemoryEvent[];
};

export type TimelineLane = "audio" | "stt" | "llm" | "tts" | "memory" | "error";

export type UnifiedTimelineEvent = {
  id: string;
  lane: TimelineLane;
  turn?: number;
  label: string;
  detail?: string;
  ms?: number;
  ts?: string;
};
