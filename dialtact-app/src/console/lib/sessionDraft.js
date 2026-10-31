// Per-tab drafts for forms a tenant fills in and then walks away from: the
// outgoing-call dialer, "Place a call", the campaign builder.
//
// These are not settings: nothing here is saved to the server until the call is
// placed or the campaign is launched. They used to live in component state, so
// switching a sub-tab or opening another page unmounted the form and silently
// threw away the chosen line, number, integrations and campaign options.
//
// sessionStorage, not localStorage: a typed phone number may stay for the life
// of the tab, never on the device afterwards. Keys are scoped to the signed-in
// user and cleared on sign-out, so a second account in the same tab starts empty.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../../context/AuthContext';

const PREFIX = 'dialtact_draft:';

function storage() {
  try {
    return typeof window !== 'undefined' ? window.sessionStorage : null;
  } catch {
    return null;
  }
}

export function readDraft(key) {
  const store = storage();
  if (!store || !key) return null;
  try {
    const raw = store.getItem(key);
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function writeDraft(key, value) {
  const store = storage();
  if (!store || !key) return;
  try {
    store.setItem(key, JSON.stringify(value));
  } catch {
    /* Storage full or blocked: the draft lives only while the form is open. */
  }
}

export function clearDraft(key) {
  const store = storage();
  if (!store || !key) return;
  try {
    store.removeItem(key);
  } catch {
    /* Nothing stored. */
  }
}

/** Remove every draft in this tab (sign-out). */
export function clearAllDrafts() {
  const store = storage();
  if (!store) return;
  try {
    for (let i = store.length - 1; i >= 0; i -= 1) {
      const key = store.key(i);
      if (key && key.startsWith(PREFIX)) store.removeItem(key);
    }
  } catch {
    /* Nothing stored. */
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('dialtact:logout', clearAllDrafts);
}

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/**
 * `[draft, patch, reset]` for an object-shaped form draft.
 *
 * `name` identifies the form and `subject` what it is for (usually the agent id),
 * so each agent keeps its own draft. Changing `subject` swaps to that subject's
 * draft. `patch` merges fields (or takes `prev => fields`); `reset(keep)` drops the
 * stored draft and returns to `initial` plus `keep`. A draft equal to `initial`
 * is not stored at all.
 */
export function useSessionDraft(name, subject, initial) {
  const { user } = useAuth();
  const owner = user?.id || user?.userId || user?.email || 'anon';
  const key = name ? `${PREFIX}${owner}:${name}:${subject || 'all'}` : null;
  const initialRef = useRef(initial);
  initialRef.current = initial;

  const load = (k) => ({ key: k, data: { ...initialRef.current, ...(readDraft(k) || {}) } });
  const [state, setState] = useState(() => load(key));
  let current = state;
  if (state.key !== key) {
    // A different agent (or user): show that one's draft in this same render.
    current = load(key);
    setState(current);
  }

  useEffect(() => {
    if (!current.key) return;
    if (same(current.data, initialRef.current)) clearDraft(current.key);
    else writeDraft(current.key, current.data);
  }, [current]);

  const patch = useCallback((fields) => {
    setState((prev) => {
      const next = typeof fields === 'function' ? fields(prev.data) : fields;
      return { key: prev.key, data: { ...prev.data, ...next } };
    });
  }, []);

  const reset = useCallback((keep = {}) => {
    setState((prev) => {
      clearDraft(prev.key);
      return { key: prev.key, data: { ...initialRef.current, ...keep } };
    });
  }, []);

  return [current.data, patch, reset];
}
