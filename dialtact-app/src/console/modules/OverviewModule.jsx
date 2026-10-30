import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, MotionConfig, motion } from 'framer-motion';
import { Activity, Bot, Phone } from 'lucide-react';
import { TactileButton } from '../ui/TactileButton';
import { Tabs } from '../ui/Tabs';
import { SelectFilter } from '../ui/Toolbar';
import { EmptyState } from '../ui/EmptyState';
import { Skeleton } from '../ui/Skeleton';
import { showToast } from '../ui/ToastHost';
import { useWorkspace } from '../context/WorkspaceContext';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../services/api';
import { dayBucket, walletAmounts } from '../../lib/money';
import { useActivityFeed, useLiveRail } from './home/useActivity';
import { FeedItem } from './home/FeedItem';
import { NowRail, SummaryStrip } from './home/NowRail';
import { Insights } from './home/Insights';
import { GuidedStart } from './home/GuidedStart';
import { ConfirmDialog, FollowUpDialog, RecordingDialog } from './home/FeedDialogs';
import { ItemDetailPanel } from './home/ItemDetailPanel';
import { FeedSkeleton, RailSkeleton } from './home/FeedSkeleton';
import { AnimatedCount } from './home/AnimatedCount';
import { collapse, crossfade } from './home/motion';

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'needs_action', label: 'Needs action' },
  { id: 'calls', label: 'Calls' },
  { id: 'leads', label: 'Leads & bookings' },
  { id: 'campaigns', label: 'Campaigns' },
  { id: 'system', label: 'Billing & system' },
];

const HOME_HASH = '#dashboard/overview';

function greeting(date = new Date()) {
  const h = date.getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

function useNow(active) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), active ? 1000 : 30000);
    return () => clearInterval(id);
  }, [active]);
  return now;
}

/** `#dashboard/overview?item=<id>` → the item id, or ''. */
function itemFromHash() {
  if (typeof window === 'undefined') return '';
  const hash = window.location.hash || '';
  if (!hash.startsWith('#dashboard/overview')) return '';
  const query = hash.split('?')[1] || '';
  return (new URLSearchParams(query).get('item') || '').slice(0, 160);
}

function writeItemHash(id) {
  if (typeof window === 'undefined') return;
  const next = id ? `${HOME_HASH}?item=${encodeURIComponent(id)}` : HOME_HASH;
  // replaceState: opening a panel is not a page in the Back history, and it must
  // not fire `hashchange` (the shell would re-route).
  if (window.location.hash !== next) window.history.replaceState(window.history.state, '', next);
}

/**
 * The page's scroll container is the shell's <main>, not the window. Measures it so
 * the right rail can stick below the top bar with its own height, and reports
 * whether the Activity header is stuck to the top.
 */
function useScrollRoot(anchorRef) {
  const [root, setRoot] = useState(null);
  const [box, setBox] = useState({ height: 0, padTop: 0, padBottom: 0 });
  useLayoutEffect(() => {
    const node = anchorRef.current?.closest('main') || null;
    setRoot(node);
    if (!node) return undefined;
    const update = () => {
      const style = getComputedStyle(node);
      const next = { height: node.clientHeight, padTop: parseFloat(style.paddingTop) || 0, padBottom: parseFloat(style.paddingBottom) || 0 };
      setBox((prev) => (prev.height === next.height && prev.padTop === next.padTop && prev.padBottom === next.padBottom ? prev : next));
    };
    update();
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(update) : null;
    ro?.observe(node);
    window.addEventListener('resize', update);
    return () => {
      ro?.disconnect();
      window.removeEventListener('resize', update);
    };
  }, [anchorRef]);
  return { root, ...box };
}

/**
 * Console home (route id `overview`): a live activity feed of what the workspace's
 * AI employees are doing, a "now" rail, and the previous Overview content under
 * Insights. Every feed row opens a detail panel (deep-linkable through
 * `#dashboard/overview?item=<id>`). See DESIGN.md → Home for where each old element lives.
 */
export function OverviewModule({ onNavigate, onOpenCreateAgent, onOpenBuyNumber }) {
  const {
    agents,
    calls,
    leads,
    phoneNumbers,
    wallet,
    setSelectedCallId,
    isLoading,
    openAddFunds,
    requireFunds,
    outboundFromE164,
  } = useWorkspace();
  const { user } = useAuth();
  const displayName = (user?.fullName || user?.name || user?.email?.split('@')[0] || 'there').split(' ')[0];

  const [filter, setFilter] = useState('all');
  const [agentFilter, setAgentFilter] = useState('');
  const live = useLiveRail(true);
  const feed = useActivityFeed({ filter, agentId: agentFilter, fast: live.isLive });
  const now = useNow(live.isLive);

  const [busyAction, setBusyAction] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [confirmError, setConfirmError] = useState('');
  const [followUp, setFollowUp] = useState(null);
  const [recording, setRecording] = useState(null);

  // The item open in the detail panel: its id (from a click or the URL) and the
  // row as it was when opened, so the panel can paint before the detail loads.
  const [selected, setSelected] = useState(() => {
    const id = itemFromHash();
    return id ? { id, item: null } : null;
  });
  const [detailRefresh, setDetailRefresh] = useState(0);

  const agentNames = useMemo(() => Object.fromEntries(agents.map((a) => [a.id, a.name])), [agents]);
  const money = walletAmounts(wallet);
  const isNewTenant = agents.length === 0 || (phoneNumbers.length === 0 && calls.length === 0);

  const pageRef = useRef(null);
  const headerRef = useRef(null);
  const sentinelRef = useRef(null);
  const railRef = useRef(null);
  // Sticky offsets are measured from <main>'s padding edge, so pull the Activity
  // header up by the padding to sit flush under the top bar.
  const { root: scrollRoot, height: rootHeight, padTop, padBottom } = useScrollRoot(pageRef);
  const [headerHeight, setHeaderHeight] = useState(0);
  const [headerStuck, setHeaderStuck] = useState(false);
  const [railEdges, setRailEdges] = useState({ top: true, bottom: true });

  // Follow the URL when someone pastes or follows a link to an item while Home is open.
  useEffect(() => {
    const onHash = () => {
      const id = itemFromHash();
      setSelected((current) => (id ? (current?.id === id ? current : { id, item: null }) : null));
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const openItem = useCallback((item) => {
    if (!item?.id) return;
    setSelected({ id: item.id, item });
    writeItemHash(item.id);
  }, []);
  const closeItem = useCallback(() => {
    setSelected(null);
    writeItemHash('');
  }, []);

  const openCall = (callId) => {
    setSelectedCallId(callId);
    onNavigate('calls');
  };
  const remember = (key, value) => {
    try {
      if (value) sessionStorage.setItem(key, value);
    } catch {
      /* storage unavailable: the page opens on its default view */
    }
  };
  const openLeadsArea = (area, search = '', leadId = '') => {
    remember('dialtact_leads_area', area);
    remember('dialtact_leads_search', search);
    remember('dialtact_leads_open', leadId);
    onNavigate('leads');
  };
  const openCampaign = (campaignId) => {
    remember('dialtact_campaigns_focus', campaignId);
    onNavigate('campaigns');
  };
  const navigate = (tab, options = {}) => {
    if (tab === 'leads' && options.leadName) return openLeadsArea('pipeline', options.leadName);
    return onNavigate(tab, options);
  };

  const afterChange = () => {
    feed.refresh();
    setDetailRefresh((n) => n + 1);
  };

  const runConfirmed = async () => {
    if (!confirm) return;
    setConfirmBusy(true);
    setConfirmError('');
    try {
      const message = await confirm.run();
      setConfirm(null);
      if (message) showToast(message, 'success');
      afterChange();
    } catch (e) {
      setConfirmError(e?.message || 'That did not work. Nothing was changed.');
    } finally {
      setConfirmBusy(false);
    }
  };

  const handleAction = async (item, action) => {
    const who = item.contact?.name || item.contact?.phoneMasked || 'this contact';
    switch (action.kind) {
      case 'open_call':
        return openCall(action.callId);
      case 'open_calls':
        return onNavigate('calls');
      case 'play_recording':
        return setRecording({ callId: action.callId, title: `${item.actor ? `${item.actor} ` : ''}${item.text}` });
      case 'call_back':
        if (requireFunds?.('Add credit to your wallet to call back.')) return undefined;
        setConfirmError('');
        return setConfirm({
          title: 'Call back now?',
          body: `Your agent will call ${who} now from your phone line. The call is charged to your wallet, and DND and calling hours still apply.`,
          confirmLabel: 'Call now',
          run: async () => {
            const res = await api.request('POST', `/api/calls/${encodeURIComponent(action.callId)}/callback`, {
              mode: 'manual',
              dialRequestId: crypto.randomUUID(),
              ...(outboundFromE164 ? { fromE164: outboundFromE164 } : {}),
            });
            if (res?.ok === false) throw new Error(res?.error?.message || res?.error || 'The call could not be placed.');
            return `Calling ${who}. It will appear here when it connects.`;
          },
        });
      case 'call_in_language':
        if (requireFunds?.('Add credit to your wallet to call back.')) return undefined;
        setConfirmError('');
        return setConfirm({
          title: `Call back in ${action.languageLabel}?`,
          body: `${agentNames[action.agentId] || 'Your agent'} will call ${who} now and speak ${action.languageLabel}. The call is charged to your wallet.`,
          confirmLabel: `Call in ${action.languageLabel}`,
          run: async () => {
            const ready = await api.languageSwitch.readiness(action.agentId, action.language);
            if (!ready?.ready) throw new Error(ready?.message || `This agent can't call in ${action.languageLabel} yet.`);
            const res = await api.languageSwitch.call(action.requestId, outboundFromE164 || null);
            if (res?.ok === false) throw new Error(res?.error || 'The call could not be placed. The request is still open.');
            return `Calling ${who} in ${action.languageLabel}.`;
          },
        });
      case 'dismiss_language':
        setBusyAction(`${item.id}:${action.kind}`);
        try {
          await api.languageSwitch.setStatus(action.requestId, 'dismissed');
          showToast('Removed from the callback list.', 'success');
          afterChange();
        } catch (e) {
          showToast(e?.message || 'Could not update this request.', 'error');
        } finally {
          setBusyAction(null);
        }
        return undefined;
      case 'approve_followup':
      case 'reject_followup':
        return setFollowUp({ item, action });
      case 'open_followups':
      case 'open_callbacks':
        return openLeadsArea('followups');
      case 'open_language':
        return openLeadsArea('language');
      case 'open_lead':
        return openLeadsArea('pipeline', action.name || '', action.leadId || '');
      case 'open_campaign':
        return action.campaignId ? openCampaign(action.campaignId) : onNavigate('campaigns');
      case 'top_up':
        return openAddFunds?.(null);
      case 'reconnect_integration':
      case 'open_integrations':
        return onNavigate('integrations');
      case 'open_numbers':
        return onNavigate('phone-numbers');
      case 'open_billing':
        return onNavigate('billing');
      default:
        return undefined;
    }
  };

  // Navigation from the panel leaves Home: close it first so the URL is clean.
  const navigateFromPanel = (item, target) => {
    closeItem();
    switch (target.kind) {
      case 'nav_call':
        return openCall(target.callId);
      case 'nav_lead':
        return openLeadsArea('pipeline', target.name || '', target.leadId);
      case 'nav_campaign':
        return openCampaign(target.campaignId);
      default:
        return handleAction(item, target);
    }
  };
  const actFromPanel = (item, action) => {
    if (['open_call', 'open_calls', 'open_followups', 'open_callbacks', 'open_language', 'open_lead', 'open_campaign',
      'reconnect_integration', 'open_integrations', 'open_numbers', 'open_billing'].includes(action.kind)) closeItem();
    return handleAction(item, action);
  };

  // Group: live calls first ("Now"), then Today / Yesterday / Earlier.
  const groups = useMemo(() => {
    const out = [];
    const byLabel = {};
    for (const item of feed.items) {
      const label = item.type === 'call.live' ? 'Now' : dayBucket(item.at, now);
      if (!byLabel[label]) {
        byLabel[label] = { label, items: [] };
        out.push(byLabel[label]);
      }
      byLabel[label].items.push(item);
    }
    return out;
    // `now` only matters across midnight; regroup at most every 30s.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feed.items, Math.floor(now / 30000)]);

  const showPinned = feed.pinned.length > 0 && filter !== 'needs_action';
  // The order ↑/↓ walks in the detail panel: what is on screen, top to bottom.
  const ordered = useMemo(
    () => [...(showPinned ? feed.pinned : []), ...groups.flatMap((g) => g.items)],
    [showPinned, feed.pinned, groups]
  );
  const selectedIndex = selected ? ordered.findIndex((i) => i.id === selected.id) : -1;
  const listedItem = selectedIndex >= 0 ? ordered[selectedIndex] : selected?.item || null;
  const step = (delta) => {
    if (!ordered.length) return;
    const next = selectedIndex < 0 ? (delta > 0 ? 0 : -1) : selectedIndex + delta;
    if (next < 0 || next >= ordered.length) return;
    const target = ordered[next];
    openItem(target);
    document.querySelector(`[data-item-id="${CSS.escape(target.id)}"]`)?.scrollIntoView({ block: 'nearest' });
  };
  const canPrev = selectedIndex > 0;
  const canNext = ordered.length > 0 && selectedIndex < ordered.length - 1;

  // Sticky Activity header: its height offsets the sticky group headers, and a
  // sentinel just above it says when it is stuck under the top bar.
  useLayoutEffect(() => {
    const node = headerRef.current;
    if (!node) return undefined;
    const update = () => setHeaderHeight(node.offsetHeight);
    update();
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(update) : null;
    ro?.observe(node);
    return () => ro?.disconnect();
  }, [scrollRoot, isLoading, isNewTenant, feed.items.length === 0]);
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !scrollRoot) return undefined;
    // One rect read per scroll event; React skips the render when the value is unchanged.
    const check = () => setHeaderStuck(sentinel.getBoundingClientRect().top < scrollRoot.getBoundingClientRect().top);
    check();
    scrollRoot.addEventListener('scroll', check, { passive: true });
    return () => scrollRoot.removeEventListener('scroll', check);
  }, [scrollRoot, isLoading, isNewTenant, feed.items.length === 0]);

  // The rail fades at whichever edge has more to scroll to (no visible scrollbar).
  const updateRailEdges = useCallback(() => {
    const node = railRef.current;
    if (!node) return;
    const top = node.scrollTop <= 1;
    const bottom = node.scrollTop + node.clientHeight >= node.scrollHeight - 1;
    setRailEdges((prev) => (prev.top === top && prev.bottom === bottom ? prev : { top, bottom }));
  }, []);
  useEffect(() => {
    updateRailEdges();
    const node = railRef.current;
    if (!node || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(updateRailEdges);
    ro.observe(node);
    if (node.firstElementChild) ro.observe(node.firstElementChild);
    return () => ro.disconnect();
  }, [updateRailEdges, rootHeight]);

  const needsCount = feed.needsActionCount;
  const summaryParts = [
    live.calls.length ? `${live.calls.length} on a call now` : `${agents.length} agent${agents.length === 1 ? '' : 's'}`,
    needsCount ? `${needsCount} thing${needsCount === 1 ? '' : 's'} need${needsCount === 1 ? 's' : ''} you` : 'nothing needs you',
    `${money.primary} in wallet`,
  ];

  if (isLoading && !agents.length && !calls.length) {
    return (
      <div className="space-y-5" data-testid="overview-loading" aria-busy="true">
        <div className="space-y-2">
          <Skeleton className="h-7 w-64" />
          <Skeleton className="h-4 w-96 max-w-full" />
        </div>
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px] xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="overflow-hidden rounded-card border border-line bg-surface">
            <div className="space-y-3 border-b border-line px-4 pt-4 pb-3 sm:px-5">
              <Skeleton className="h-5 w-24" />
              <div className="flex gap-1.5">
                {['w-12', 'w-28', 'w-16', 'w-32', 'w-24'].map((w) => <Skeleton key={w} className={`h-8 rounded-pill ${w}`} />)}
              </div>
            </div>
            <FeedSkeleton rows={5} />
          </div>
          <div className="hidden lg:block">
            <RailSkeleton />
          </div>
        </div>
      </div>
    );
  }

  const agentOptions = [{ value: '', label: 'All agents' }, ...agents.map((a) => ({ value: a.id, label: a.name }))];
  const showFeed = !(isNewTenant && feed.items.length === 0 && feed.pinned.filter((p) => p.type !== 'billing.low').length === 0);
  const viewKey = `${filter}|${agentFilter}`;
  const feedState = feed.loading && feed.items.length === 0 ? 'loading' : feed.items.length === 0 ? 'empty' : 'list';
  const stickyTop = { top: `${headerHeight - padTop}px` };
  const railMax = rootHeight ? `${Math.max(320, rootHeight - padTop - padBottom)}px` : 'calc(100dvh - 8rem)';
  const railMask = railEdges.top && railEdges.bottom
    ? undefined
    : `linear-gradient(to bottom, ${railEdges.top ? '#000' : 'transparent'} 0, #000 24px, #000 calc(100% - 32px), ${railEdges.bottom ? '#000' : 'transparent'} 100%)`;

  const renderRow = (item) => (
    <FeedItem
      key={item.id}
      item={item}
      agentName={agentNames[item.agentId]}
      now={now}
      fresh={feed.freshIds.has(item.id)}
      busyAction={busyAction}
      onAction={handleAction}
      onOpen={openItem}
      selected={selected?.id === item.id}
    />
  );

  return (
    <MotionConfig reducedMotion="user">
      <div ref={pageRef} className="space-y-5" data-testid="home-activity">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-heading sm:text-display text-ink">
              {greeting()}, {displayName}
            </h1>
            <p className="mt-1 text-copy text-fg-body" data-testid="home-summary-line">
              {summaryParts.join(' · ')}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 sm:shrink-0">
            <TactileButton
              onClick={onOpenBuyNumber}
              variant="secondary"
              icon={Phone}
              size="sm"
              data-tour="buy-number"
              data-testid="overview-buy-number-btn"
            >
              Buy number
            </TactileButton>
            <TactileButton
              onClick={onOpenCreateAgent}
              variant="primary"
              icon={Bot}
              size="sm"
              data-tour="create-agent"
              data-testid="overview-create-agent-btn"
            >
              Create agent
            </TactileButton>
          </div>
        </header>

        <SummaryStrip
          live={live}
          wallet={wallet}
          needsActionCount={needsCount}
          onShowNeeds={() => setFilter('needs_action')}
          onShowCalls={() => setFilter('calls')}
          onTopUp={() => openAddFunds?.(null)}
        />

        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_320px] xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="min-w-0 space-y-5">
            {isNewTenant && (
              <GuidedStart
                agents={agents}
                phoneNumbers={phoneNumbers}
                calls={calls}
                onOpenCreateAgent={onOpenCreateAgent}
                onOpenBuyNumber={onOpenBuyNumber}
                onNavigate={navigate}
              />
            )}

            {showFeed && (
              <section aria-labelledby="home-feed-title" className="rounded-card border border-line bg-surface shadow-craft-xs" data-testid="home-feed">
                <div ref={sentinelRef} aria-hidden="true" className="h-0" />
                <div
                  ref={headerRef}
                  data-testid="home-feed-header"
                  data-stuck={headerStuck ? 'true' : undefined}
                  style={{ top: `${-padTop}px` }}
                  className={`sticky z-[3] space-y-3 rounded-t-card border-b px-4 pt-4 pb-3 transition-[background-color,box-shadow,border-color] duration-200 ease-out sm:px-5 ${
                    headerStuck ? 'rounded-t-none border-line bg-surface/95 shadow-craft-sm backdrop-blur-md' : 'border-line bg-surface'
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h2 id="home-feed-title" className="flex items-center gap-2 text-title text-ink">
                      <Activity className="h-4 w-4 text-fg-body" aria-hidden="true" />
                      Activity
                      {live.calls.length > 0 && (
                        <span className="inline-flex items-center gap-1 rounded-pill bg-success-soft px-2 py-0.5 text-meta font-medium text-success-fg">
                          <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-success motion-safe:animate-pulse" />
                          <AnimatedCount value={live.calls.length} /> live
                        </span>
                      )}
                    </h2>
                    {agents.length > 1 && (
                      <SelectFilter label="Agent" value={agentFilter} onChange={setAgentFilter} options={agentOptions} />
                    )}
                  </div>
                  <Tabs
                    variant="pills"
                    label="Filter activity"
                    value={filter}
                    onChange={setFilter}
                    items={FILTERS.map((f) => (f.id === 'needs_action' ? { ...f, count: needsCount } : f))}
                  />
                </div>

                {feed.error && (
                  <p role="status" className="mx-4 mt-3 rounded-control bg-warning-soft px-3 py-2 text-ui text-warning-fg sm:mx-5">
                    {feed.error}
                  </p>
                )}

                <AnimatePresence initial={false}>
                  {showPinned && (
                    <motion.div key="pinned" {...collapse} data-testid="home-pinned">
                      <div className="border-b border-line bg-warning-soft/40">
                        <h3
                          className="sticky z-[2] flex items-center gap-1.5 bg-warning-soft/95 px-4 pt-3 pb-1 text-ui font-semibold text-warning-fg backdrop-blur-sm sm:px-5"
                          style={stickyTop}
                        >
                          Needs you
                          <span className="rounded-pill bg-surface/70 px-1.5 font-mono text-meta tabular-nums">
                            <AnimatedCount value={feed.pinned.length} />
                          </span>
                        </h3>
                        <ul className="divide-y divide-line" aria-label="Needs action">
                          <AnimatePresence initial={false}>{feed.pinned.map(renderRow)}</AnimatePresence>
                        </ul>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                <AnimatePresence mode="wait" initial={false}>
                  <motion.div key={`${viewKey}:${feedState}`} {...crossfade}>
                    {feedState === 'loading' ? (
                      <FeedSkeleton rows={4} />
                    ) : feedState === 'empty' ? (
                      <EmptyState
                        compact
                        icon={Activity}
                        title={filter === 'needs_action' ? 'Nothing needs you right now' : 'No activity here yet'}
                        description={
                          filter === 'all'
                            ? 'Calls, bookings, callbacks and account updates will appear here as your agents work.'
                            : 'Try another filter, or check back after your agents take a few calls.'
                        }
                      />
                    ) : (
                      <div aria-live="polite" aria-relevant="additions">
                        {groups.map((group) => (
                          <div key={group.label} data-testid="home-feed-group">
                            <h3
                              className="sticky z-[2] flex items-center gap-2 border-b border-line/60 bg-surface/95 px-4 pt-2.5 pb-1.5 text-meta font-medium text-fg-muted backdrop-blur-sm sm:px-5"
                              style={stickyTop}
                            >
                              {group.label === 'Now' && <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-success motion-safe:animate-pulse" />}
                              {group.label}
                            </h3>
                            <ul className="divide-y divide-line">
                              <AnimatePresence initial={false}>{group.items.map(renderRow)}</AnimatePresence>
                            </ul>
                          </div>
                        ))}
                        {feed.hasMore && (
                          <div className="border-t border-line p-3 text-center">
                            <TactileButton variant="ghost" size="sm" loading={feed.loadingMore} onClick={feed.loadMore}>
                              Show older activity
                            </TactileButton>
                          </div>
                        )}
                      </div>
                    )}
                  </motion.div>
                </AnimatePresence>
              </section>
            )}

            <Insights
              agents={agents}
              calls={calls}
              leads={leads}
              wallet={wallet}
              onNavigate={navigate}
              onInspectCall={openCall}
            />
          </div>

          <aside
            ref={railRef}
            aria-label="Right now"
            tabIndex={0}
            onScroll={updateRailEdges}
            data-testid="home-rail"
            className="no-scrollbar min-w-0 rounded-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent lg:sticky lg:top-0 lg:max-h-[var(--rail-max)] lg:overflow-y-auto lg:overscroll-auto"
            style={{ '--rail-max': railMax, WebkitMaskImage: railMask, maskImage: railMask }}
          >
            <NowRail
              live={live}
              now={now}
              agents={agents}
              wallet={wallet}
              needsActionCount={needsCount}
              onShowNeeds={() => setFilter('needs_action')}
              onOpenCall={openCall}
              onTopUp={() => openAddFunds?.(null)}
              onNavigate={navigate}
              onOpenCreateAgent={onOpenCreateAgent}
              onOpenBuyNumber={onOpenBuyNumber}
            />
          </aside>
        </div>

        <ItemDetailPanel
          itemId={selected?.id || null}
          item={listedItem}
          position={selectedIndex + 1}
          total={ordered.length}
          onPrev={canPrev ? () => step(-1) : undefined}
          onNext={canNext ? () => step(1) : undefined}
          onClose={closeItem}
          onAction={actFromPanel}
          onNavigateTo={navigateFromPanel}
          onOpenItem={openItem}
          busyAction={busyAction}
          agentNames={agentNames}
          now={now}
          suspended={Boolean(confirm || followUp || recording)}
          refreshKey={detailRefresh}
        />

        <ConfirmDialog
          open={Boolean(confirm)}
          title={confirm?.title}
          body={confirm?.body}
          confirmLabel={confirm?.confirmLabel}
          busy={confirmBusy}
          error={confirmError}
          onConfirm={runConfirmed}
          onClose={() => setConfirm(null)}
        />
        <FollowUpDialog
          target={followUp}
          onClose={() => setFollowUp(null)}
          onDone={(message) => {
            setFollowUp(null);
            showToast(message, 'success');
            afterChange();
          }}
        />
        <RecordingDialog callId={recording?.callId} title={recording?.title} onClose={() => setRecording(null)} />
      </div>
    </MotionConfig>
  );
}
