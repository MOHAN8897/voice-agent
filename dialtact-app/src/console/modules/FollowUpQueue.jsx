import React, { useCallback, useEffect, useState } from 'react';
import { CalendarClock, PhoneCall, PhoneMissed, RefreshCw } from 'lucide-react';
import { api } from '../../services/api';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
import { Modal } from '../ui/Modal';
import { Avatar } from '../ui/Avatar';
import { Badge, StatusBadge } from '../ui/StatusBadge';
import { EmptyState } from '../ui/EmptyState';
import { NeedsYouItem } from './NeedsYouItem';
import { humanizeToken, statusWord } from '../../lib/internalLabels';
import { showToast } from '../ui/ToastHost';
import { CampaignSetup } from './CampaignSetup';
import { useWorkspace } from '../context/WorkspaceContext';

const field = 'mt-1 block min-h-11 w-full min-w-0 rounded-control border border-line bg-surface px-3 text-base sm:text-ui text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15 disabled:opacity-50';
const STATUS_LABEL = { active: 'Active', planning: 'Working out the time' };
const statusLabel = (value) => STATUS_LABEL[value] || statusWord(value).label;
const KIND_LABEL = { callback: 'Callback request', missed: 'Missed call' };
const kindLabel = (value) => KIND_LABEL[value] || humanizeToken(value);
/** Why a follow-up is in its current state, in plain words. */
const REASON_LABEL = {
  resolve_requested_time: 'Working out the time the caller asked for',
  interrupted_request_review: 'Call ended before the request was confirmed',
  approval_required: 'Waiting for your approval',
  automation_disabled: 'Follow-ups were turned off',
  newer_callback_request: 'Replaced by a newer request',
  do_not_call: 'Number is on the do-not-call list',
  worker_restarted_review_dispatch: 'Check whether this call went out',
  request_expired: 'Request expired',
  request_closed: 'Request closed',
  authorization_no_longer_valid: 'Your approval needs renewing',
  no_calling_window_before_expiry: 'No calling hours left before it expires',
  carrier_result_missing: 'Call result unknown',
  carrier_result_pending: 'Waiting for the call result',
  retry_unanswered: 'Retrying after no answer',
  lead_converted: 'Lead already converted',
};
const reasonLabel = (value) => REASON_LABEL[value] || humanizeToken(value);
const instant = (value, zone) => value ? new Date(value).toLocaleString('en-IN', { timeZone: zone || undefined, dateStyle: 'medium', timeStyle: 'short' }) : 'Choose a time';

export function FollowUpQueue({ agentId, readOnly = false }) {
  const { agents } = useWorkspace();
  const [importOpen, setImportOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState('');
  const [importConfig, setImportConfig] = useState({ agentId: agentId || agents[0]?.id || '', kind: 'missed', days: 7 });
  const [campaignOpen, setCampaignOpen] = useState(false);
  const [campaignBusy, setCampaignBusy] = useState(false);
  const [status, setStatus] = useState('active');
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState({ jobs: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [editing, setEditing] = useState(null);
  const [due, setDue] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [editError, setEditError] = useState('');
  const agentName = (id) => (id ? agents.find((agent) => String(agent.id) === String(id))?.name || '' : '');
  useEffect(() => {
    let active = true;
    setLoading(true); setError(''); setData({ jobs: [], total: 0 });
    api.followups.list({ agentId, status, offset, limit: 25 }).then((res) => { if (active) setData(res); })
      .catch((e) => { if (active) setError(e.message || 'Could not load follow-ups.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [agentId, status, offset, revision]);
  const refresh = useCallback(() => setRevision((v) => v + 1), []);
  async function importReview(event) {
    event.preventDefault();
    const importAgent = agentId || importConfig.agentId;
    if (importing || readOnly || !importAgent) return;
    setImporting(true); setImportError('');
    try {
      const result = await api.followups.importReview(importAgent, importConfig.kind, Number(importConfig.days));
      showToast(`${result.imported} earlier requests imported from the last ${result.days} days for review. No automatic calls were enabled.`, 'success');
      setImportOpen(false); refresh();
    } catch (error) { setImportError(error.message || 'Could not import earlier calls.'); }
    finally { setImporting(false); }
  }
  const open = (row, action) => { setEditing({ row, action }); setDue(''); setConfirmed(false); setEditError(''); };
  const save = async (e) => {
    e.preventDefault(); if (busy || !confirmed || readOnly) return;
    setBusy(true); setEditError('');
    try {
      // datetime-local uses the browser timezone; the UI names this explicitly.
      const dueAt = editing.action === 'schedule' ? new Date(due).toISOString() : null;
      await api.followups.update(editing.row.id, { action: editing.action, dueAt, expectedUpdatedAt: editing.row.updatedAt, confirm: true });
      showToast(editing.action === 'cancel' ? 'Pending follow-up cancelled.' : 'Follow-up saved. DND, calling hours and wallet checks still apply.', 'success');
      setEditing(null); refresh();
    } catch (e) { setEditError(e.message || 'Could not update follow-up.'); }
    finally { setBusy(false); }
  };
  return <div className="min-w-0 space-y-4" data-testid="followup-queue">
    <Modal isOpen={importOpen} onClose={() => { if (!importing) setImportOpen(false); }} title="Import earlier calls for review" maxWidth="max-w-lg">
      <form onSubmit={importReview} className="space-y-4">
        <p className="text-copy text-fg-body">Add older missed calls or saved callback requests to the review list. This does not authorize automatic calls. The agent’s permission, expiry and DND rules still apply.</p>
        {!agentId && <label className="block text-ui font-medium text-ink">Agent for review import<select required value={importConfig.agentId} onChange={(event) => setImportConfig((value) => ({ ...value, agentId: event.target.value }))} className={field}>{agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></label>}
        <label className="block text-ui font-medium text-ink">Earlier call type<select value={importConfig.kind} onChange={(event) => setImportConfig((value) => ({ ...value, kind: event.target.value }))} className={field}><option value="missed">Missed inbound calls</option><option value="callback">Saved callback requests</option></select></label>
        <label className="block text-ui font-medium text-ink">Look back (days)<input type="number" required min="1" max="30" value={importConfig.days} onChange={(event) => setImportConfig((value) => ({ ...value, days: event.target.value }))} className={`${field} font-mono tabular-nums`} /></label>
        <p className="text-meta text-fg-muted">The agent’s expiry setting can shorten this period. Each import brings in one batch; repeat it to bring in more.</p>
        {importError && <p role="alert" className="text-ui text-danger-fg">{importError}</p>}
        <TactileButton type="submit" variant="primary" loading={importing} disabled={importing || readOnly || !(agentId || importConfig.agentId)}>Import for review</TactileButton>
      </form>
    </Modal>
    <SolidCard padding="p-0" className="min-w-0 overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-3 px-4 pt-4 sm:px-5 sm:pt-5">
        <div className="flex min-w-0 max-w-2xl gap-3">
          <Avatar icon={CalendarClock} tone="accent" size="sm" />
          <div className="min-w-0">
            <h2 className="text-title text-ink">Scheduled follow-ups</h2>
            <p className="mt-0.5 text-ui text-fg-muted">Callback requests and missed calls wait here in one list. Check any unclear times. Whether follow-ups run on their own is set in each agent’s settings.</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <TactileButton variant="secondary" size="sm" icon={RefreshCw} onClick={refresh} disabled={loading}>Refresh follow-ups</TactileButton>
          {!readOnly && <TactileButton variant="secondary" size="sm" onClick={() => { setImportError(''); setImportOpen(true); }}>Import earlier calls for review</TactileButton>}
          {!readOnly && <TactileButton variant="primary" size="sm" onClick={() => setCampaignOpen(true)}>Create follow-up campaign</TactileButton>}
        </div>
      </div>
      <div className="px-4 pt-4 sm:px-5">
        <label className="block max-w-xs text-meta font-medium text-fg-body">Follow-up status<select aria-label="Follow-up status" className={field} value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>{['active', 'needs_review', 'scheduled', 'completed', 'suppressed', 'cancelled', 'expired'].map((value) => <option key={value} value={value}>{statusLabel(value)}</option>)}</select></label>
      </div>
      {error && <p role="alert" className="mx-4 mt-4 rounded-control border border-warning-line bg-warning-soft p-3 text-ui text-warning-fg sm:mx-5">{error}</p>}
      {loading ? <p role="status" className="p-6 text-center text-ui text-fg-muted">Loading follow-ups…</p> : !error && <>
        {data.jobs.length === 0 ? (
          <EmptyState compact icon={CalendarClock} title={`No ${statusLabel(status).toLowerCase()} follow-ups`} description="Callback requests and missed calls appear here once an agent schedules them." />
        ) : (
          <ul className="mt-4 divide-y divide-line border-t border-line">{data.jobs.map((row) => {
            const editable = ['planning', 'needs_review', 'scheduled'].includes(row.status);
            const review = row.status === 'needs_review' || row.status === 'planning';
            const agent = agentName(row.agentId);
            return (
              <NeedsYouItem
                key={row.id}
                agentName={agent}
                icon={row.kind === 'missed' ? PhoneMissed : PhoneCall}
                tone={review ? 'warning' : 'info'}
                needsYou={review}
                at={row.createdAt || row.updatedAt || null}
                actor={<span className="font-mono tabular-nums">{row.phone || 'Number unavailable'}</span>}
                text={row.kind === 'missed' ? 'called and was missed' : row.kind === 'callback' ? 'asked for a call back' : `needs a follow-up (${humanizeToken(row.kind).toLowerCase()})`}
                detail={<>Due {instant(row.dueAt, row.timezone)}{row.timezone && <span className="text-meta"> ({row.timezone})</span>}</>}
                meta={<>
                  {agent && <span>· {agent}</span>}
                  <span>· <span className="font-mono tabular-nums">{row.attempts}</span> {row.attempts === 1 ? 'attempt' : 'attempts'}</span>
                  <span>· expires {instant(row.expiresAt, row.timezone)}</span>
                </>}
                badges={<>
                  <Badge tone="neutral" size="xs">{kindLabel(row.kind)}</Badge>
                  <StatusBadge status={row.status} size="xs" />
                  {row.reason && <span>{reasonLabel(row.reason)}</span>}
                </>}
                actions={editable ? <>
                  <TactileButton size="xs" variant={review ? 'primary' : 'secondary'} className="min-h-[36px] sm:min-h-0" disabled={readOnly} onClick={() => open(row, 'schedule')}>Review time</TactileButton>
                  <TactileButton size="xs" variant="secondary" className="min-h-[36px] sm:min-h-0" disabled={readOnly} onClick={() => open(row, 'cancel')}>Cancel follow-up</TactileButton>
                </> : null}
              >
                {row.requestedWhen && <p className="mt-0.5 max-w-xl break-words text-ui text-fg-body">Caller requested: {row.requestedWhen}</p>}
                {row.campaignId && <a href="#dashboard/campaigns" className="mt-1 inline-block text-ui font-medium text-accent-fg hover:text-accent hover:underline">Managed by {row.campaignName || 'a campaign'} · resume it after reviewing this follow-up</a>}
              </NeedsYouItem>
            );
          })}</ul>
        )}
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-4 py-3 text-meta text-fg-muted sm:px-5"><span><span className="font-mono tabular-nums">{data.total}</span> matching follow-ups</span><div className="flex gap-2"><TactileButton size="sm" variant="secondary" disabled={!offset || loading} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous follow-ups</TactileButton><TactileButton size="sm" variant="secondary" disabled={offset + 25 >= data.total || loading} onClick={() => setOffset(offset + 25)}>Next follow-ups</TactileButton></div></div>
      </>}
    </SolidCard>
    <Modal isOpen={Boolean(editing)} onClose={() => { if (!busy) setEditing(null); }} title={editing?.action === 'cancel' ? 'Cancel this follow-up?' : 'Review callback time'} maxWidth="max-w-lg">
      <form onSubmit={save} className="space-y-4">
        {editing?.action === 'schedule' && <label className="block text-ui font-medium text-ink">Time in your browser timezone ({Intl.DateTimeFormat().resolvedOptions().timeZone})<input aria-label="Follow-up date and time" type="datetime-local" required value={due} onChange={(e) => setDue(e.target.value)} className={field} /></label>}
        <label className="flex items-start gap-3 rounded-control border border-warning-line bg-warning-soft p-4 text-ui text-warning-fg"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} className="mt-0.5 h-4 w-4 shrink-0 accent-accent" /><span>{editing?.action === 'cancel' ? 'Cancel the pending request. A call that has already started cannot be stopped here.' : 'I approve this follow-up call and its wallet charges. Calling hours may move it later; DND or a conversion can block it.'}</span></label>
        {editError && <p role="alert" className="text-ui text-danger-fg">{editError}</p>}
        <TactileButton type="submit" variant={editing?.action === 'cancel' ? 'danger' : 'primary'} disabled={!confirmed || busy || readOnly} loading={busy}>{editing?.action === 'cancel' ? 'Confirm cancellation' : 'Schedule follow-up'}</TactileButton>
      </form>
    </Modal>
    <Modal isOpen={campaignOpen} onClose={() => { if (!campaignBusy) setCampaignOpen(false); }} title="Campaign from scheduled follow-ups" subtitle="Choose callback requests or missed calls without changing their saved times." maxWidth="max-w-6xl">{campaignOpen && <CampaignSetup initialAgentId={agentId || ''} initialSource="callbacks" onBusyChange={setCampaignBusy} onComplete={() => { setCampaignOpen(false); refresh(); }} />}</Modal>
  </div>;
}
