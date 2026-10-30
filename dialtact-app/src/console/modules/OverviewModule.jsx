import React, { useEffect, useMemo, useState } from 'react';
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

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'needs_action', label: 'Needs action' },
  { id: 'calls', label: 'Calls' },
  { id: 'leads', label: 'Leads & bookings' },
  { id: 'campaigns', label: 'Campaigns' },
  { id: 'system', label: 'Billing & system' },
];

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

/**
 * Console home (route id `overview`): a live activity feed of what the workspace's
 * AI employees are doing, a "now" rail, and the previous Overview content under
 * Insights. See DESIGN.md → Home for where each old element lives.
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

  const agentNames = useMemo(() => Object.fromEntries(agents.map((a) => [a.id, a.name])), [agents]);
  const money = walletAmounts(wallet);
  const isNewTenant = agents.length === 0 || (phoneNumbers.length === 0 && calls.length === 0);

  const openCall = (callId) => {
    setSelectedCallId(callId);
    onNavigate('calls');
  };
  const openLeadsArea = (area, search = '') => {
    try {
      if (area) sessionStorage.setItem('dialtact_leads_area', area);
      if (search) sessionStorage.setItem('dialtact_leads_search', search);
    } catch {
      /* storage unavailable: Leads opens on its default view */
    }
    onNavigate('leads');
  };
  const navigate = (tab, options = {}) => {
    if (tab === 'leads' && options.leadName) return openLeadsArea('pipeline', options.leadName);
    return onNavigate(tab, options);
  };

  const runConfirmed = async () => {
    if (!confirm) return;
    setConfirmBusy(true);
    setConfirmError('');
    try {
      const message = await confirm.run();
      setConfirm(null);
      if (message) showToast(message, 'success');
      feed.refresh();
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
          feed.refresh();
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
        return openLeadsArea('pipeline', action.name || '');
      case 'open_campaign':
        return onNavigate('campaigns');
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

  const needsCount = feed.needsActionCount;
  const summaryParts = [
    live.calls.length ? `${live.calls.length} on a call now` : `${agents.length} agent${agents.length === 1 ? '' : 's'}`,
    needsCount ? `${needsCount} thing${needsCount === 1 ? '' : 's'} need${needsCount === 1 ? 's' : ''} you` : 'nothing needs you',
    `${money.primary} in wallet`,
  ];

  if (isLoading && !agents.length && !calls.length) {
    return (
      <div className="space-y-6" data-testid="overview-loading" aria-busy="true">
        <div className="space-y-2">
          <Skeleton className="h-7 w-64" />
          <Skeleton className="h-4 w-96 max-w-full" />
        </div>
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="space-y-3 rounded-card border border-line bg-surface p-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex gap-3">
                <Skeleton className="h-8 w-8 rounded-full" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-3/4" />
                  <Skeleton className="h-3 w-1/3" />
                </div>
              </div>
            ))}
          </div>
          <div className="hidden space-y-4 lg:block">
            <Skeleton className="h-32 w-full rounded-card" />
            <Skeleton className="h-40 w-full rounded-card" />
          </div>
        </div>
      </div>
    );
  }

  const agentOptions = [{ value: '', label: 'All agents' }, ...agents.map((a) => ({ value: a.id, label: a.name }))];
  const showFeed = !(isNewTenant && feed.items.length === 0 && feed.pinned.filter((p) => p.type !== 'billing.low').length === 0);

  return (
    <div className="space-y-5" data-testid="home-activity">
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
            <section aria-labelledby="home-feed-title" className="rounded-card border border-line bg-surface shadow-craft-xs">
              <div className="space-y-3 border-b border-line px-4 pt-4 pb-3 sm:px-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 id="home-feed-title" className="flex items-center gap-2 text-title text-ink">
                    <Activity className="h-4 w-4 text-fg-body" aria-hidden="true" />
                    Activity
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

              {feed.pinned.length > 0 && filter !== 'needs_action' && (
                <div className="border-b border-line bg-warning-soft/40" data-testid="home-pinned">
                  <h3 className="px-4 pt-3 text-ui font-semibold text-warning-fg sm:px-5">Needs you</h3>
                  <ul className="divide-y divide-line" aria-label="Needs action">
                    {feed.pinned.map((item) => (
                      <FeedItem
                        key={item.id}
                        item={item}
                        agentName={agentNames[item.agentId]}
                        now={now}
                        fresh={feed.freshIds.has(item.id)}
                        busyAction={busyAction}
                        onAction={handleAction}
                      />
                    ))}
                  </ul>
                </div>
              )}

              {feed.loading && feed.items.length === 0 ? (
                <div className="space-y-4 p-5" aria-busy="true">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className="flex gap-3">
                      <Skeleton className="h-8 w-8 rounded-full" />
                      <div className="flex-1 space-y-2">
                        <Skeleton className="h-4 w-2/3" />
                        <Skeleton className="h-3 w-1/4" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : feed.items.length === 0 ? (
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
                    <div key={group.label}>
                      <h3 className="sticky top-0 z-[1] bg-surface/95 px-4 pt-3 pb-1 text-meta font-medium text-fg-muted backdrop-blur-sm sm:px-5">
                        {group.label}
                      </h3>
                      <ul className="divide-y divide-line">
                        {group.items.map((item) => (
                          <FeedItem
                            key={item.id}
                            item={item}
                            agentName={agentNames[item.agentId]}
                            now={now}
                            fresh={feed.freshIds.has(item.id)}
                            busyAction={busyAction}
                            onAction={handleAction}
                          />
                        ))}
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

        <aside aria-label="Right now" className="min-w-0 lg:sticky lg:top-4">
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
          feed.refresh();
        }}
      />
      <RecordingDialog callId={recording?.callId} title={recording?.title} onClose={() => setRecording(null)} />
    </div>
  );
}
