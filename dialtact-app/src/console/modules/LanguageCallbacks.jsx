import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Languages, PhoneCall, RefreshCw, Users } from 'lucide-react';
import { api } from '../../services/api';
import { useWorkspace } from '../context/WorkspaceContext';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
import { Modal } from '../ui/Modal';
import { Avatar } from '../ui/Avatar';
import { Badge } from '../ui/StatusBadge';
import { EmptyState } from '../ui/EmptyState';
import { NeedsYouItem } from './NeedsYouItem';
import { humanizeToken } from '../../lib/internalLabels';
import { contactName, formatPhone } from '../../lib/phoneMask';

const field = 'mt-1 block min-h-11 min-w-0 max-w-full rounded-control border border-line bg-surface px-3 py-2 text-base sm:text-ui text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15';
const STATUS_LABEL = { pending: 'Needs callback', calling: 'Callback placed', done: 'Done', dismissed: 'Removed' };
const STATUS_TONE = { pending: 'warning', calling: 'info', done: 'success', dismissed: 'neutral' };

function LanguageChip({ label, active = false, onClick, count }) {
  const cls = `inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-pill border px-3 text-ui font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${active ? 'border-ink bg-ink text-white' : 'border-line bg-surface text-fg-body hover:border-line-strong hover:text-ink'}`;
  if (!onClick) {
    return (
      <span className="inline-flex items-center gap-1 rounded-pill border border-accent-soft bg-accent-soft px-2 py-0.5 text-meta font-medium text-accent-fg">
        <Languages className="h-3 w-3" aria-hidden="true" />{label}
      </span>
    );
  }
  return (
    <button type="button" aria-pressed={active} onClick={onClick} className={cls}>
      {label}{typeof count === 'number' && <span className={`rounded-pill px-1.5 font-mono text-meta tabular-nums ${active ? 'bg-white/20 text-white' : 'bg-surface-subtle text-fg-body'}`}>{count}</span>}
    </button>
  );
}

/** "Callback needed in another language": callers who asked for a language the agent's pack doesn't speak. */
export function LanguageCallbacks({ agentId = null, readOnly = false }) {
  const { agents = [], outboundFromE164 } = useWorkspace();
  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState('open');
  const [language, setLanguage] = useState('');
  const [agentFilter, setAgentFilter] = useState(agentId || '');
  const [selected, setSelected] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [bulkOpen, setBulkOpen] = useState(false);
  const [consent, setConsent] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const params = new URLSearchParams({ status });
      if (agentFilter) params.set('agentId', agentFilter);
      const data = await api.request('GET', `/api/language-switch-requests?${params}`);
      setRows(data.requests || []);
      setSelected([]);
    } catch (e) {
      setError(e.message || 'Could not load language callbacks.');
    } finally {
      setLoading(false);
    }
  }, [status, agentFilter]);
  useEffect(() => { load(); }, [load]);

  const agentName = (id) => agents.find((agent) => String(agent.id) === String(id))?.name || 'Agent';
  const languageCounts = useMemo(() => rows.reduce((acc, row) => {
    acc[row.requestedLanguage] = { label: row.requestedLanguageLabel, count: (acc[row.requestedLanguage]?.count || 0) + 1 };
    return acc;
  }, {}), [rows]);
  const visible = language ? rows.filter((row) => row.requestedLanguage === language) : rows;
  const callable = visible.filter((row) => row.status === 'pending' || row.status === 'calling');
  const selectedRows = visible.filter((row) => selected.includes(row.id));

  const callNow = async (row) => {
    setBusy(row.id); setError(''); setNotice('');
    try {
      const ready = await api.request('GET', `/api/language-switch-requests/readiness?agentId=${encodeURIComponent(row.agentId)}&language=${encodeURIComponent(row.requestedLanguage)}`);
      if (!ready.ready) throw new Error(ready.message || `This agent can't call in ${row.requestedLanguageLabel} yet.`);
      const result = await api.request('POST', `/api/language-switch-requests/${row.id}/call`, outboundFromE164 ? { fromE164: outboundFromE164 } : {});
      if (result.ok === false) throw new Error(result.error || 'The call could not be placed. The request is still in the list.');
      setNotice(`Calling ${contactName(row.contactName, row.phone, 'this caller')} in ${row.requestedLanguageLabel} with ${agentName(row.agentId)}. It is marked done after a connected call in ${row.requestedLanguageLabel}.`);
      setRows((current) => current.map((item) => item.id === row.id ? { ...item, status: 'calling' } : item));
    } catch (e) {
      setError(e.message || 'Could not start the call.');
    } finally {
      setBusy('');
    }
  };

  const setRowStatus = async (row, next) => {
    setBusy(row.id); setError(''); setNotice('');
    try {
      const updated = await api.request('PATCH', `/api/language-switch-requests/${row.id}`, { status: next });
      setRows((current) => (status === 'open' && next !== 'pending'
        ? current.filter((item) => item.id !== row.id)
        : current.map((item) => item.id === row.id ? updated : item)));
      setNotice(next === 'done' ? 'Marked done.' : 'Removed from the list.');
    } catch (e) {
      setError(e.message || 'Could not update this request.');
    } finally {
      setBusy('');
    }
  };

  const createCampaign = async () => {
    setBusy('bulk'); setError(''); setNotice('');
    try {
      const result = await api.request('POST', '/api/language-switch-requests/campaign', {
        ids: selectedRows.map((row) => row.id), consentConfirmed: consent, autoStart: true,
        name: language ? `${languageCounts[language]?.label || language} callbacks` : 'Language callbacks',
        ...(outboundFromE164 ? { fromE164: outboundFromE164 } : {}),
      });
      const total = (result.campaigns || []).reduce((sum, c) => sum + (c.contacts || 0), 0);
      setNotice(`Started ${result.campaigns?.length || 0} campaign${result.campaigns?.length === 1 ? '' : 's'} for ${total} contact${total === 1 ? '' : 's'}. Each contact is called in the language they asked for. Track progress in Campaigns.`);
      setBulkOpen(false); setConsent(false);
      await load();
    } catch (e) {
      setError(e.message || 'Could not create the campaign.');
    } finally {
      setBusy('');
    }
  };

  const toggle = (row) => setSelected((current) => current.includes(row.id) ? current.filter((id) => id !== row.id) : [...current, row.id]);
  const allSelected = callable.length > 0 && callable.every((row) => selected.includes(row.id));

  return (
    <SolidCard padding="p-0" className="min-w-0 overflow-hidden" data-testid="language-callbacks">
      <div className="space-y-4 px-4 pt-4 sm:px-5 sm:pt-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 max-w-2xl gap-3">
            <Avatar icon={Languages} tone="accent" size="sm" />
            <div className="min-w-0">
              <h3 className="text-title text-ink">Callback needed in another language</h3>
              <p className="mt-0.5 text-ui text-fg-muted">
                These callers asked to talk in a language their agent doesn’t speak. The agent promised a call back and
                ended politely. When you call back, the same agent speaks, listens and opens in the caller’s language.
                The request is marked done after a connected call in that language, and the caller’s language is remembered.
              </p>
            </div>
          </div>
          <TactileButton type="button" variant="secondary" size="sm" icon={RefreshCw} onClick={load} disabled={loading || Boolean(busy)}>Refresh</TactileButton>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <label className="min-w-0 text-meta font-medium text-fg-body">Status
            <select className={field} value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="open">Needs callback</option><option value="done">Done</option><option value="dismissed">Removed</option><option value="all">All</option>
            </select>
          </label>
          {!agentId && (
            <label className="min-w-0 text-meta font-medium text-fg-body">Agent
              <select className={field} value={agentFilter} onChange={(event) => setAgentFilter(event.target.value)}>
                <option value="">All agents</option>{agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
              </select>
            </label>
          )}
        </div>
        {Object.keys(languageCounts).length > 0 && (
          <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 no-scrollbar" role="group" aria-label="Filter by requested language">
            <LanguageChip label="All languages" active={!language} count={rows.length} onClick={() => { setLanguage(''); setSelected([]); }} />
            {Object.entries(languageCounts).map(([code, info]) => (
              <LanguageChip key={code} label={info.label} count={info.count} active={language === code} onClick={() => { setLanguage(code); setSelected([]); }} />
            ))}
          </div>
        )}

        {error && <p role="alert" className="rounded-control border border-danger-line bg-danger-soft p-3 text-ui text-danger-fg">{error}</p>}
        {notice && <p role="status" className="rounded-control border border-success-line bg-success-soft p-3 text-ui text-success-fg">{notice}</p>}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3">
          <label className="flex min-h-11 items-center gap-2 text-ui text-fg-body sm:min-h-0">
            <input type="checkbox" className="h-4 w-4 accent-accent" disabled={readOnly || !callable.length} checked={allSelected}
              onChange={(event) => setSelected(event.target.checked ? callable.map((row) => row.id) : [])} />
            Select all{language ? ` ${languageCounts[language]?.label || ''}` : ''} requests ({callable.length})
          </label>
          <TactileButton type="button" variant="brand" size="sm" icon={Users} disabled={readOnly || !selectedRows.length || Boolean(busy)} onClick={() => setBulkOpen(true)}>
            Call all selected{selectedRows.length ? ` (${selectedRows.length})` : ''}
          </TactileButton>
        </div>
      </div>

      {loading ? <p role="status" className="px-4 py-6 text-ui text-fg-muted sm:px-5">Loading language callbacks…</p> : visible.length === 0 && !error ? (
        <EmptyState compact icon={Languages} title="Nobody is waiting" description="No callers are waiting for a call in another language." />
      ) : (
        <ul className="mt-3 divide-y divide-line border-t border-line" data-testid="language-callback-list">
          {visible.map((row) => {
            const open = row.status === 'pending' || row.status === 'calling';
            const who = contactName(row.contactName, null, 'Caller');
            const agent = agentName(row.agentId);
            return (
              <NeedsYouItem
                key={row.id}
                tone={row.error ? 'danger' : 'warning'}
                needsYou={row.status === 'pending'}
                leading={
                  <input type="checkbox" aria-label={`Select ${contactName(row.contactName, row.phone, 'caller')}`} className="mt-2 h-4 w-4 shrink-0 accent-accent"
                    disabled={readOnly || !open} checked={selected.includes(row.id)} onChange={() => toggle(row)} />
                }
                agentName={agent}
                actor={who}
                text={`wants a call back in ${row.requestedLanguageLabel}`}
                detail={<><span className="font-mono tabular-nums">{formatPhone(row.phone) || row.phone}</span> · spoke {row.originalLanguageLabel} with {agent}</>}
                at={row.createdAt || null}
                badges={<>
                  <LanguageChip label={`Wants ${row.requestedLanguageLabel}`} />
                  <Badge tone={STATUS_TONE[row.status] || 'neutral'} size="xs">{STATUS_LABEL[row.status] || humanizeToken(row.status)}</Badge>
                </>}
                actions={open ? <>
                  <TactileButton type="button" size="xs" variant="primary" icon={PhoneCall} className="min-h-[36px] sm:min-h-0" disabled={readOnly || Boolean(busy)} onClick={() => callNow(row)}>
                    {busy === row.id ? 'Checking…' : `Call now in ${row.requestedLanguageLabel}`}
                  </TactileButton>
                  <TactileButton type="button" size="xs" variant="secondary" className="min-h-[36px] sm:min-h-0" disabled={readOnly || Boolean(busy)} onClick={() => setRowStatus(row, 'done')}>Mark done</TactileButton>
                  <TactileButton type="button" size="xs" variant="ghost" className="min-h-[36px] sm:min-h-0" disabled={readOnly || Boolean(busy)} onClick={() => setRowStatus(row, 'dismissed')}>Remove</TactileButton>
                </> : null}
              >
                {row.requestText && <p className="mt-0.5 break-words text-ui text-fg-body">Caller said: “{row.requestText}”</p>}
                {row.error && <p className="mt-0.5 text-ui text-danger-fg">Last attempt: {row.error}</p>}
              </NeedsYouItem>
            );
          })}
        </ul>
      )}

      <Modal isOpen={bulkOpen} onClose={() => setBulkOpen(false)} title="Call selected contacts in their language" subtitle="Creates one campaign per agent and starts it now" maxWidth="max-w-lg">
        <div className="space-y-4 text-copy text-fg-body">
          <p><span className="font-mono tabular-nums">{selectedRows.length}</span> contact{selectedRows.length === 1 ? '' : 's'} will be called by the same agent that took their call, each in the language they asked for:</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(selectedRows.reduce((acc, row) => ({ ...acc, [row.requestedLanguageLabel]: (acc[row.requestedLanguageLabel] || 0) + 1 }), {}))
              .map(([label, count]) => <LanguageChip key={label} label={`${label} · ${count}`} />)}
          </div>
          <p>Calling hours, retries and the do-not-call list apply as for any campaign. If an agent can’t speak one of these languages yet, nothing is created and you’ll see why.</p>
          <label className="flex items-start gap-3 rounded-control border border-line p-3">
            <input type="checkbox" className="mt-0.5 h-4 w-4 shrink-0 accent-accent" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
            <span>These callers asked for this callback, and I have consent to call them.</span>
          </label>
          <div className="flex justify-end gap-2">
            <TactileButton type="button" variant="secondary" onClick={() => setBulkOpen(false)}>Cancel</TactileButton>
            <TactileButton type="button" variant="brand" disabled={!consent || busy === 'bulk'} onClick={createCampaign}>{busy === 'bulk' ? 'Creating…' : 'Start calls'}</TactileButton>
          </div>
        </div>
      </Modal>
    </SolidCard>
  );
}
