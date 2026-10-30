/**
 * Plain-language labels for internal values.
 *
 * Callers should not have to know that `realtime_voice` is a pipeline name or that
 * `agent_hangup` is a carrier reason. Anything user-facing goes through here so the
 * internal vocabulary can change without leaking into the console.
 */

/** Internal call pipelines → what the user sees. */
const PIPELINE_LABEL = {
  realtime_voice: 'Real-time voice',
  realtime_text: 'Real-time voice',
  realtime_audio: 'Real-time voice',
  pstn_realtime: 'Real-time voice',
  stt_tts_pipeline: 'Speech to text and back',
  browser_text: 'Browser test',
  test: 'Test call',
};

/**
 * Carrier / lifecycle end reasons → what a customer would understand.
 * Anything unrecognised is deliberately not shown rather than dumped raw.
 */
const END_REASON_LABEL = {
  pstn_hangup: 'Call ended',
  user_stop: 'Call ended',
  agent_hangup: 'Agent ended the call',
  goodbye: 'Goodbye',
  firm_refusal: 'Caller declined',
  goal_complete: 'Handled',
  out_of_scope: 'Out of scope',
  abuse: 'Caller hung up',
  transfer: 'Transferred',
  opt_out: 'Caller opted out',
  callback_cancelled: 'Callback cancelled',
  max_duration: 'Call length limit reached',
  silence_timeout: 'Caller went quiet',
  farewell_timeout: 'Goodbye timed out',
  response_timeout: 'Caller went quiet',
  response_failure: 'Call ended',
  runtime_failure: 'Call ended unexpectedly',
  provider_failure: 'Call ended unexpectedly',
  stream_error: 'Call ended unexpectedly',
  timeout: 'No answer',
  stale_recovery: 'Call ended unexpectedly',
  superseded: 'Replaced by a newer call',
  ws_disconnect: 'Call ended unexpectedly',
  browser_unload: 'Page closed',
  error: 'Call ended unexpectedly',
  no_answer: 'No answer',
  busy: 'Line busy',
  rejected: 'Call declined',
  cancelled: 'Call cancelled',
  voicemail: 'Voicemail',
  answering_machine: 'Answering machine',
  after_hours: 'Outside business hours',
  technical_fallback: 'Technical issue — caller told, call ended',
  technical_failure: 'Technical issue — call ended',
};

/** End reasons that mean the AI service failed mid-call (outage message played). */
const TECHNICAL_FAILURE_REASONS = new Set(['technical_fallback', 'technical_failure']);

export function isTechnicalFailure(reason) {
  return TECHNICAL_FAILURE_REASONS.has(String(reason || '').trim().toLowerCase());
}

export function pipelineLabel(pipeline) {
  const key = String(pipeline || '').trim().toLowerCase();
  if (!key) return null;
  return PIPELINE_LABEL[key] || null;
}

/** Returns null for anything we cannot confidently explain to a user. */
export function endReasonLabel(reason) {
  const key = String(reason || '').trim().toLowerCase();
  if (!key) return null;
  return END_REASON_LABEL[key] || null;
}

/**
 * A short, human reference for a call, so support can quote it without exposing a
 * raw database id. Stable within a session for the same call.
 */
export function callReference(callId) {
  const id = String(callId || '');
  if (!id) return null;
  return `#${id.replace(/-/g, '').slice(0, 6).toUpperCase()}`;
}

/* -------------------------------------------------------------------------- */
/* Shared humanizer. Every tag, disposition, status or stage shown to a       */
/* tenant goes through here. Rule: never render a raw token (snake_case,      */
/* `category:value`, `custom:x`). Unknown tokens become sentence-case words.  */
/* -------------------------------------------------------------------------- */

/** `callback_required` / `phone-known` → `Callback required` / `Phone known`. */
// Provider and stack names are internal; a misconfigured label must never show them to tenants.
export const BLOCKED_TENANT_TERMS = /\b(vobiz|telnyx|nango|exotel|plivo|composio|sarvam|gemini|gnani|cartesia|openai|elevenlabs|deepgram|playht|murf|azure|bulbul|timbre|sonic|saaras|saarika)\b/i;

/** The label if it is safe to show a tenant, otherwise an empty string. */
export function publicLabel(value) {
  const text = typeof value === 'string' ? value.trim() : '';
  return text && !BLOCKED_TENANT_TERMS.test(text) ? text : '';
}

export function humanizeToken(value) {
  const raw = String(value ?? '').trim();
  if (!raw) return '';
  const words = raw.replace(/[_\-.]+/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Post-call outcome (`calls.disposition`) → owner-facing words. */
const DISPOSITION_LABEL = {
  new_lead: 'New lead',
  interested: 'Interested',
  qualified: 'Qualified',
  site_visit_planned: 'Site visit planned',
  callback_required: 'Wants a callback',
  not_interested: 'Not interested',
  wrong_number: 'Wrong number',
  converted: 'Converted',
  no_outcome: 'No clear outcome',
};

export function dispositionLabel(disposition) {
  const key = String(disposition || '').trim().toLowerCase();
  if (!key) return null;
  return DISPOSITION_LABEL[key] || humanizeToken(key);
}

/** Status tags (`category:value`) from server/call/outcome_schema.py. */
const TAG_LABEL = {
  'followup:callback': 'Wants a callback',
  'followup:language_switch': 'Callback in another language',
  'followup:schedule_pending': 'Time to be confirmed',
  'followup:send_info': 'Send details',
  'followup:send_quote': 'Send a quote',
  'followup:site_visit': 'Site visit',
  'contact:email_known': 'Email captured',
  'contact:name_known': 'Name captured',
  'contact:phone_known': 'Number captured',
  'contact:preferred_language': 'Language preference noted',
  'compliance:disclosure_delivered': 'Recording notice given',
  'compliance:disclosure_missing': 'Recording notice missed',
  'compliance:recording_objected': 'Objected to recording',
  'quality:agent_failure': 'Agent problem',
  'quality:inconclusive': 'Unclear call',
  'quality:language_mismatch': 'Language mismatch',
  'quality:poor_audio': 'Poor audio',
  'quality:short_call': 'Short call',
  'quality:tts_failure': 'Voice problem',
  'signal:do_not_call': 'Do not call',
  'signal:ready_to_buy': 'Ready to buy',
  'signal:decision_maker': 'Decision maker',
  'signal:budget_confirmed': 'Budget confirmed',
  'signal:competitor_mentioned': 'Mentioned a competitor',
  'signal:needs_approval': 'Needs approval',
  'signal:price_sensitive': 'Price sensitive',
  'signal:repeat_customer': 'Repeat customer',
  'action:required': 'Action needed',
  'action:urgent': 'Urgent',
};

/** `custom:solar_panels` → `Solar panels`; `outcome:qualified` → `Qualified`. */
export function tagLabel(tag) {
  const raw = String(tag || '').trim().toLowerCase();
  if (!raw) return '';
  if (TAG_LABEL[raw]) return TAG_LABEL[raw];
  const [category, ...rest] = raw.split(':');
  const value = rest.join(':');
  if (!value) return humanizeToken(category);
  if (category === 'outcome') return dispositionLabel(value);
  return humanizeToken(value);
}

/** Semantic tone for a tag, following DESIGN.md status-colour rules. */
export function tagTone(tag) {
  const raw = String(tag || '').trim().toLowerCase();
  if (raw === 'signal:do_not_call' || raw.startsWith('quality:') || raw === 'compliance:disclosure_missing') return 'warning';
  if (raw === 'action:required' || raw === 'action:urgent' || raw.startsWith('followup:')) return 'warning';
  if (['outcome:qualified', 'outcome:converted', 'outcome:site_visit_planned', 'signal:ready_to_buy'].includes(raw)) return 'success';
  return 'neutral';
}

/**
 * Status words for badges: agent, call, campaign, lead stage, follow-up, number,
 * integration. Returns `{ label, tone }`. Tone follows DESIGN.md: danger = a problem,
 * warning = needs attention, success = done or live, info/neutral = plain facts.
 */
const STATUS_WORDS = {
  active: ['Active', 'success'],
  live: ['Live', 'success'],
  running: ['Running', 'success'],
  in_progress: ['On a call', 'success'],
  answered: ['Answered', 'success'],
  completed: ['Completed', 'success'],
  converted: ['Converted', 'success'],
  qualified: ['Qualified', 'success'],
  resolved: ['Resolved', 'success'],
  'meeting booked': ['Meeting booked', 'success'],
  meeting_booked: ['Meeting booked', 'success'],
  done: ['Done', 'success'],
  connected: ['Connected', 'success'],
  synced: ['Synced', 'neutral'],
  paused: ['Paused', 'warning'],
  draft: ['Draft', 'neutral'],
  idle: ['Idle', 'neutral'],
  new: ['New', 'info'],
  contacted: ['Contacted', 'info'],
  pending: ['Pending', 'warning'],
  scheduled: ['Scheduled', 'info'],
  needs_review: ['Needs review', 'warning'],
  requires_review: ['Needs review', 'warning'],
  requested: ['Requested', 'warning'],
  blocked: ['Blocked', 'warning'],
  missed: ['Missed', 'warning'],
  voicemail: ['Voicemail', 'neutral'],
  declined: ['Declined', 'neutral'],
  inbound: ['Incoming', 'info'],
  outbound: ['Outgoing', 'info'],
  unqualified: ['Unqualified', 'neutral'],
  not_interested: ['Not interested', 'neutral'],
  cancelled: ['Cancelled', 'neutral'],
  canceled: ['Cancelled', 'neutral'],
  expired: ['Expired', 'neutral'],
  suppressed: ['Skipped', 'neutral'],
  dismissed: ['Dismissed', 'neutral'],
  failed: ['Failed', 'danger'],
  error: ['Needs attention', 'danger'],
  suspended_unpaid: ['Paused, rent due', 'danger'],
  grace: ['Payment due', 'warning'],
  lapsed: ['Lapsed', 'danger'],
};

export function statusWord(status) {
  const key = String(status || '').trim().toLowerCase();
  if (!key) return { label: 'Unknown', tone: 'neutral' };
  const hit = STATUS_WORDS[key];
  if (hit) return { label: hit[0], tone: hit[1] };
  if (DISPOSITION_LABEL[key]) return { label: DISPOSITION_LABEL[key], tone: 'neutral' };
  return { label: humanizeToken(key), tone: 'neutral' };
}

/** Ingress policy reasons (`after_hours_voicemail`, `inbound_disabled`) as words. */
const POLICY_REASON_LABEL = {
  answered: 'answered',
  inbound_disabled: 'incoming calls are turned off for this line',
  after_hours_voicemail: 'outside business hours, sent to voicemail',
  after_hours_hangup: 'outside business hours',
  carrier_hangup: 'the caller hung up while it was ringing',
};

export function policyReasonLabel(reason) {
  const key = String(reason || '').trim().toLowerCase();
  if (!key) return null;
  return POLICY_REASON_LABEL[key] || humanizeToken(key).toLowerCase();
}
