import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowUpRight, LayoutGrid, List, PhoneCall, Plus, RefreshCw, Search, Users } from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { StatusBadge } from '../ui/StatusBadge';
import { TactileButton } from '../ui/TactileButton';
import { Modal } from '../ui/Modal';
import { useWorkspace } from '../context/WorkspaceContext';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../services/api';
import { leadStageToApi } from '../../services/apiNormalize';
import { CallbackRequests } from './CallbackRequests';
import { CampaignSetup } from './CampaignSetup';
import { FollowUpQueue } from './FollowUpQueue';
import { DncRegistryPanel } from './DncRegistryPanel';
import { LeadPriority } from './LeadPriority';

const STAGES = ['New', 'Contacted', 'Qualified', 'Meeting Booked', 'Converted', 'Unqualified'];
const PAGE_SIZE = 25;
const field = 'w-full min-w-0 min-h-11 rounded-xl border border-[#E4E2EB] bg-white px-3 py-2 text-sm text-[#0F0E17] focus:outline-none focus:ring-2 focus:ring-[#6344E7]/30';
const emptyLead = { name: '', phone: '', email: '', notes: '', agentId: '' };
const formatDate = (value) => {
  const date = new Date(value);
  return value && Number.isFinite(date.getTime()) ? date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : 'Not recorded';
};

export function LeadsModule({ agentId = null, agentName = '', onOpenHistory }) {
  const { user } = useAuth();
  const readOnly = user?.role === 'customer_viewer' || user?.role === 'viewer';
  const { agents, createLead, triggerCallToLead, phoneNumbers, outboundFromE164, setPreferredOutboundFrom, setSelectedCallId } = useWorkspace();
  const [area, setArea] = useState('pipeline');
  const [view, setView] = useState('table');
  const [filters, setFilters] = useState({ search: '', stage: '', owner: '', phone: '', days: '', sort: 'updated' });
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [page, setPage] = useState({ leads: [], total: 0, stageCounts: {}, key: '' });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [selected, setSelected] = useState([]);
  const [detail, setDetail] = useState(null);
  const [draft, setDraft] = useState({ stage: '', notes: '' });
  const [detailError, setDetailError] = useState('');
  const [conversionConfirmed, setConversionConfirmed] = useState(false);
  const [busy, setBusy] = useState('');
  const operationLock = useRef(false);
  const [addOpen, setAddOpen] = useState(false);
  const [addForm, setAddForm] = useState(emptyLead);
  const [addError, setAddError] = useState('');
  const [campaignLeads, setCampaignLeads] = useState(null);
  const [campaignBusy, setCampaignBusy] = useState(false);
  useEffect(() => { const timer = setTimeout(() => setSearch(filters.search.trim()), 250); return () => clearTimeout(timer); }, [filters.search]);
  const updatedSince = useMemo(() => filters.days ? new Date(Date.now() - Number(filters.days) * 86400000).toISOString() : undefined, [filters.days]);
  const query = useMemo(() => ({ agentId: agentId || filters.owner || undefined, search,
    stage: filters.stage || undefined, hasPhone: filters.phone ? filters.phone === 'yes' : undefined,
    updatedSince, sort: filters.sort, limit: PAGE_SIZE, offset }), [agentId, filters.owner, filters.stage, filters.phone, filters.sort, updatedSince, search, offset]);
  const key = JSON.stringify(query);
  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    api.leads.listPage(query).then((result) => {
      if (!active) return;
      if (result.total && offset >= result.total) { setOffset(Math.floor((result.total - 1) / PAGE_SIZE) * PAGE_SIZE); return; }
      const counts = result.stageCounts || Object.fromEntries(STAGES.map((stage) => [leadStageToApi(stage), result.leads.filter((lead) => lead.stage === stage).length]));
      setPage({ ...result, stageCounts: counts, key });
    }).catch((err) => { if (active) setError(err.message || 'Could not load leads. Try again.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [query, key, refresh]);
  useEffect(() => { setSelected([]); setDetail(null); setNotice(''); }, [agentId]);
  const rows = page.key === key ? page.leads : [];
  const total = page.key === key ? page.total : 0;
  const counts = page.key === key ? page.stageCounts : {};
  const selectedRows = rows.filter((lead) => selected.includes(lead.id) && !lead.doNotCall);
  const callableRows = rows.filter((lead) => Boolean(lead.phone?.trim()) && !lead.doNotCall);
  const ownerName = (lead) => agents.find((agent) => agent.id === lead.agentId)?.name || (lead.agentId ? 'Former agent' : 'Unassigned');
  const changeFilter = (name, value) => { setFilters((current) => ({ ...current, [name]: value })); setOffset(0); setSelected([]); };
  const openDetail = (lead) => { setDetail(lead); setDraft({ stage: lead.stage, notes: lead.notes || '' }); setDetailError(''); setConversionConfirmed(false); };
  const detailDirty = detail && (draft.stage !== detail.stage || draft.notes !== (detail.notes || ''));
  const closeDetail = () => {
    if (busy) return;
    if (detailDirty && !window.confirm('Discard the unsaved lead changes?')) return;
    setDetail(null);
  };
  async function saveDetail() {
    if (!detail || operationLock.current || readOnly) return;
    operationLock.current = true; setBusy('save'); setDetailError('');
    try {
      const updated = await api.leads.update(detail.id, { ...draft, expectedUpdatedAt: detail.updatedAt || null, ...(draft.stage === 'Converted' && detail.stage !== 'Converted' ? { confirmConverted: conversionConfirmed } : {}) });
      setDetail(updated || { ...detail, ...draft }); setRefresh((value) => value + 1);
      setNotice('Lead changes saved.');
    } catch (err) { setDetailError(err.message || 'Could not save. Your changes are still here.'); }
    finally { operationLock.current = false; setBusy(''); }
  }
  async function callLead(lead) {
    if (operationLock.current) return;
    operationLock.current = true; setBusy(lead.id); setDetailError(''); setError(''); setNotice('');
    try { await triggerCallToLead(lead, agentId); setNotice(`Call requested for ${lead.name}. Follow its progress in call history.`); }
    catch (err) { const message = err.message || 'Could not start the call.'; setError(message); if (detail) setDetailError(message); }
    finally { operationLock.current = false; setBusy(''); }
  }
  function openHistory(lead) {
    if (detailDirty && !window.confirm('Discard the unsaved lead changes and open call history?')) return;
    setSelectedCallId?.(null);
    if (onOpenHistory) onOpenHistory(lead);
    else {
      sessionStorage.setItem('dialtact_calls_search', lead.phone);
      if (lead.agentId) sessionStorage.setItem('dialtact_calls_agent', lead.agentId);
      window.location.hash = '#dashboard/calls';
    }
  }
  const toggle = (lead) => setSelected((current) => current.includes(lead.id) ? current.filter((id) => id !== lead.id) : [...current, lead.id]);
  const metrics = [['Matching leads', total], ['New enquiries', counts.new || 0], ['Qualified', counts.qualified || 0], ['Meetings booked', counts.meeting_booked || 0], ['Converted', counts.converted || 0]];

  const navigation = <nav aria-label="Lead management" className="flex flex-wrap gap-2 rounded-2xl border border-[#E4E2EB] bg-white p-2">{[['pipeline', 'Pipeline'], ['followups', 'Callbacks & missed calls'], ['dnd', 'Do not call']].map(([value, title]) => <button key={value} type="button" aria-pressed={area === value} onClick={() => setArea(value)} className={`min-h-11 rounded-xl px-4 text-sm font-medium ${area === value ? 'bg-[#0F0E17] text-white' : 'text-[#524E5E] hover:bg-[#FAF9FD]'}`}>{title}</button>)}</nav>;
  if (area === 'followups') return <div className="space-y-5">{navigation}<FollowUpQueue agentId={agentId} readOnly={readOnly} /><CallbackRequests agentId={agentId} readOnly={readOnly} /></div>;
  if (area === 'dnd') return <div className="space-y-5">{navigation}<DncRegistryPanel readOnly={readOnly} /></div>;
  return (
    <div className="min-w-0 space-y-5" data-testid="leads-workspace">
      {navigation}
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div><p className="text-xs font-semibold uppercase tracking-wider text-[#716C7F]">Customer pipeline</p>
          <h2 className="mt-1 text-2xl font-bold tracking-tight text-[#0F0E17]">{agentId ? `${agentName || 'Agent'} leads` : 'Leads'}</h2>
          <p className="mt-1 text-sm text-[#524E5E]">Review enquiries, keep a clear next step, and follow up by call or campaign.</p></div>
        <div className="flex flex-wrap gap-2">
          <TactileButton variant="secondary" icon={RefreshCw} disabled={loading} onClick={() => setRefresh((value) => value + 1)}>Refresh leads</TactileButton>
          <TactileButton icon={Plus} disabled={readOnly} onClick={() => { setAddForm({ ...emptyLead, agentId: agentId || '' }); setAddError(''); setAddOpen(true); }}>Add lead</TactileButton>
        </div>
      </header>
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-5" aria-label="Lead analytics">
        {metrics.map(([label, value]) => <SolidCard key={label} padding="p-4"><p className="text-xs text-[#524E5E]">{label}</p><p className="mt-2 text-2xl font-semibold tabular-nums" data-testid={`lead-metric-${label.toLowerCase().replaceAll(' ', '-')}`}>{loading ? '—' : value.toLocaleString()}</p><p className="mt-1 text-[11px] text-[#716C7F]">Across current filters</p></SolidCard>)}
      </div>
      <SolidCard padding="p-4" className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <label className="block text-xs font-medium sm:col-span-2">Search leads<div className="relative mt-1"><Search className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-[#716C7F]" /><input type="search" className={`${field} pl-9`} value={filters.search} onChange={(event) => changeFilter('search', event.target.value)} placeholder="Name, phone, email or notes" /></div></label>
          <label className="block text-xs font-medium">Stage<select className={`${field} mt-1`} value={filters.stage} onChange={(event) => changeFilter('stage', event.target.value)}><option value="">All stages</option>{STAGES.map((stage) => <option key={stage}>{stage}</option>)}</select></label>
          {!agentId && <label className="block text-xs font-medium">Agent owner<select className={`${field} mt-1`} value={filters.owner} onChange={(event) => changeFilter('owner', event.target.value)}><option value="">All agents</option><option value="unassigned">Unassigned</option>{agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></label>}
          <label className="block text-xs font-medium">Contact availability<select className={`${field} mt-1`} value={filters.phone} onChange={(event) => changeFilter('phone', event.target.value)}><option value="">All contacts</option><option value="yes">Has phone number</option><option value="no">Missing phone number</option></select></label>
          <label className="block text-xs font-medium">Last updated<select className={`${field} mt-1`} value={filters.days} onChange={(event) => changeFilter('days', event.target.value)}><option value="">Any time</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option></select></label>
          <label className="block text-xs font-medium">Sort by<select className={`${field} mt-1`} value={filters.sort} onChange={(event) => changeFilter('sort', event.target.value)}><option value="updated">Recently updated</option><option value="created">Newest enquiries</option><option value="name">Name A–Z</option></select></label>
          <div className="flex items-end"><TactileButton variant="ghost" onClick={() => { setFilters({ search: '', stage: '', owner: '', phone: '', days: '', sort: 'updated' }); setOffset(0); setSelected([]); }}>Clear filters</TactileButton></div>
        </div>
      </SolidCard>
      {error && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"><span>{error}</span><TactileButton variant="secondary" onClick={() => setRefresh((value) => value + 1)}>Retry leads</TactileButton></div>}
      {notice && <p role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}
      <SolidCard padding="p-0" className="min-w-0 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#E4E2EB] p-4">
          <div><h3 className="text-sm font-semibold">Your pipeline</h3><p className="mt-1 text-xs text-[#716C7F]">{selectedRows.length ? `${selectedRows.length} selected on this page` : `${total.toLocaleString()} matching leads · select contacts for a campaign`}</p></div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-lg border border-[#E4E2EB] p-1" role="group" aria-label="Lead view">{[['table', 'List view', List], ['board', 'Board view', LayoutGrid]].map(([value, label, Icon]) => <button key={value} type="button" aria-label={label} aria-pressed={view === value} onClick={() => setView(value)} className={`min-h-9 min-w-9 rounded-md p-2 ${view === value ? 'bg-[#0F0E17] text-white' : 'text-[#524E5E]'}`}><Icon className="h-4 w-4" /></button>)}</div>
            <TactileButton variant="brand" icon={Users} disabled={readOnly || !selectedRows.length || loading} onClick={() => setCampaignLeads(selectedRows)}>Create campaign{selectedRows.length ? ` (${selectedRows.length})` : ''}</TactileButton>
          </div>
        </div>
        {loading ? <p role="status" className="p-8 text-center text-sm text-[#524E5E]">Loading leads…</p> : rows.length === 0 ? <div className="p-10 text-center"><Users className="mx-auto h-8 w-8 text-[#8C879A]" /><h4 className="mt-3 text-sm font-semibold">{error ? 'Leads could not be loaded' : 'No leads match these filters'}</h4><p className="mt-1 text-sm text-[#716C7F]">{error ? 'Retry to load your pipeline.' : 'Clear the filters or add your first enquiry.'}</p></div> : view === 'table' ? <>
          <div className="hidden overflow-x-auto md:block"><table className="w-full text-left text-sm"><caption className="sr-only">Lead contacts, pipeline stage, owner and last update</caption>
            <thead className="bg-[#FAF9FD] text-xs text-[#716C7F]"><tr><th className="p-4"><input type="checkbox" aria-label="Select all callable leads on this page" disabled={readOnly || !callableRows.length} checked={Boolean(callableRows.length) && callableRows.every((lead) => selected.includes(lead.id))} onChange={(event) => setSelected(event.target.checked ? callableRows.map((lead) => lead.id) : [])} className="h-4 w-4 accent-[#6344E7]" /></th>{['Contact', 'Stage', 'Agent owner', 'Updated', ''].map((label) => <th key={label} className="px-4 py-3 font-medium">{label}</th>)}</tr></thead>
            <tbody className="divide-y divide-[#E4E2EB]">{rows.map((lead) => <tr key={lead.id} className="hover:bg-[#FAF9FD]" data-testid={`lead-row-${lead.id}`}>
              <td className="p-4"><input type="checkbox" aria-label={`Select ${lead.name}`} disabled={readOnly || lead.doNotCall || !lead.phone?.trim()} checked={selected.includes(lead.id)} onChange={() => toggle(lead)} className="h-4 w-4 accent-[#6344E7]" /></td>
              <td className="max-w-sm p-4"><button type="button" onClick={() => openDetail(lead)} className="font-semibold text-[#0F0E17] hover:text-[#6344E7] hover:underline">{lead.name}</button><p className="mt-1 font-mono text-xs text-[#524E5E]">{lead.phone || 'Phone missing'}</p>{lead.email && <p className="mt-0.5 truncate text-xs text-[#716C7F]">{lead.email}</p>}<p className="mt-1 line-clamp-1 max-w-xs text-xs text-[#716C7F]">{lead.notes || 'Add notes and a next step'}</p></td>
              <td className="p-4"><StatusBadge status={lead.stage} size="xs" /><LeadPriority lead={lead} /></td><td className="p-4 text-xs text-[#524E5E]">{ownerName(lead)}</td><td className="whitespace-nowrap p-4 text-xs text-[#716C7F]">{formatDate(lead.updatedAt)}</td>
              <td className="p-4 text-right"><TactileButton size="sm" variant="secondary" icon={ArrowUpRight} onClick={() => openDetail(lead)} aria-label={`Open ${lead.name}`}>Details</TactileButton></td>
            </tr>)}</tbody></table></div>
          <ul className="divide-y divide-[#E4E2EB] md:hidden">{rows.map((lead) => <li key={lead.id} className="space-y-3 p-4"><div className="flex items-start justify-between gap-3"><div className="flex min-w-0 items-center gap-3"><input type="checkbox" aria-label={`Select ${lead.name}`} disabled={readOnly || lead.doNotCall || !lead.phone?.trim()} checked={selected.includes(lead.id)} onChange={() => toggle(lead)} className="h-4 w-4 accent-[#6344E7]" /><button type="button" onClick={() => openDetail(lead)} className="truncate text-left text-sm font-semibold">{lead.name}</button></div><StatusBadge status={lead.stage} size="xs" /></div><LeadPriority lead={lead} /><p className="font-mono text-xs text-[#524E5E]">{lead.phone || 'Phone missing'}</p><p className="line-clamp-2 text-xs text-[#716C7F]">{lead.notes || 'No notes yet'}</p><div className="flex justify-between text-xs text-[#716C7F]"><span>{ownerName(lead)}</span><span>{formatDate(lead.updatedAt)}</span></div><TactileButton variant="secondary" size="sm" onClick={() => openDetail(lead)}>View details</TactileButton></li>)}</ul>
        </> : <div className="flex gap-4 overflow-x-auto p-4" aria-label="Lead stages on this page">{STAGES.map((stage) => <section key={stage} className="w-64 shrink-0 space-y-3"><h4 className="flex justify-between text-xs font-semibold">{stage}<span>{counts[leadStageToApi(stage)] || 0} total</span></h4>{rows.filter((lead) => lead.stage === stage).map((lead) => <div key={lead.id} className="space-y-3 rounded-xl border border-[#E4E2EB] p-4"><div className="flex items-start gap-2"><input type="checkbox" aria-label={`Select ${lead.name}`} disabled={readOnly || lead.doNotCall || !lead.phone?.trim()} checked={selected.includes(lead.id)} onChange={() => toggle(lead)} className="mt-1 h-4 w-4 accent-[#6344E7]" /><button type="button" onClick={() => openDetail(lead)} className="text-left text-sm font-semibold hover:text-[#6344E7]">{lead.name}</button></div><LeadPriority lead={lead} /><p className="text-xs text-[#524E5E]">{lead.phone || 'Phone missing'}</p><p className="line-clamp-3 text-xs text-[#716C7F]">{lead.notes || 'No notes yet'}</p><p className="text-xs text-[#716C7F]">{ownerName(lead)} · {formatDate(lead.updatedAt)}</p></div>)}{!rows.some((lead) => lead.stage === stage) && <p className="rounded-xl border border-dashed border-[#E4E2EB] p-4 text-xs text-[#716C7F]">No {stage.toLowerCase()} leads on this page.</p>}</section>)}</div>}
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-[#E4E2EB] px-4 py-3 text-xs text-[#716C7F]"><span>{total ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} of ${total}` : '0 leads'} · {view === 'board' ? 'Board shows this page' : '25 per page'}</span><div className="flex gap-2"><TactileButton variant="secondary" size="sm" disabled={!offset || loading} onClick={() => { setOffset(Math.max(0, offset - PAGE_SIZE)); setSelected([]); }}>Previous leads</TactileButton><TactileButton variant="secondary" size="sm" disabled={offset + PAGE_SIZE >= total || loading} onClick={() => { setOffset(offset + PAGE_SIZE); setSelected([]); }}>Next leads</TactileButton></div></footer>
      </SolidCard>
      <CallbackRequests agentId={agentId} readOnly={readOnly} />
      {readOnly && <p className="text-xs text-[#716C7F]" role="status">Read-only access: you can review leads and call history.</p>}
      <Modal isOpen={Boolean(detail)} onClose={closeDetail} title={detail?.name || 'Lead details'} subtitle="Contact details, notes and follow-up" maxWidth="max-w-2xl">
        {detail && <div className="space-y-5">
          <LeadPriority lead={detail} detailed />
          <dl className="grid grid-cols-2 gap-4 rounded-xl bg-[#FAF9FD] p-4 text-sm">{[['Phone', detail.phone || 'Not provided'], ['Email', detail.email || 'Not provided'], ['Agent owner', ownerName(detail)], ['Created', formatDate(detail.createdAt)], ['Last updated', formatDate(detail.updatedAt)]].map(([label, value]) => <div key={label} className="min-w-0"><dt className="text-xs text-[#716C7F]">{label}</dt><dd className="mt-1 break-words font-medium">{value}</dd></div>)}</dl>
          <label className="block text-sm font-medium">Pipeline stage<select className={`${field} mt-1`} value={draft.stage} disabled={readOnly || Boolean(busy)} onChange={(event) => { setDraft((current) => ({ ...current, stage: event.target.value })); setConversionConfirmed(false); }}>{STAGES.map((stage) => <option key={stage}>{stage}</option>)}</select></label>
          {draft.stage === 'Converted' && detail.stage !== 'Converted' && <label className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900"><input type="checkbox" checked={conversionConfirmed} disabled={readOnly || Boolean(busy)} onChange={(event) => setConversionConfirmed(event.target.checked)} className="mt-1 h-4 w-4 shrink-0" /><span>I confirm this lead became a customer.</span></label>}
          <label className="block text-sm font-medium">Notes & next step<textarea className={`${field} mt-1 min-h-36 leading-relaxed`} maxLength={20000} value={draft.notes} disabled={readOnly || Boolean(busy)} onChange={(event) => setDraft((current) => ({ ...current, notes: event.target.value }))} placeholder="What they need, what was discussed, and what should happen next." /></label>
          <p className="text-xs text-[#716C7F]">Notes are saved when you choose Save lead changes.</p>
          {detailError && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{detailError}</p>}
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#E4E2EB] pt-4"><TactileButton variant="secondary" disabled={!detail.phone || Boolean(busy)} onClick={() => openHistory(detail)}>View recent calls</TactileButton><TactileButton disabled={readOnly || !detailDirty || Boolean(busy) || (draft.stage === 'Converted' && detail.stage !== 'Converted' && !conversionConfirmed)} loading={busy === 'save'} onClick={saveDetail}>Save lead changes</TactileButton></div>
          <section className="space-y-3 rounded-xl border border-[#E4E2EB] p-4" aria-label="Call this lead"><h3 className="text-sm font-semibold">Follow up by phone</h3>
            {phoneNumbers.length > 0 && <label className="block text-xs font-medium">Outbound caller ID<select className={`${field} mt-1`} value={outboundFromE164 || ''} onChange={(event) => setPreferredOutboundFrom(event.target.value)}><option value="">Agent’s configured line</option>{phoneNumbers.filter((number) => number.status !== 'released').map((number) => <option key={number.id} value={number.number}>{number.formatted || number.number}</option>)}</select></label>}
            {!detail.agentId && <p className="text-xs text-[#92400E]">Assign an agent when adding this lead, or select it for a campaign and choose who calls.</p>}
            <TactileButton icon={PhoneCall} disabled={readOnly || detail.doNotCall || !detail.phone || !detail.agentId || Boolean(busy) || detailDirty} loading={busy === detail.id} onClick={() => callLead(detail)}>Call lead</TactileButton>
            {detailDirty && <p className="text-xs text-[#716C7F]">Save your notes before starting a call.</p>}
          </section>
        </div>}
      </Modal>
      <Modal isOpen={addOpen} onClose={() => { if (!busy) setAddOpen(false); }} title="Add lead" subtitle="Capture an enquiry and assign its next conversation." maxWidth="max-w-lg">
        <form className="space-y-4" onSubmit={async (event) => {
          event.preventDefault(); if (operationLock.current) return;
          operationLock.current = true; setBusy('add'); setAddError('');
          try {
            if (!addForm.name.trim()) throw new Error('Name is required.');
            await createLead({ ...addForm, agentId: agentId || addForm.agentId || null });
            setAddOpen(false); setOffset(0); setRefresh((value) => value + 1); setNotice('Lead added to your pipeline.');
          } catch (err) { setAddError(err.message || 'Could not create the lead. Your details are still here.'); }
          finally { operationLock.current = false; setBusy(''); }
        }}>
          {['name', 'phone', 'email'].map((name) => <label key={name} className="block text-sm font-medium">{name === 'phone' ? 'Phone (with country code)' : name === 'name' ? 'Name' : 'Email'}<input className={`${field} mt-1`} required={name === 'name'} type={name === 'email' ? 'email' : name === 'phone' ? 'tel' : 'text'} maxLength={name === 'name' ? 255 : name === 'phone' ? 32 : 320} value={addForm[name]} disabled={readOnly || Boolean(busy)} onChange={(event) => setAddForm((current) => ({ ...current, [name]: event.target.value }))} /></label>)}
          {!agentId && <label className="block text-sm font-medium">Agent owner<select className={`${field} mt-1`} disabled={Boolean(busy)} value={addForm.agentId} onChange={(event) => setAddForm((current) => ({ ...current, agentId: event.target.value }))}><option value="">Unassigned</option>{agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></label>}
          <label className="block text-sm font-medium">Notes & next step<textarea className={`${field} mt-1 min-h-24`} maxLength={20000} value={addForm.notes} disabled={readOnly || Boolean(busy)} onChange={(event) => setAddForm((current) => ({ ...current, notes: event.target.value }))} /></label>
          {addError && <p role="alert" className="text-sm text-red-800">{addError}</p>}
          <TactileButton type="submit" loading={busy === 'add'} disabled={Boolean(busy)}>Save lead</TactileButton>
        </form>
      </Modal>
      <Modal isOpen={Boolean(campaignLeads)} onClose={() => { if (!campaignBusy) setCampaignLeads(null); }} title="Campaign from selected leads" subtitle="Review contacts, choose an agent, then save a draft or launch." maxWidth="max-w-5xl">
        {campaignLeads && <CampaignSetup initialAgentId={agentId || ''} initialContacts={campaignLeads.map((lead) => ({ phone: lead.phone, full_name: lead.name, email: lead.email, notes: lead.notes, 'custom_field:lead_id': lead.id, 'custom_field:lead_stage': lead.stage }))}
          onBusyChange={setCampaignBusy} onComplete={(campaign) => { setCampaignLeads(null); setSelected([]); setNotice(`${campaign.name} ${campaign.status === 'running' ? 'queued' : 'saved as a draft'}. You can manage it in Campaigns.`); }} />}
      </Modal>
    </div>
  );
}
