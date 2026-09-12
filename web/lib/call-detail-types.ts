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
  input_tokens?: number;
  output_tokens?: number;
  cached_tokens?: number;
  cache_write_tokens?: number;
  input_audio_tokens?: number;
  output_audio_tokens?: number;
  cost_usd?: number;
  cost_inr?: number;
  llm_model?: string;
  pipeline?: string;
  user_text?: string;
  assistant_text?: string;
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

export type CallUsage = {
  pipeline?: string;
  llm_model?: string;
  input_tokens?: number;
  output_tokens?: number;
  input_audio_tokens?: number;
  output_audio_tokens?: number;
  cached_tokens?: number;
  turns?: number;
  cost_usd?: number;
  cost_inr?: number;
  duration_sec?: number;
  cost_usd_per_min?: number;
  cost_inr_per_min?: number;
  fx_rate_inr?: number;
  model_cost_usd?: number;
  model_cost_inr?: number;
  telnyx_usd?: number;
  telnyx_inr?: number;
};

export type CallMeta = {
  call_id?: string;
  agent_id?: string;
  channel?: string;
  pipeline?: string;
  caller_id?: string;
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
  usage?: CallUsage;
  cost_usd?: number;
  cost_inr?: number;
  cost_inr_per_min?: number;
  model_cost_inr?: number;
  telnyx_inr?: number;
  audio?: { mix?: boolean; user?: boolean; agent?: boolean };
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
