import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowUpRight, LayoutGrid, List, PhoneCall, Plus, RefreshCw, Search, Users } from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { StatusBadge } from '../ui/StatusBadge';
import { PageHeader } from '../ui/PageHeader';
import { EmptyState } from '../ui/EmptyState';
import { Avatar } from '../ui/Avatar';
import { statusWord } from '../../lib/internalLabels';
import { relativeTime } from '../../lib/money';
import { TactileButton } from '../ui/TactileButton';
import { Modal } from '../ui/Modal';
import { useWorkspace } from '../context/WorkspaceContext';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../services/api';
import { leadStageToApi } from '../../services/apiNormalize';
import { CallbackRequests } from './CallbackRequests';
import { LanguageCallbacks } from './LanguageCallbacks';
import { CampaignSetup } from './CampaignSetup';
import { FollowUpQueue } from './FollowUpQueue';
import { DncRegistryPanel } from './DncRegistryPanel';
import { LeadPriority } from './LeadPriority';

const STAGES = ['New', 'Contacted', 'Qualified', 'Meeting Booked', 'Converted', 'Unqualified'];
const PAGE_SIZE = 25;
const field = 'w-full min-w-0 min-h-11 rounded-control border border-line bg-surface px-3 py-2 text-base sm:text-ui text-ink placeholder:text-fg-subtle focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15 disabled:opacity-50';
const emptyLead = { name: '', phone: '', email: '', notes: '', agentId: '' };
const formatDate = (value) => {
  const date = new Date(value);
  return value && Number.isFinite(date.getTime()) ? date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : 'Not recorded';
};

export function LeadsModule({ agentId = null, agentName = '', onOpenHistory }) {
  const { user } = useAuth();
  const readOnly = user?.role === 'customer_viewer' || user?.role === 'viewer';
  const { agents, createLead, triggerCallToLead, phoneNumbers, outboundFromE164, setPreferredOutboundFrom, setSelectedCallId } = useWorkspace();
  // One-shot deep links from the home feed ("Open follow-ups", "Open lead").
  const [area, setArea] = useState(() => {
    if (agentId || typeof window === 'undefined') return 'pipeline';
    const wanted = sessionStorage.getItem('dialtact_leads_area');
    sessionStorage.removeItem('dialtact_leads_area');
    return ['pipeline', 'followups', 'language', 'dnd'].includes(wanted) ? wanted : 'pipeline';
  });
  const [view, setView] = useState('table');
  const [initialLeadSearch] = useState(() => {
    if (agentId || typeof window === 'undefined') return '';
    const wanted = sessionStorage.getItem('dialtact_leads_search') || '';
    sessionStorage.removeItem('dialtact_leads_search');
    return wanted.slice(0, 120);
  });
  // One-shot "open this lead" from the home feed's detail panel.
  const [openLeadId] = useState(() => {
    if (agentId || typeof window === 'undefined') return '';
    const wanted = sessionStorage.getItem('dialtact_leads_open') || '';
    sessionStorage.removeItem('dialtact_leads_open');
    return wanted.slice(0, 64);
  });
  const leadOpened = useRef(false);
  const [filters, setFilters] = useState({ search: initialLeadSearch, stage: '', owner: '', phone: '', days: '', sort: 'updated' });
  const [search, setSearch] = useState(initialLeadSearch);
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
  useEffect(() => {
    if (!openLeadId || leadOpened.current || loading) return;
    const hit = rows.find((lead) => lead.id === openLeadId);
    if (hit) { leadOpened.current = true; openDetail(hit); }
    else if (page.key === key) leadOpened.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openLeadId, rows, loading]);
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

  const areaTabs = [['pipeline', 'Pipeline'], ['followups', 'Callbacks & missed calls'], ['language', 'Callback in another language'], ['dnd', 'Do not call']];
  const areaCopy = {
    pipeline: 'Review enquiries, keep a clear next step, and follow up by call or campaign.',
    followups: 'Callers who asked for a call back and calls you missed, in the order they are due.',
    language: 'Callers who asked to talk in a language their agent does not speak yet.',
    dnd: 'Numbers your agents must never call.',
  };
  const header = (
    <PageHeader
      eyebrow={area === 'pipeline' ? 'Customer pipeline' : null}
      title={agentId ? `${agentName || 'Agent'} leads` : 'Leads'}
      description={areaCopy[area]}
      actions={area === 'pipeline' ? <>
        <TactileButton variant="secondary" icon={RefreshCw} disabled={loading} onClick={() => setRefresh((value) => value + 1)}>Refresh leads</TactileButton>
        <TactileButton icon={Plus} disabled={readOnly} onClick={() => { setAddForm({ ...emptyLead, agentId: agentId || '' }); setAddError(''); setAddOpen(true); }}>Add lead</TactileButton>
      </> : null}
    />
  );
  const navigation = (
    <nav aria-label="Lead management" className="flex max-w-full gap-0.5 overflow-x-auto rounded-control border border-line bg-surface-subtle p-0.5 no-scrollbar sm:inline-flex">
      {areaTabs.map(([value, title]) => (
        <button
          key={value}
          type="button"
          aria-pressed={area === value}
          onClick={() => setArea(value)}
          className={`inline-flex min-h-[40px] sm:min-h-[32px] shrink-0 items-center rounded-[8px] px-3 py-1.5 text-ui font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${area === value ? 'bg-surface text-ink shadow-craft-xs' : 'text-fg-body hover:text-ink'}`}
        >
          {title}
        </button>
      ))}
    </nav>
  );
  if (area === 'followups') return <div className="min-w-0 space-y-5">{header}{navigation}<FollowUpQueue agentId={agentId} readOnly={readOnly} /><CallbackRequests agentId={agentId} readOnly={readOnly} /></div>;
  if (area === 'language') return <div className="min-w-0 space-y-5">{header}{navigation}<LanguageCallbacks agentId={agentId} readOnly={readOnly} /></div>;
  if (area === 'dnd') return <div className="min-w-0 space-y-5">{header}{navigation}<DncRegistryPanel readOnly={readOnly} /></div>;
  const selectBox = (lead, extra = '') => (
    <input type="checkbox" aria-label={`Select ${lead.name}`} disabled={readOnly || lead.doNotCall || !lead.phone?.trim()} checked={selected.includes(lead.id)} onChange={() => toggle(lead)} className={`h-4 w-4 shrink-0 accent-accent ${extra}`} />
  );
  const updated = (lead) => (
    <time dateTime={lead.updatedAt || undefined} title={lead.updatedAt ? formatDate(lead.updatedAt) : undefined}>{lead.updatedAt ? relativeTime(lead.updatedAt) : 'Not recorded'}</time>
  );
  return (
    <div className="min-w-0 space-y-5" data-testid="leads-workspace">
      {header}
      {navigation}
      <section aria-label="Lead analytics" className="space-y-2">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
          {metrics.map(([label, value]) => (
            <SolidCard key={label} padding="p-4" className="min-w-0">
              <p className="text-meta text-fg-muted">{label}</p>
              <p className="mt-1 font-mono text-heading tabular-nums text-ink" data-testid={`lead-metric-${label.toLowerCase().replaceAll(' ', '-')}`}>{loading ? '—' : value.toLocaleString()}</p>
            </SolidCard>
          ))}
        </div>
        <p className="text-meta text-fg-muted">Counts follow the filters below.</p>
      </section>
      <SolidCard padding="p-4" className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <label className="block min-w-0 text-meta font-medium text-fg-body sm:col-span-2">Search leads<div className="relative mt-1"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-subtle" aria-hidden="true" /><input type="search" className={`${field} pl-9`} value={filters.search} onChange={(event) => changeFilter('search', event.target.value)} placeholder="Name, phone, email or notes" /></div></label>
          <label className="block min-w-0 text-meta font-medium text-fg-body">Stage<select className={`${field} mt-1`} value={filters.stage} onChange={(event) => changeFilter('stage', event.target.value)}><option value="">All stages</option>{STAGES.map((stage) => <option key={stage} value={stage}>{statusWord(stage).label}</option>)}</select></label>
          {!agentId && <label className="block min-w-0 text-meta font-medium text-fg-body">Agent owner<select className={`${field} mt-1`} value={filters.owner} onChange={(event) => changeFilter('owner', event.target.value)}><option value="">All agents</option><option value="unassigned">Unassigned</option>{agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></label>}
          <label className="block min-w-0 text-meta font-medium text-fg-body">Contact availability<select className={`${field} mt-1`} value={filters.phone} onChange={(event) => changeFilter('phone', event.target.value)}><option value="">All contacts</option><option value="yes">Has phone number</option><option value="no">Missing phone number</option></select></label>
          <label className="block min-w-0 text-meta font-medium text-fg-body">Last updated<select className={`${field} mt-1`} value={filters.days} onChange={(event) => changeFilter('days', event.target.value)}><option value="">Any time</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option></select></label>
          <label className="block min-w-0 text-meta font-medium text-fg-body">Sort by<select className={`${field} mt-1`} value={filters.sort} onChange={(event) => changeFilter('sort', event.target.value)}><option value="updated">Recently updated</option><option value="created">Newest enquiries</option><option value="name">Name A–Z</option></select></label>
          <div className="flex items-end"><TactileButton variant="ghost" onClick={() => { setFilters({ search: '', stage: '', owner: '', phone: '', days: '', sort: 'updated' }); setOffset(0); setSelected([]); }}>Clear filters</TactileButton></div>
        </div>
      </SolidCard>
      {error && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-control border border-danger-line bg-danger-soft p-4 text-ui text-danger-fg"><span className="min-w-0 break-words">{error}</span><TactileButton variant="secondary" size="sm" onClick={() => setRefresh((value) => value + 1)}>Retry leads</TactileButton></div>}
      {notice && <p role="status" className="rounded-control border border-success-line bg-success-soft p-3 text-ui text-success-fg">{notice}</p>}
      <SolidCard padding="p-0" className="min-w-0 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
          <div className="min-w-0"><h3 className="text-title text-ink">Your pipeline</h3><p className="mt-0.5 text-meta text-fg-muted">{selectedRows.length ? `${selectedRows.length} selected on this page` : `${total.toLocaleString()} matching leads · select contacts for a campaign`}</p></div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex items-center gap-0.5 rounded-control border border-line bg-surface-subtle p-0.5" role="group" aria-label="Lead view">{[['table', 'List view', List], ['board', 'Board view', LayoutGrid]].map(([value, label, Icon]) => <button key={value} type="button" aria-label={label} title={label} aria-pressed={view === value} onClick={() => setView(value)} className={`inline-flex min-h-9 min-w-9 items-center justify-center rounded-[8px] p-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${view === value ? 'bg-surface text-ink shadow-craft-xs' : 'text-fg-body hover:text-ink'}`}><Icon className="h-4 w-4" aria-hidden="true" /></button>)}</div>
            <TactileButton variant="brand" size="sm" icon={Users} disabled={readOnly || !selectedRows.length || loading} onClick={() => setCampaignLeads(selectedRows)}>Create campaign{selectedRows.length ? ` (${selectedRows.length})` : ''}</TactileButton>
          </div>
        </div>
        {loading ? <p role="status" className="p-8 text-center text-ui text-fg-muted">Loading leads…</p> : rows.length === 0 ? (
          <EmptyState
            compact
            icon={Users}
            title={error ? 'Leads could not be loaded' : 'No leads match these filters'}
            description={error ? 'Retry to load your pipeline.' : 'Clear the filters or add your first enquiry.'}
          />
        ) : view === 'table' ? <>
          <div className="hidden overflow-x-auto md:block"><table className="w-full text-left text-ui"><caption className="sr-only">Lead contacts, pipeline stage, owner and last update</caption>
            <thead><tr className="border-b border-line text-meta text-fg-muted"><th className="w-10 py-2.5 pl-5 pr-2"><input type="checkbox" aria-label="Select all callable leads on this page" disabled={readOnly || !callableRows.length} checked={Boolean(callableRows.length) && callableRows.every((lead) => selected.includes(lead.id))} onChange={(event) => setSelected(event.target.checked ? callableRows.map((lead) => lead.id) : [])} className="h-4 w-4 accent-accent" /></th>{['Contact', 'Stage', 'Agent owner', 'Updated', ''].map((label, index) => <th key={label || index} scope="col" className="px-3 py-2.5 font-medium">{label ? label : <span className="sr-only">Actions</span>}</th>)}</tr></thead>
            <tbody className="divide-y divide-line">{rows.map((lead) => <tr key={lead.id} className="align-top transition-colors hover:bg-canvas" data-testid={`lead-row-${lead.id}`}>
              <td className="py-4 pl-5 pr-2">{selectBox(lead)}</td>
              <td className="max-w-sm px-3 py-4"><div className="flex min-w-0 items-start gap-3"><Avatar name={lead.name} size="sm" /><div className="min-w-0"><button type="button" onClick={() => openDetail(lead)} title={lead.name} className="max-w-full truncate text-left font-semibold text-ink hover:text-accent-fg hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-control">{lead.name}</button><p className={`mt-0.5 text-meta text-fg-body ${lead.phone ? 'font-mono tabular-nums' : ''}`}>{lead.phone || 'Phone missing'}</p>{lead.email && <p className="mt-0.5 truncate text-meta text-fg-muted" title={lead.email}>{lead.email}</p>}<p className="mt-1 line-clamp-1 max-w-xs text-meta text-fg-muted" title={lead.notes || undefined}>{lead.notes || 'Add notes and a next step'}</p></div></div></td>
              <td className="px-3 py-4"><StatusBadge status={lead.stage} size="xs" /><LeadPriority lead={lead} /></td>
              <td className="px-3 py-4 text-ui text-fg-body"><span className="inline-flex min-w-0 items-center gap-2">{lead.agentId && <Avatar name={ownerName(lead)} size="xs" />}{ownerName(lead)}</span></td>
              <td className="whitespace-nowrap px-3 py-4 text-meta text-fg-muted">{updated(lead)}</td>
              <td className="py-4 pl-3 pr-5 text-right"><TactileButton size="sm" variant="secondary" icon={ArrowUpRight} onClick={() => openDetail(lead)} aria-label={`Open ${lead.name}`}>Details</TactileButton></td>
            </tr>)}</tbody></table></div>
          <ul className="divide-y divide-line md:hidden">{rows.map((lead) => <li key={lead.id} className="space-y-2 p-4">
            <div className="flex items-start gap-3">{selectBox(lead, 'mt-2.5')}<Avatar name={lead.name} size="sm" /><div className="min-w-0 flex-1"><div className="flex items-start justify-between gap-2"><button type="button" onClick={() => openDetail(lead)} title={lead.name} className="min-w-0 truncate text-left text-copy font-semibold text-ink">{lead.name}</button><StatusBadge status={lead.stage} size="xs" /></div><p className={`text-meta text-fg-body ${lead.phone ? 'font-mono tabular-nums' : ''}`}>{lead.phone || 'Phone missing'}</p></div></div>
            <LeadPriority lead={lead} />
            <p className="line-clamp-2 text-meta text-fg-muted">{lead.notes || 'No notes yet'}</p>
            <div className="flex items-center justify-between gap-2 text-meta text-fg-muted"><span className="min-w-0 truncate">{ownerName(lead)}</span>{updated(lead)}</div>
            <TactileButton variant="secondary" size="sm" onClick={() => openDetail(lead)}>View details</TactileButton>
          </li>)}</ul>
        </> : <div className="flex gap-4 overflow-x-auto p-4" aria-label="Lead stages on this page">{STAGES.map((stage) => <section key={stage} className="w-64 shrink-0 space-y-3">
          <h4 className="flex items-center justify-between gap-2 text-ui font-semibold text-ink">{statusWord(stage).label}<span className="text-meta font-normal text-fg-muted"><span className="font-mono tabular-nums">{counts[leadStageToApi(stage)] || 0}</span> total</span></h4>
          {rows.filter((lead) => lead.stage === stage).map((lead) => <div key={lead.id} className="space-y-2 rounded-control border border-line bg-surface p-3">
            <div className="flex items-start gap-2">{selectBox(lead, 'mt-1')}<button type="button" onClick={() => openDetail(lead)} title={lead.name} className="min-w-0 break-words text-left text-ui font-semibold text-ink hover:text-accent-fg">{lead.name}</button></div>
            <LeadPriority lead={lead} />
            <p className={`text-meta text-fg-body ${lead.phone ? 'font-mono tabular-nums' : ''}`}>{lead.phone || 'Phone missing'}</p>
            <p className="line-clamp-3 text-meta text-fg-muted">{lead.notes || 'No notes yet'}</p>
            <p className="text-meta text-fg-muted">{ownerName(lead)} · {updated(lead)}</p>
          </div>)}
          {!rows.some((lead) => lead.stage === stage) && <p className="rounded-control border border-dashed border-line p-4 text-meta text-fg-muted">No {statusWord(stage).label.toLowerCase()} leads on this page.</p>}
        </section>)}</div>}
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-3 text-meta text-fg-muted sm:px-5"><span><span className="font-mono tabular-nums">{total ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)}` : '0'}</span>{total ? ` of ${total.toLocaleString()}` : ' leads'} · {view === 'board' ? 'Board shows this page' : '25 per page'}</span><div className="flex gap-2"><TactileButton variant="secondary" size="sm" disabled={!offset || loading} onClick={() => { setOffset(Math.max(0, offset - PAGE_SIZE)); setSelected([]); }}>Previous leads</TactileButton><TactileButton variant="secondary" size="sm" disabled={offset + PAGE_SIZE >= total || loading} onClick={() => { setOffset(offset + PAGE_SIZE); setSelected([]); }}>Next leads</TactileButton></div></footer>
      </SolidCard>
      <CallbackRequests agentId={agentId} readOnly={readOnly} />
      {readOnly && <p className="text-meta text-fg-muted" role="status">You have view-only access: you can review leads and call history.</p>}
      <Modal isOpen={Boolean(detail)} onClose={closeDetail} title={detail?.name || 'Lead details'} subtitle="Contact details, notes and follow-up" maxWidth="max-w-2xl">
        {detail && <div className="space-y-5">
          <LeadPriority lead={detail} detailed />
          <dl className="grid grid-cols-1 gap-4 rounded-control border border-line bg-canvas p-4 text-ui sm:grid-cols-2">{[['Phone', detail.phone || 'Not provided'], ['Email', detail.email || 'Not provided'], ['Agent owner', ownerName(detail)], ['Created', formatDate(detail.createdAt)], ['Last updated', formatDate(detail.updatedAt)]].map(([label, value]) => <div key={label} className="min-w-0"><dt className="text-meta text-fg-muted">{label}</dt><dd className={`mt-1 break-words font-medium text-ink ${label === 'Phone' && detail.phone ? 'font-mono tabular-nums' : ''}`}>{value}</dd></div>)}</dl>
          <label className="block text-ui font-medium text-ink">Pipeline stage<select className={`${field} mt-1`} value={draft.stage} disabled={readOnly || Boolean(busy)} onChange={(event) => { setDraft((current) => ({ ...current, stage: event.target.value })); setConversionConfirmed(false); }}>{STAGES.map((stage) => <option key={stage} value={stage}>{statusWord(stage).label}</option>)}</select></label>
          {draft.stage === 'Converted' && detail.stage !== 'Converted' && <label className="flex items-start gap-3 rounded-control border border-success-line bg-success-soft p-4 text-copy text-success-fg"><input type="checkbox" checked={conversionConfirmed} disabled={readOnly || Boolean(busy)} onChange={(event) => setConversionConfirmed(event.target.checked)} className="mt-1 h-4 w-4 shrink-0" /><span>I confirm this lead became a customer.</span></label>}
          <label className="block text-ui font-medium text-ink">Notes & next step<textarea className={`${field} mt-1 min-h-36 leading-relaxed`} maxLength={20000} value={draft.notes} disabled={readOnly || Boolean(busy)} onChange={(event) => setDraft((current) => ({ ...current, notes: event.target.value }))} placeholder="What they need, what was discussed, and what should happen next." /></label>
          <p className="text-meta text-fg-muted">Notes are saved when you choose Save lead changes.</p>
          {detailError && <p role="alert" className="rounded-control border border-danger-line bg-danger-soft p-3 text-ui text-danger-fg">{detailError}</p>}
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4"><TactileButton variant="secondary" disabled={!detail.phone || Boolean(busy)} onClick={() => openHistory(detail)}>View recent calls</TactileButton><TactileButton disabled={readOnly || !detailDirty || Boolean(busy) || (draft.stage === 'Converted' && detail.stage !== 'Converted' && !conversionConfirmed)} loading={busy === 'save'} onClick={saveDetail}>Save lead changes</TactileButton></div>
          <section className="space-y-3 rounded-control border border-line p-4" aria-label="Call this lead"><h3 className="text-title text-ink">Follow up by phone</h3>
            {phoneNumbers.length > 0 && <label className="block text-meta font-medium text-fg-body">Call from<select className={`${field} mt-1`} value={outboundFromE164 || ''} onChange={(event) => setPreferredOutboundFrom(event.target.value)}><option value="">Agent’s own line</option>{phoneNumbers.filter((number) => number.status !== 'released').map((number) => <option key={number.id} value={number.number}>{number.formatted || number.number}</option>)}</select></label>}
            {!detail.agentId && <p className="rounded-control border border-warning-line bg-warning-soft px-3 py-2 text-meta text-warning-fg">Assign an agent when adding this lead, or select it for a campaign and choose who calls.</p>}
            <TactileButton icon={PhoneCall} disabled={readOnly || detail.doNotCall || !detail.phone || !detail.agentId || Boolean(busy) || detailDirty} loading={busy === detail.id} onClick={() => callLead(detail)}>Call lead</TactileButton>
            {detailDirty && <p className="text-meta text-fg-muted">Save your notes before starting a call.</p>}
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
          {['name', 'phone', 'email'].map((name) => <label key={name} className="block text-ui font-medium text-ink">{name === 'phone' ? 'Phone (with country code)' : name === 'name' ? 'Name' : 'Email'}<input className={`${field} mt-1`} required={name === 'name'} type={name === 'email' ? 'email' : name === 'phone' ? 'tel' : 'text'} maxLength={name === 'name' ? 255 : name === 'phone' ? 32 : 320} value={addForm[name]} disabled={readOnly || Boolean(busy)} onChange={(event) => setAddForm((current) => ({ ...current, [name]: event.target.value }))} /></label>)}
          {!agentId && <label className="block text-ui font-medium text-ink">Agent owner<select className={`${field} mt-1`} disabled={Boolean(busy)} value={addForm.agentId} onChange={(event) => setAddForm((current) => ({ ...current, agentId: event.target.value }))}><option value="">Unassigned</option>{agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></label>}
          <label className="block text-ui font-medium text-ink">Notes & next step<textarea className={`${field} mt-1 min-h-24`} maxLength={20000} value={addForm.notes} disabled={readOnly || Boolean(busy)} onChange={(event) => setAddForm((current) => ({ ...current, notes: event.target.value }))} /></label>
          {addError && <p role="alert" className="text-ui text-danger-fg">{addError}</p>}
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
