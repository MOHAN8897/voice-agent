import React, { useEffect, useRef, useState } from 'react';
import { Megaphone, Plus, Play, Pause, ShieldAlert } from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { StatusBadge } from '../ui/StatusBadge';
import { TactileButton } from '../ui/TactileButton';
import { Modal } from '../ui/Modal';
import { CampaignCardSkeleton } from '../ui/Skeleton';
import { DncRegistryPanel } from './DncRegistryPanel';
import { CampaignSetup } from './CampaignSetup';
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
  const campaignIds = campaigns.map((campaign) => campaign.id).join(',');
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
    async function refresh() {
      if (inProgress) return;
      inProgress = true;
      const ids = campaignIds.split(',').filter(Boolean);
      const rows = [];
      for (let offset = 0; offset < ids.length && alive; offset += 4) {
        rows.push(...await Promise.allSettled(ids.slice(offset, offset + 4).map(async (id) => [id, await fetchStatistics(id)])));
      }
      if (alive) setAnalytics((previous) => ({ ...previous, ...Object.fromEntries(rows.filter((r) => r.status === 'fulfilled').map((r) => r.value)) }));
      if (alive) setStatisticsError(rows.some((row) => row.status === 'rejected'));
      inProgress = false;
    }
    refresh();
    const timer = setInterval(refresh, 15000);
    return () => { alive = false; clearInterval(timer); };
  }, [campaignIds]);
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
  return (
    <div className="min-w-0 space-y-6">
      <Modal isOpen={Boolean(cancelTarget)} onClose={() => { if (!pending.has(cancelTarget?.id)) setCancelTarget(null); }} title="Cancel campaign?" maxWidth="max-w-lg"><div className="space-y-4"><p className="text-sm text-[#524E5E]">Stop future calls for {cancelTarget?.name}. Linked pending follow-up jobs will be cancelled. Calls already dispatched may continue.</p><TactileButton variant="primary" loading={pending.has(cancelTarget?.id)} disabled={readOnly || pending.has(cancelTarget?.id)} onClick={confirmCancel}>Confirm campaign cancellation</TactileButton></div></Modal>
      <div className="flex flex-wrap gap-4 border-b border-[#E4E2EB]" role="group" aria-label="Campaign sections">
        {[['campaigns', 'Campaigns', Megaphone], ['dnd', 'Do Not Call registry', ShieldAlert]].map(([id, label, Icon]) => <button key={id} type="button" onClick={() => setTab(id)} aria-pressed={tab === id} data-testid={`${id === 'dnd' ? 'dnd-registry' : 'campaigns'}-tab-button`} className={`flex min-h-11 items-center gap-2 border-b-2 px-1 pb-3 text-sm font-semibold ${tab === id ? 'border-[#FF5C35] text-[#B9381B]' : 'border-transparent text-[#524E5E]'}`}><Icon className="h-4 w-4" />{label}</button>)}
      </div>
      {tab === 'dnd' ? <DncRegistryPanel readOnly={readOnly} /> : <>
        {statisticsError && <p role="status" className="text-sm text-amber-800">Some campaign statistics could not refresh. Retrying automatically; the last available values are shown.</p>}
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center"><div><h2 className="text-xl font-bold tracking-tight">Outbound campaigns</h2><p className="mt-1 text-sm text-[#645D73]">Prepare contacts, review your settings, and launch from one page.</p></div><TactileButton onClick={() => setOpen(true)} icon={Plus} variant="primary" disabled={readOnly}>New campaign</TactileButton></div>
        {isLoading && !campaigns.length ? <CampaignCardSkeleton count={3} /> : !campaigns.length ? <SolidCard className="space-y-3 py-12 text-center"><Megaphone className="mx-auto h-8 w-8 text-[#6344E7]" /><h3 className="font-semibold">Your first campaign starts here</h3><p className="mx-auto max-w-md text-sm text-[#645D73]">Upload a spreadsheet, paste contacts, or use a saved list. Review everything before any calls are placed.</p><TactileButton onClick={() => setOpen(true)} variant="secondary" disabled={readOnly}>Create first campaign</TactileButton></SolidCard> : <div className="space-y-4">{campaigns.map((campaign) => {
          const stats = analytics[campaign.id];
          const groups = stats?.dispositions || {};
          const total = stats ? Object.values(groups).reduce((sum, n) => sum + n, 0) : campaign.totalContacts || 0;
          const connected = Math.min(total, stats?.connects ?? campaign.connectedCalls ?? 0);
          const active = (groups.dialing || 0) + (groups.placed || 0) + (groups.connected || 0);
          const review = (groups.requires_review || 0) + (groups.needs_review || 0) + (groups.blocked || 0);
          const agent = agents.find((item) => item.id === campaign.agentId);
          return <SolidCard key={campaign.id} className="min-w-0 space-y-4">
            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="min-w-0 break-words text-base font-bold">{campaign.name}</h3><StatusBadge status={campaign.status} size="xs" /></div><p className="mt-1 break-words text-sm text-[#645D73]">{agent?.name || campaign.agentName || 'Agent'}{campaign.description ? ` · ${campaign.description}` : ''}</p></div>{['draft', 'running', 'paused', 'requires_review'].includes(campaign.status) && <TactileButton disabled={readOnly || pending.has(campaign.id)} onClick={() => changeStatus(campaign)} icon={campaign.status === 'running' ? Pause : Play} variant="secondary">{pending.has(campaign.id) ? 'Updating…' : campaign.status === 'running' ? 'Pause campaign' : campaign.status === 'draft' ? 'Start campaign' : campaign.status === 'requires_review' ? 'Resume reviewed campaign' : 'Resume campaign'}</TactileButton>}</div>
            {['draft', 'running', 'paused', 'requires_review'].includes(campaign.status) && <div className="flex justify-end"><TactileButton variant="ghost" disabled={readOnly || pending.has(campaign.id)} onClick={() => setCancelTarget(campaign)}>Cancel campaign</TactileButton></div>}
            <dl className="grid grid-cols-2 gap-4 rounded-xl border border-[#E4E2EB] bg-[#FAF9FD] p-4 sm:grid-cols-4">{[['Contacts', total], ['Connected', connected], ['Active calls', active], ['Needs review', review]].map(([label, value]) => <div key={label}><dt className="text-xs text-[#645D73]">{label}</dt><dd className="mt-1 text-lg font-semibold tabular-nums">{Number(value).toLocaleString()}</dd></div>)}</dl>
            {review > 0 && <p role="status" className="text-sm text-amber-800">{review} contact{review === 1 ? '' : 's'} need review. Check call history and account settings before creating another attempt.</p>}
            <p className="text-xs text-[#645D73]">Up to {campaign.concurrencyLimit || campaign.concurrency || 1} concurrent calls · {stats ? `${stats.attempts || 0} dial attempts` : 'Loading call statistics…'}</p>
          </SolidCard>;
        })}</div>}
        <Modal isOpen={open} onClose={() => { if (!setupBusy) setOpen(false); }} title="New outbound campaign" subtitle="Set up your contacts and review the campaign on one page." maxWidth="max-w-6xl">
          {open && <CampaignSetup onBusyChange={setSetupBusy} onComplete={() => setOpen(false)} />}
        </Modal>
      </>}
    </div>
  );
}
