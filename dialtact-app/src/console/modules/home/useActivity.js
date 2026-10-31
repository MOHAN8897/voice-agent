import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../../services/api';

/**
 * Visibility-aware polling (same contract as CallsModule / CampaignsModule):
 * runs `fn` now, then again after `delay()` ms, pauses while the tab is hidden,
 * and refreshes once immediately when the tab becomes visible again. Never runs
 * two requests at once.
 */
export function useVisiblePoll(fn, delay, deps) {
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const delayRef = useRef(delay);
  delayRef.current = delay;

  useEffect(() => {
    let disposed = false;
    let timer = null;
    let inflight = false;
    const schedule = () => {
      clearTimeout(timer);
      if (!disposed) timer = setTimeout(tick, delayRef.current());
    };
    async function tick(first = false) {
      if (disposed || inflight) return;
      if (!first && typeof document !== 'undefined' && document.visibilityState !== 'visible') {
        schedule();
        return;
      }
      inflight = true;
      try {
        await fnRef.current(first);
      } finally {
        inflight = false;
        schedule();
      }
    }
    tick(true);
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        clearTimeout(timer);
        tick();
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      disposed = true;
      clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

function startOfToday() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

/** Calls in progress + today's numbers. 5s while anyone is on a call, 25s otherwise. */
export function useLiveRail(enabled = true) {
  const [data, setData] = useState({ calls: [], ringing: 0, today: null });
  const [error, setError] = useState('');
  const [loaded, setLoaded] = useState(false);
  const liveRef = useRef(false);

  useVisiblePoll(
    async () => {
      if (!enabled || !api.getToken()) return;
      try {
        const next = await api.activity.live({ since: startOfToday() });
        liveRef.current = (next?.calls?.length || 0) > 0 || (next?.ringing || 0) > 0;
        setData({ calls: next?.calls || [], ringing: next?.ringing || 0, today: next?.today || null });
        setError('');
      } catch (e) {
        setError(e?.message || 'Live status is unavailable.');
      } finally {
        setLoaded(true);
      }
    },
    () => (liveRef.current ? 5000 : 25000),
    [enabled]
  );

  return { ...data, error, loaded, isLive: data.calls.length > 0 };
}

/**
 * The activity feed. The first page is re-polled (8s while calls are live, 25s
 * otherwise); older pages loaded with "Show older" are kept and de-duplicated
 * against the refreshed head. Ids seen for the first time after the initial load
 * are reported in `freshIds` so the UI can animate them in.
 */
export function useActivityFeed({ filter = 'all', agentId = '', fast = false, enabled = true } = {}) {
  const [head, setHead] = useState([]);
  const [tail, setTail] = useState([]);
  const [pinned, setPinned] = useState([]);
  const [headCursor, setHeadCursor] = useState(null);
  const [tailCursor, setTailCursor] = useState(null);
  const [needsActionCount, setNeedsActionCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [freshIds, setFreshIds] = useState(() => new Set());
  const seen = useRef(new Set());
  const primed = useRef(false);
  const generation = useRef(0);
  const fastRef = useRef(fast);
  fastRef.current = fast;

  const loadHead = useCallback(async () => {
    if (!enabled || !api.getToken()) {
      setLoading(false);
      return;
    }
    const gen = generation.current;
    try {
      const res = await api.activity.feed({ filter, agentId: agentId || undefined, limit: 30 });
      if (gen !== generation.current) return;
      const items = res?.items || [];
      const pins = res?.pinned || [];
      const fresh = new Set();
      for (const item of [...pins, ...items]) {
        if (primed.current && !seen.current.has(item.id)) fresh.add(item.id);
        seen.current.add(item.id);
      }
      primed.current = true;
      if (fresh.size) setFreshIds(fresh);
      setHead(items);
      setPinned(pins);
      setHeadCursor(res?.nextCursor || null);
      setNeedsActionCount(Number(res?.needsActionCount) || 0);
      setError(res?.unavailable ? 'Some activity could not be loaded right now.' : '');
    } catch (e) {
      if (gen === generation.current) setError(e?.message || 'Could not load activity.');
    } finally {
      if (gen === generation.current) setLoading(false);
    }
  }, [filter, agentId, enabled]);

  // Reset when the filter or agent changes.
  useEffect(() => {
    generation.current += 1;
    primed.current = false;
    seen.current = new Set();
    setHead([]);
    setTail([]);
    setPinned([]);
    setHeadCursor(null);
    setTailCursor(null);
    setFreshIds(new Set());
    setLoading(true);
  }, [filter, agentId]);

  useVisiblePoll(loadHead, () => (fastRef.current ? 8000 : 25000), [loadHead]);

  const cursor = tail.length ? tailCursor : headCursor;
  const loadMore = useCallback(async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    const gen = generation.current;
    try {
      const res = await api.activity.feed({ filter, agentId: agentId || undefined, limit: 30, cursor });
      if (gen !== generation.current) return;
      for (const item of res?.items || []) seen.current.add(item.id);
      setTail((current) => [...current, ...(res?.items || [])]);
      setTailCursor(res?.nextCursor || null);
    } catch (e) {
      setError(e?.message || 'Could not load older activity.');
    } finally {
      setLoadingMore(false);
    }
  }, [cursor, loadingMore, filter, agentId]);

  const headIds = new Set(head.map((i) => i.id));
  const items = [...head, ...tail.filter((i) => !headIds.has(i.id))];

  return {
    items,
    pinned,
    needsActionCount,
    loading,
    loadingMore,
    error,
    freshIds,
    hasMore: Boolean(cursor),
    loadMore,
    refresh: loadHead,
  };
}
