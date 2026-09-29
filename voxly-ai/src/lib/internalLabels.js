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
};

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
