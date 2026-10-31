import { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { loadLanguageRequests } from './languageRequests';

/**
 * How much work waits behind each Leads sub-tab, from the lists those tabs show:
 *   followups — follow-ups that need review plus pending callback requests
 *   language  — open "call back in another language" requests
 * A list that fails to load counts as unknown (null), never as zero.
 */
export function useLeadWorkCounts(agentId = null, revision = 0) {
  const [counts, setCounts] = useState({ followups: null, language: null });
  useEffect(() => {
    let active = true;
    const scope = agentId ? { agentId } : {};
    const query = agentId ? `?agentId=${encodeURIComponent(agentId)}` : '';
    Promise.allSettled([
      api.followups.list({ ...scope, status: 'needs_review', limit: 1, offset: 0 }),
      api.request('GET', `/api/callback-requests${query}`),
      loadLanguageRequests(agentId, { force: revision > 0 }),
    ]).then(([review, callbacks, language]) => {
      if (!active) return;
      const reviewCount = review.status === 'fulfilled' ? Number(review.value?.total ?? review.value?.jobs?.length ?? 0) : null;
      const callbackCount = callbacks.status === 'fulfilled' ? (callbacks.value?.requests || []).length : null;
      setCounts({
        followups: reviewCount == null && callbackCount == null ? null : (reviewCount || 0) + (callbackCount || 0),
        language: language.status === 'fulfilled' ? language.value.open : null,
      });
    });
    return () => { active = false; };
  }, [agentId, revision]);
  return counts;
}
