import { api } from '../../../services/api';

/**
 * Detail for one feed item (`GET /api/activity/item?id=`): the item rebuilt from its
 * source row, the source call in the same shape `GET /api/calls` returns, related
 * callbacks / follow-ups / language callbacks / integration actions, and lead or
 * campaign facts. Read-only.
 */
export function fetchItemDetail(itemId) {
  return api.request('GET', `/api/activity/item?id=${encodeURIComponent(itemId)}`);
}

/**
 * One call-history row by id, for deep links into the Calls page when the call is
 * not in the first page of history. Tries a connected call, then a ringing attempt.
 * Resolves to the raw timeline row (pass it through `normalizeCall`) or null.
 */
export async function fetchCallRecord(callId) {
  if (!callId) return null;
  for (const prefix of ['call', 'attempt']) {
    try {
      const detail = await fetchItemDetail(`${prefix}:${callId}`);
      if (detail?.call) return detail.call;
    } catch {
      /* not this kind; try the next */
    }
  }
  return null;
}

/** The record a feed item points at, for the panel's "Open in …" buttons. */
export function itemTargets(item, detail) {
  const refs = item?.refs || {};
  const callId = detail?.call?.call_id || refs.callId || null;
  const leadId = detail?.lead?.leadId || refs.leadId || null;
  const campaignId = detail?.campaign?.campaignId || refs.campaignId || null;
  return { callId, leadId, campaignId };
}
