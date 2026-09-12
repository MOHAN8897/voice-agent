import type { OutcomePayload, TranscriptLine } from "@/lib/call-detail-types";

export type DevTelephonyContact = {
  contact_id: string;
  name: string;
  phone: string;
  notes?: string;
  created_at?: string;
  updated_at?: string;
};

export type DevTelephonyHistoryEvent = {
  at: string;
  stage: string;
  detail?: string;
};

export type DevTelephonyHistoryRow = {
  history_id: string;
  provider?: string;
  external_id?: string;
  internal_call_id?: string | null;
  agent_id?: string;
  source_session_id?: string;
  language?: string;
  tier?: string;
  direction?: string;
  from_e164?: string;
  to_e164?: string;
  pipeline?: string;
  status?: string;
  placed_at?: string;
  answered_at?: string | null;
  ended_at?: string | null;
  duration_sec?: number | null;
  events?: DevTelephonyHistoryEvent[];
  usage?: Record<string, unknown>;
  cost?: {
    cost_usd?: number;
    cost_inr?: number;
    cost_inr_per_min?: number;
    model_cost_usd?: number;
    model_cost_inr?: number;
    telnyx_usd?: number;
    telnyx_inr?: number;
    pipeline?: string;
    end_reason?: string;
  };
  has_recording?: boolean;
  transcript_lines?: number;
  transcript?: TranscriptLine[];
  outcome?: OutcomePayload | Record<string, unknown> | null;
  review?: Record<string, unknown>;
  ledger_meta?: Record<string, unknown>;
  meta?: { stack_override?: Record<string, unknown> };
};
