/** Plain-language labels for SaaS users (avoid internal stack / PSTN jargon). */

export const PHONE_STACK_LABEL = 'Live phone AI';

export const CALL_BUCKET_LABELS = {
  all: 'All calls',
  answered: 'Answered',
  missed: 'Missed / no answer',
  declined: 'Busy or declined',
  outbound: 'Outgoing',
  inbound: 'Incoming',
};

export function callBucket(call) {
  if (!call) return 'all';
  const dir = String(call.direction || '').toLowerCase();
  if (dir === 'outbound') return 'outbound';
  const reason = String(call.endReason || call.end_reason || '').toLowerCase();
  const disp = String(call.disposition || '').toLowerCase();
  const sec =
    call.durationSec ??
    (() => {
      const m = String(call.duration || '').match(/(\d+)m\s*(\d+)/);
      if (!m) return 0;
      return parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
    })();
  if (['busy', 'rejected', 'declined', 'cancelled', 'failed'].some((k) => reason.includes(k))) {
    return 'declined';
  }
  if (['no_answer', 'no-answer', 'unanswered', 'timeout'].some((k) => reason.includes(k))) {
    return 'missed';
  }
  if (disp === 'wrong_number') return 'declined';
  if (dir === 'inbound' && sec < 5 && !call.summary) return 'missed';
  if (dir === 'inbound') return 'inbound';
  return 'answered';
}
