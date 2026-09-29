/**
 * Canonical call status — the single vocabulary the console filters on.
 *
 * Mirrors `server/call/call_status.py`. The server is authoritative: every list
 * response carries `status`, and the console filters with `?status=` rather than
 * re-deriving buckets from raw fields. `deriveStatus` exists only as a fallback
 * for rows the server has not classified yet.
 */

export const CALL_STATUSES = [
  'answered',
  'missed',
  'outbound',
  'declined',
  'failed',
  'voicemail',
  'in_progress',
];

export const CALL_STATUS_META = {
  answered: {
    label: 'Answered',
    short: 'Answered',
    tone: 'success',
    hint: 'The agent spoke with the caller.',
  },
  missed: {
    label: 'Missed',
    short: 'Missed',
    tone: 'warning',
    hint: 'Nobody picked up, or the caller hung up immediately.',
  },
  outbound: {
    label: 'Outgoing',
    short: 'Outgoing',
    tone: 'info',
    hint: 'A call your agent placed.',
  },
  declined: {
    label: 'Busy or declined',
    short: 'Declined',
    tone: 'muted',
    hint: 'The line was busy or the other side declined.',
  },
  failed: {
    label: 'Failed',
    short: 'Failed',
    tone: 'danger',
    hint: 'The carrier could not connect the call.',
  },
  voicemail: {
    label: 'Voicemail',
    short: 'Voicemail',
    tone: 'muted',
    hint: 'The call reached an answering machine or after-hours greeting.',
  },
  in_progress: {
    label: 'Live',
    short: 'Live',
    tone: 'info',
    hint: 'This call is still connected.',
  },
};

export const DEFAULT_CALL_STATUS = 'answered';

export function isCallStatus(value) {
  return CALL_STATUSES.includes(String(value || '').trim().toLowerCase());
}

export function normalizeCallStatuses(value) {
  const raw = Array.isArray(value) ? value : String(value || '').split(',');
  const out = [];
  for (const item of raw) {
    const token = String(item || '').trim().toLowerCase();
    if (isCallStatus(token) && !out.includes(token)) out.push(token);
  }
  return out;
}

export function statusMeta(status) {
  return CALL_STATUS_META[status] || CALL_STATUS_META[DEFAULT_CALL_STATUS];
}

export function statusLabel(status) {
  return statusMeta(status).label;
}

/** Tabs shown above the call list, in the order a user cares about them. */
export const CALL_STATUS_TABS = [
  { id: 'all', label: 'All calls' },
  { id: 'answered', label: 'Answered' },
  { id: 'missed', label: 'Missed' },
  { id: 'voicemail', label: 'Voicemail' },
  { id: 'outbound', label: 'Outgoing' },
  { id: 'declined', label: 'Declined' },
  { id: 'failed', label: 'Failed' },
  { id: 'in_progress', label: 'Live' },
];

/**
 * Fallback classification for rows the server has not stamped.
 * Only used when `row.status` is absent; prefer the server value.
 */
export function deriveStatus(row) {
  if (!row) return DEFAULT_CALL_STATUS;
  const haystack = `${row.end_reason || row.endReason || ''} ${row.disposition || ''}`.toLowerCase();
  if (/(voicemail|answering_machine|answering machine|after_hours|after-hours)/.test(haystack)) {
    return 'voicemail';
  }
  if (/(no_answer|no-answer|noanswer|unanswered|not_answered|no_response|timeout|ring_timeout|outbound_ring)/.test(haystack)) {
    return 'missed';
  }
  if (/(busy|rejected|declined|cancelled|canceled|refused)/.test(haystack)) return 'declined';
  const duration = Number(row.duration_sec ?? row.durationSec ?? 0) || 0;
  if (row.in_progress || (!row.ended_at && !row.endedAt)) return 'in_progress';
  if (/(failed|failure|error|unavailable|unreachable|carrier|provider_failure|runtime_failure)/.test(haystack)) {
    return duration < 5 ? 'failed' : 'answered';
  }
  if (String(row.direction || '').toLowerCase() === 'outbound') return 'outbound';
  return duration < 5 ? 'missed' : 'answered';
}

export function callStatus(row) {
  const stored = String(row?.status || '').trim().toLowerCase();
  return isCallStatus(stored) ? stored : deriveStatus(row);
}

/** True when a call is worth offering a "call back" action for. */
export function isCallbackCandidate(row) {
  const status = callStatus(row);
  return status === 'missed' || status === 'voicemail' || status === 'declined';
}

export function formatDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  if (total === 0) return '—';
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}m ${String(secs).padStart(2, '0')}s`;
}
