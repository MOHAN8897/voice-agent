/** Plain-language labels for SaaS users (avoid internal stack / PSTN jargon). */

import { CALL_STATUS_META, CALL_STATUS_TABS, callStatus, isCallStatus } from './callStatus';

export const PHONE_STACK_LABEL = 'Live phone AI';

export const CALL_BUCKET_LABELS = {
  all: 'All calls',
  answered: CALL_STATUS_META.answered.label,
  missed: CALL_STATUS_META.missed.label,
  declined: CALL_STATUS_META.declined.label,
  outbound: CALL_STATUS_META.outbound.label,
  voicemail: CALL_STATUS_META.voicemail.label,
  failed: CALL_STATUS_META.failed.label,
  in_progress: CALL_STATUS_META.in_progress.label,
};

export { CALL_STATUS_TABS, callStatus };

/**
 * Filter value used by the call-history tabs. `all` means no status filter;
 * everything else is a canonical status the server understands.
 */
export function callBucket(call) {
  if (!call) return 'all';
  const status = callStatus(call);
  return isCallStatus(status) ? status : 'all';
}

/** Tabs that can be sent to the API as `?status=`. */
export function bucketToApiStatus(bucket) {
  if (!bucket || bucket === 'all') return null;
  return isCallStatus(bucket) ? bucket : null;
}
