import React, { useCallback, useEffect, useState } from 'react';
import { CalendarClock, RefreshCw } from 'lucide-react';
import { api } from '../../services/api';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
import { Modal } from '../ui/Modal';
import { showToast } from '../ui/ToastHost';

const label = (value) => String(value || '').replace(/_/g, ' ');
const instant = (value, zone) => value ? new Date(value).toLocaleString(undefined, { timeZone: zone || undefined, dateStyle: 'medium', timeStyle: 'short' }) : 'Choose a time';

export function FollowUpQueue({ agentId, readOnly = false }) {
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
  useEffect(() => {
    let active = true;
    setLoading(true); setError(''); setData({ jobs: [], total: 0 });
    api.followups.list({ agentId, status, offset, limit: 25 }).then((res) => { if (active) setData(res); })
      .catch((e) => { if (active) setError(e.message || 'Could not load follow-ups.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [agentId, status, offset, revision]);
  const refresh = useCallback(() => setRevision((v) => v + 1), []);
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
  return <div className="space-y-4" data-testid="followup-queue">
    <SolidCard><div className="flex flex-wrap items-center justify-between gap-4"><div className="flex gap-3"><CalendarClock className="h-5 w-5 text-[#6344E7]" /><div><h2 className="font-semibold">Scheduled follow-ups</h2><p className="mt-1 max-w-2xl text-sm text-[#716C7F]">Caller requests and missed inbound calls share one durable queue. Review unclear timing here. Permission and automatic modes are configured in each agent’s settings.</p></div></div><TactileButton variant="secondary" icon={RefreshCw} onClick={refresh} disabled={loading}>Refresh follow-ups</TactileButton></div>
      <label className="mt-4 block max-w-xs text-xs font-medium">Follow-up status<select aria-label="Follow-up status" className="mt-1 min-h-11 w-full rounded-xl border border-[#E4E2EB] bg-white px-3" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>{['active', 'needs_review', 'scheduled', 'completed', 'suppressed', 'cancelled', 'expired'].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label>
    </SolidCard>
    {error && <p role="alert" className="rounded-xl bg-amber-50 p-4 text-sm text-amber-950">{error}</p>}
    {loading ? <p role="status" className="p-6 text-center text-sm">Loading follow-ups…</p> : !error && <SolidCard className="space-y-4">{data.jobs.length === 0 ? <p className="py-6 text-center text-sm text-[#716C7F]">No {label(status)} follow-ups.</p> : <ul className="divide-y divide-[#E4E2EB]">{data.jobs.map((row) => <li key={row.id} className="flex flex-wrap items-start justify-between gap-4 py-4"><div className="min-w-0"><p className="text-sm font-semibold">{row.phone || 'Number unavailable'} <span className="ml-2 rounded-md bg-[#F0ECFF] px-2 py-1 text-xs text-[#5034CE]">{label(row.kind)}</span></p><p className="mt-2 text-sm">{instant(row.dueAt, row.timezone)} {row.timezone && <span className="text-xs text-[#716C7F]">({row.timezone})</span>}</p>{row.requestedWhen && <p className="mt-1 max-w-xl break-words text-xs text-[#524E5E]">Caller requested: {row.requestedWhen}</p>}<p className="mt-1 text-xs text-[#716C7F]">{label(row.status)} · {label(row.reason)} · {row.attempts} attempts</p><p className="mt-1 text-xs text-[#716C7F]">Expires {instant(row.expiresAt, row.timezone)}</p></div>{['planning', 'needs_review', 'scheduled'].includes(row.status) && <div className="flex gap-2"><TactileButton size="sm" variant="secondary" disabled={readOnly} onClick={() => open(row, 'schedule')}>Review time</TactileButton><TactileButton size="sm" variant="secondary" disabled={readOnly} onClick={() => open(row, 'cancel')}>Cancel follow-up</TactileButton></div>}</li>)}</ul>}<div className="flex flex-wrap items-center justify-between gap-2 border-t border-[#E4E2EB] pt-4 text-xs text-[#716C7F]"><span>{data.total} matching follow-ups</span><div className="flex gap-2"><TactileButton size="sm" variant="secondary" disabled={!offset || loading} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous follow-ups</TactileButton><TactileButton size="sm" variant="secondary" disabled={offset + 25 >= data.total || loading} onClick={() => setOffset(offset + 25)}>Next follow-ups</TactileButton></div></div></SolidCard>}
    <Modal isOpen={Boolean(editing)} onClose={() => { if (!busy) setEditing(null); }} title={editing?.action === 'cancel' ? 'Cancel this follow-up?' : 'Review callback time'} maxWidth="max-w-lg"><form onSubmit={save} className="space-y-4">{editing?.action === 'schedule' && <label className="block text-sm font-medium">Time in your browser timezone ({Intl.DateTimeFormat().resolvedOptions().timeZone})<input aria-label="Follow-up date and time" type="datetime-local" required value={due} onChange={(e) => setDue(e.target.value)} className="mt-2 min-h-11 w-full rounded-xl border border-[#E4E2EB] px-3" /></label>}<label className="flex items-start gap-3 rounded-xl bg-amber-50 p-4 text-sm text-amber-950"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} className="mt-1 h-4 w-4 shrink-0" /><span>{editing?.action === 'cancel' ? 'Cancel the pending request. A call already dispatched cannot be recalled here.' : 'I approve this follow-up call and its wallet charges. Calling hours may move it later; DND or conversion can block it.'}</span></label>{editError && <p role="alert" className="text-sm text-red-700">{editError}</p>}<TactileButton type="submit" disabled={!confirmed || busy || readOnly} loading={busy}>{editing?.action === 'cancel' ? 'Confirm cancellation' : 'Schedule follow-up'}</TactileButton></form></Modal>
  </div>;
}
