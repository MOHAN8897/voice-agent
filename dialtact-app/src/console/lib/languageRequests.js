import { useEffect, useState } from 'react';
import { api } from '../../services/api';

/**
 * Language callback requests, shared by every surface that tags a caller with the
 * language they asked for (follow-ups, callback requests, leads, calls). One
 * request per agent scope is in flight at a time and reused for a few seconds,
 * so a page showing several of these lists asks the server once.
 */
const TTL_MS = 15000;
const cache = new Map();

/** Last ten digits: "+91 98765 43210" and "919876543210" are the same caller. */
export function phoneKey(phone) {
  const digits = String(phone || '').replace(/\D/g, '');
  return digits.length >= 10 ? digits.slice(-10) : digits;
}

const OPEN = new Set(['pending', 'calling']);

function index(rows) {
  const byPhone = new Map();
  const byCall = new Map();
  let open = 0;
  for (const row of rows) {
    const tag = { code: row.requestedLanguage, label: row.requestedLanguageLabel, status: row.status, open: OPEN.has(row.status) };
    if (tag.open) open += 1;
    const key = phoneKey(row.phone);
    // Newest first from the API; an open request wins over a closed one for the same caller.
    if (key && (!byPhone.has(key) || (tag.open && !byPhone.get(key).open))) byPhone.set(key, tag);
    if (row.callId && !byCall.has(row.callId)) byCall.set(row.callId, { ...tag, role: 'requested' });
    if (row.callbackCallId && !byCall.has(row.callbackCallId)) byCall.set(row.callbackCallId, { ...tag, role: 'callback' });
  }
  return { byPhone, byCall, open };
}

const EMPTY = { byPhone: new Map(), byCall: new Map(), open: 0 };

export function loadLanguageRequests(agentId = null, { force = false } = {}) {
  const scope = agentId || '';
  const hit = cache.get(scope);
  if (!force && hit && Date.now() - hit.at < TTL_MS) return hit.promise;
  const params = new URLSearchParams({ status: 'all' });
  if (agentId) params.set('agentId', agentId);
  const promise = api.request('GET', `/api/language-switch-requests?${params}`)
    .then((data) => index(data?.requests || []))
    .catch(() => { cache.delete(scope); return EMPTY; });
  cache.set(scope, { at: Date.now(), promise });
  return promise;
}

/** Drop cached requests (after a call, a status change or a campaign). */
export function invalidateLanguageRequests() { cache.clear(); }

/** `{ byPhone, byCall, open }` for this agent scope; empty until loaded, never throws. */
export function useLanguageRequests(agentId = null, revision = 0) {
  const [state, setState] = useState(EMPTY);
  useEffect(() => {
    let active = true;
    loadLanguageRequests(agentId, { force: revision > 0 }).then((value) => { if (active) setState(value); });
    return () => { active = false; };
  }, [agentId, revision]);
  return state;
}

/** The tag prefix for a request: still waiting, being called, or done. */
export function languagePrefix(tag) {
  if (!tag) return '';
  if (tag.role === 'requested') return 'Asked for';
  if (tag.status === 'calling') return 'Calling in';
  if (tag.status === 'done' || tag.role === 'callback') return 'Called in';
  if (tag.status === 'dismissed') return 'Asked for';
  return 'Wants';
}
