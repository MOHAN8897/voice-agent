import React, { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Megaphone, Plus, Play, Pause, ShieldAlert } from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { StatusBadge } from '../ui/StatusBadge';
import { TactileButton } from '../ui/TactileButton';
import { Modal } from '../ui/Modal';
import { PageHeader } from '../ui/PageHeader';
import { EmptyState } from '../ui/EmptyState';
import { Avatar } from '../ui/Avatar';
import { CampaignCardSkeleton } from '../ui/Skeleton';
import { DncRegistryPanel } from './DncRegistryPanel';
import { CampaignSetup } from './CampaignSetup';
import { IntegrationSelectionSummary } from '../ui/CallIntegrationPicker';
import { useWorkspace } from '../context/WorkspaceContext';
import { showToast } from '../ui/ToastHost';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../services/api';

export function CampaignsModule() {
  const { user } = useAuth();
  const readOnly = user?.role === 'customer_viewer' || user?.role === 'viewer';
  const { campaigns, toggleCampaignStatus, startCampaign, fetchCampaignAnalytics, agents, isLoading, loadWorkspaceData } = useWorkspace();
  const [open, setOpen] = useState(false);
  const [analytics, setAnalytics] = useState({});
  const [statisticsError, setStatisticsError] = useState(false);
  const [tab, setTab] = useState('campaigns');
  const [pending, setPending] = useState(new Set());
  const [setupBusy, setSetupBusy] = useState(false);
  const [cancelTarget, setCancelTarget] = useState(null);
  const actions = useRef(new Set());
  const statisticsRequests = useRef(new Map());
  const fetcher = useRef(fetchCampaignAnalytics);
  fetcher.current = fetchCampaignAnalytics;
  // The campaign list already carries each campaign's analytics. Seed from it and
  // poll only while a campaign can still change (running/paused) and the tab is visible.
  useEffect(() => {
    const seeded = Object.fromEntries(campaigns.filter((c) => c.analytics).map((c) => [c.id, c.analytics]));
    if (Object.keys(seeded).length) setAnalytics((previous) => ({ ...previous, ...seeded }));
  }, [campaigns]);
  const campaignIds = campaigns.map((campaign) => campaign.id).join(',');
  const missingIds = campaigns.filter((campaign) => !campaign.analytics).map((campaign) => campaign.id).join(',');
  const liveIds = campaigns.filter((campaign) => ['running', 'paused'].includes(campaign.status)).map((campaign) => campaign.id).join(',');
  useEffect(() => {
    let alive = true;
    let inProgress = false;
    async function fetchStatistics(id) {
      const active = statisticsRequests.current;
      if (active.has(id)) return active.get(id);
      if (active.size >= 4) {
        await Promise.race([...active.values()].map((request) => request.catch(() => undefined)));
        if (!alive) throw new Error('Statistics view closed');
        return fetchStatistics(id);
      }
      const request = fetcher.current(id);
      active.set(id, request);
      try { return await request; }
      finally { if (active.get(id) === request) active.delete(id); }
    }
    async function refreshEach(ids) {
      const rows = [];
      for (let offset = 0; offset < ids.length && alive; offset += 4) {
        rows.push(...await Promise.allSettled(ids.slice(offset, offset + 4).map(async (id) => [id, await fetchStatistics(id)])));
      }
      if (alive) setAnalytics((previous) => ({ ...previous, ...Object.fromEntries(rows.filter((r) => r.status === 'fulfilled').map((r) => r.value)) }));
      if (alive) setStatisticsError(rows.some((row) => row.status === 'rejected'));
    }
    async function refresh() {
      if (inProgress || !alive) return;
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
      inProgress = true;
      try {
        const live = new Set(liveIds.split(',').filter(Boolean));
        if (!live.size) return;
        // One grouped request refreshes every campaign on the page.
        const rows = await api.campaigns.list();
        const fresh = Object.fromEntries(rows.filter((row) => row.analytics && live.has(row.id)).map((row) => [row.id, row.analytics]));
        if (alive) setAnalytics((previous) => ({ ...previous, ...fresh }));
        const stale = [...live].filter((id) => !fresh[id]);
        if (stale.length) await refreshEach(stale);
        else if (alive) setStatisticsError(false);
      } catch {
        if (alive) setStatisticsError(true);
      } finally {
        inProgress = false;
      }
    }
    // Rows from an older API without embedded analytics are fetched once.
    const missing = missingIds.split(',').filter(Boolean);
    if (missing.length) refreshEach(missing).catch(() => undefined);
    const timer = liveIds ? setInterval(refresh, 15000) : null;
    const onVisible = () => { if (document.visibilityState === 'visible') refresh(); };
    if (liveIds) document.addEventListener('visibilitychange', onVisible);
    return () => {
      alive = false;
      if (timer) clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [campaignIds, missingIds, liveIds]);
  async function changeStatus(campaign) {
    if (readOnly) return;
    if (actions.current.has(campaign.id)) return;
    actions.current.add(campaign.id); setPending(new Set(actions.current));
    try {
      if (campaign.status === 'draft') await startCampaign(campaign.id);
      else await toggleCampaignStatus(campaign.id);
    } catch (error) { showToast(error.message || 'Could not update campaign', 'error'); }
    finally { actions.current.delete(campaign.id); setPending(new Set(actions.current)); }
  }
  async function confirmCancel() {
    const campaign = cancelTarget;
    if (!campaign || readOnly || actions.current.has(campaign.id)) return;
    actions.current.add(campaign.id); setPending(new Set(actions.current));
    try {
      await api.campaigns.cancel(campaign.id);
      setCancelTarget(null);
      showToast('Campaign cancelled. No new work will start; calls already dispatched may continue.', 'success');
      await loadWorkspaceData();
    } catch (error) { showToast(error.message || 'Could not cancel or refresh the campaign. Refresh to check its current status.', 'error'); }
    finally { actions.current.delete(campaign.id); setPending(new Set(actions.current)); }
  }
  const sectionTabs = [['campaigns', 'Campaigns', Megaphone], ['dnd', 'Do not call registry', ShieldAlert]];
  return (
    <div className="min-w-0 space-y-6">
      <Modal isOpen={Boolean(cancelTarget)} onClose={() => { if (!pending.has(cancelTarget?.id)) setCancelTarget(null); }} title="Cancel campaign?" maxWidth="max-w-lg">
        <div className="space-y-4">
          <p className="text-copy text-fg-body">No new calls will start for {cancelTarget?.name}, and its pending follow-ups are cancelled. Calls already ringing may finish.</p>
          <TactileButton variant="danger" loading={pending.has(cancelTarget?.id)} disabled={readOnly || pending.has(cancelTarget?.id)} onClick={confirmCancel}>Confirm campaign cancellation</TactileButton>
        </div>
      </Modal>
      <PageHeader
        title="Campaigns"
        description="Call a list of contacts with one of your agents. You check everything before any calls are placed."
        actions={tab === 'campaigns' ? <TactileButton onClick={() => setOpen(true)} icon={Plus} variant="primary" disabled={readOnly}>New campaign</TactileButton> : null}
      />
      <div className="inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-control border border-line bg-surface-subtle p-0.5 no-scrollbar" role="group" aria-label="Campaign sections">
        {sectionTabs.map(([id, label, Icon]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            aria-pressed={tab === id}
            data-testid={`${id === 'dnd' ? 'dnd-registry' : 'campaigns'}-tab-button`}
            className={`inline-flex min-h-[40px] sm:min-h-[32px] shrink-0 items-center gap-1.5 rounded-[8px] px-3 py-1.5 text-ui font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${tab === id ? 'bg-surface text-ink shadow-craft-xs' : 'text-fg-body hover:text-ink'}`}
          >
            <Icon className="h-4 w-4" aria-hidden="true" />{label}
          </button>
        ))}
      </div>
      {tab === 'dnd' ? <DncRegistryPanel readOnly={readOnly} /> : <>
        {statisticsError && <p role="status" className="rounded-control border border-warning-line bg-warning-soft px-3 py-2 text-ui text-warning-fg">Some campaign numbers could not refresh. We keep retrying and show the last numbers we have.</p>}
        {isLoading && !campaigns.length ? <CampaignCardSkeleton count={3} /> : !campaigns.length ? (
          <SolidCard padding="p-0">
            <EmptyState
              icon={Megaphone}
              title="No campaigns yet"
              description="Upload a spreadsheet, paste contacts or use a saved list. You review everything before any calls are placed."
              action={<TactileButton onClick={() => setOpen(true)} variant="secondary" disabled={readOnly}>Create first campaign</TactileButton>}
            />
          </SolidCard>
        ) : <div className="space-y-4">{campaigns.map((campaign) => {
          const stats = analytics[campaign.id];
          const groups = stats?.dispositions || {};
          const total = stats ? Object.values(groups).reduce((sum, n) => sum + n, 0) : campaign.totalContacts || 0;
          const connected = Math.min(total, stats?.connects ?? campaign.connectedCalls ?? 0);
          const active = (groups.dialing || 0) + (groups.placed || 0) + (groups.connected || 0);
          const review = (groups.requires_review || 0) + (groups.needs_review || 0) + (groups.blocked || 0);
          const agent = agents.find((item) => item.id === campaign.agentId);
          const agentLabel = agent?.name || campaign.agentName || 'Agent';
          const controllable = ['draft', 'running', 'paused', 'requires_review'].includes(campaign.status);
          return <SolidCard key={campaign.id} className="min-w-0 space-y-4">
            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
              <div className="flex min-w-0 items-start gap-3">
                <Avatar name={agentLabel} size="md" live={campaign.status === 'running' && active > 0} title={agentLabel} />
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2"><h3 className="min-w-0 break-words text-title text-ink">{campaign.name}</h3><StatusBadge status={campaign.status} size="xs" /></div>
                  <p className="mt-0.5 break-words text-ui text-fg-muted">Called by {agentLabel}{campaign.description ? ` · ${campaign.description}` : ''}</p>
                </div>
              </div>
              {controllable && (
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  <TactileButton disabled={readOnly || pending.has(campaign.id)} onClick={() => changeStatus(campaign)} icon={campaign.status === 'running' ? Pause : Play} variant="secondary" size="sm">{pending.has(campaign.id) ? 'Updating…' : campaign.status === 'running' ? 'Pause campaign' : campaign.status === 'draft' ? 'Start campaign' : campaign.status === 'requires_review' ? 'Resume reviewed campaign' : 'Resume campaign'}</TactileButton>
                  <TactileButton variant="ghost" size="sm" disabled={readOnly || pending.has(campaign.id)} onClick={() => setCancelTarget(campaign)}>Cancel campaign</TactileButton>
                </div>
              )}
            </div>
            <dl className="grid grid-cols-2 gap-4 rounded-control border border-line bg-canvas p-4 sm:grid-cols-4">{[['Contacts', total], ['Connected', connected], ['On a call now', active], ['Needs review', review]].map(([label, value]) => <div key={label} className="min-w-0"><dt className="text-meta text-fg-muted">{label}</dt><dd className={`mt-1 font-mono text-heading tabular-nums ${label === 'Needs review' && value > 0 ? 'text-warning-fg' : 'text-ink'}`}>{Number(value).toLocaleString('en-IN')}</dd></div>)}</dl>
            {review > 0 && <p role="status" className="flex items-start gap-2 rounded-control border border-warning-line bg-warning-soft px-3 py-2 text-ui text-warning-fg"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" /><span>{review} contact{review === 1 ? ' needs' : 's need'} review. Check call history and your account before trying again.</span></p>}
            <div className="rounded-control border border-line p-3" data-testid="campaign-integrations"><p className="mb-1.5 text-meta font-medium text-fg-body">Integrations each call may use</p><IntegrationSelectionSummary selection={campaign.integrations} emptyText="None chosen: every call uses the agent’s saved integration settings." /></div>
            <p className="text-meta text-fg-muted">Up to <span className="font-mono tabular-nums">{campaign.concurrencyLimit || campaign.concurrency || 1}</span> calls at once · {stats ? <><span className="font-mono tabular-nums">{(stats.attempts || 0).toLocaleString('en-IN')}</span> calls attempted</> : 'Loading call numbers…'}</p>
          </SolidCard>;
        })}</div>}
        <Modal isOpen={open} onClose={() => { if (!setupBusy) setOpen(false); }} title="New campaign" subtitle="Add your contacts and review the campaign on one page." maxWidth="max-w-6xl">
          {open && <CampaignSetup onBusyChange={setSetupBusy} onComplete={() => setOpen(false)} />}
        </Modal>
      </>}
    </div>
  );
}
