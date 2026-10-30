import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Languages, PhoneCall, RefreshCw, Users } from 'lucide-react';
import { api } from '../../services/api';
import { useWorkspace } from '../context/WorkspaceContext';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
import { Modal } from '../ui/Modal';

const field = 'min-h-11 rounded-xl border border-[#E4E2EB] bg-white px-3 py-2 text-sm text-[#0F0E17] focus:outline-none focus:ring-2 focus:ring-[#6344E7]/30';
const STATUS_LABEL = { pending: 'Needs callback', calling: 'Callback placed', done: 'Done', dismissed: 'Removed' };
const STATUS_STYLE = {
  pending: 'border-[#FDE68A] bg-[#FFFBEB] text-[#92400E]',
  calling: 'border-[#BFDBFE] bg-[#EFF6FF] text-[#1E40AF]',
  done: 'border-[#A7F3D0] bg-[#ECFDF5] text-[#047857]',
  dismissed: 'border-[#E4E2EB] bg-[#F0EEF6] text-[#524E5E]',
};
const formatDate = (value) => {
  const date = new Date(value);
  return value && Number.isFinite(date.getTime())
    ? date.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
    : 'Not recorded';
};

function LanguageChip({ label, active = false, onClick, count }) {
  const cls = `inline-flex min-h-9 items-center gap-1.5 rounded-full border px-3 text-xs font-semibold ${active ? 'border-[#6344E7] bg-[#6344E7] text-white' : 'border-[#DDD6FE] bg-[#F5F3FF] text-[#5B21B6]'}`;
  if (!onClick) return <span className={cls}><Languages className="h-3.5 w-3.5" aria-hidden="true" />{label}</span>;
  return (
    <button type="button" aria-pressed={active} onClick={onClick} className={cls}>
      {label}{typeof count === 'number' && <span className={active ? 'text-white/80' : 'text-[#7C6BC4]'}>{count}</span>}
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
      setNotice(`Calling ${row.contactName || row.phone} in ${row.requestedLanguageLabel} with ${agentName(row.agentId)}. It is marked done after a connected call in ${row.requestedLanguageLabel}.`);
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
    <SolidCard className="space-y-4" data-testid="language-callbacks">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 max-w-2xl">
          <h3 className="text-base font-semibold text-[#0F0E17]">Callback needed in another language</h3>
          <p className="mt-1 text-sm text-[#524E5E]">
            These callers asked to speak a different language from the agent's. The agent stayed in its own language,
            promised a call back in theirs and ended politely. Call them back with the same agent: the call uses the
            requested language for the script, speech recognition, voice and opening line. A request is marked done
            after a connected call in that language, and the contact's language is remembered.
          </p>
        </div>
        <TactileButton type="button" variant="secondary" size="sm" icon={RefreshCw} onClick={load} disabled={loading || Boolean(busy)}>Refresh</TactileButton>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs font-medium text-[#524E5E]">Status
          <select className={`${field} mt-1 block`} value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="open">Needs callback</option><option value="done">Done</option><option value="dismissed">Removed</option><option value="all">All</option>
          </select>
        </label>
        {!agentId && (
          <label className="text-xs font-medium text-[#524E5E]">Agent
            <select className={`${field} mt-1 block`} value={agentFilter} onChange={(event) => setAgentFilter(event.target.value)}>
              <option value="">All agents</option>{agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
            </select>
          </label>
        )}
      </div>
      {Object.keys(languageCounts).length > 0 && (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by requested language">
          <LanguageChip label="All languages" active={!language} count={rows.length} onClick={() => { setLanguage(''); setSelected([]); }} />
          {Object.entries(languageCounts).map(([code, info]) => (
            <LanguageChip key={code} label={info.label} count={info.count} active={language === code} onClick={() => { setLanguage(code); setSelected([]); }} />
          ))}
        </div>
      )}

      {error && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      {notice && <p role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#E4E2EB] pt-3">
        <label className="flex items-center gap-2 text-xs text-[#524E5E]">
          <input type="checkbox" className="h-4 w-4 accent-[#6344E7]" disabled={readOnly || !callable.length} checked={allSelected}
            onChange={(event) => setSelected(event.target.checked ? callable.map((row) => row.id) : [])} />
          Select all{language ? ` ${languageCounts[language]?.label || ''}` : ''} requests ({callable.length})
        </label>
        <TactileButton type="button" variant="brand" size="sm" icon={Users} disabled={readOnly || !selectedRows.length || Boolean(busy)} onClick={() => setBulkOpen(true)}>
          Call all selected{selectedRows.length ? ` (${selectedRows.length})` : ''}
        </TactileButton>
      </div>

      {loading ? <p role="status" className="text-sm text-[#524E5E]">Loading language callbacks…</p> : visible.length === 0 && !error ? (
        <p className="rounded-xl border border-dashed border-[#E4E2EB] p-6 text-center text-sm text-[#716C7F]">No callers are waiting for a call in another language.</p>
      ) : (
        <ul className="divide-y divide-[#E4E2EB]" data-testid="language-callback-list">
          {visible.map((row) => {
            const open = row.status === 'pending' || row.status === 'calling';
            return (
              <li key={row.id} className="flex flex-col gap-3 py-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex min-w-0 items-start gap-3">
                  <input type="checkbox" aria-label={`Select ${row.contactName || row.phone}`} className="mt-1 h-4 w-4 shrink-0 accent-[#6344E7]"
                    disabled={readOnly || !open} checked={selected.includes(row.id)} onChange={() => toggle(row)} />
                  <div className="min-w-0 space-y-1.5">
                    <p className="text-sm font-semibold text-[#0F0E17]">{row.contactName || 'Caller'} <span className="font-mono text-xs font-normal text-[#524E5E]">{row.phone}</span></p>
                    <div className="flex flex-wrap items-center gap-2">
                      <LanguageChip label={`Wants ${row.requestedLanguageLabel}`} />
                      <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-semibold ${STATUS_STYLE[row.status] || STATUS_STYLE.dismissed}`}>{STATUS_LABEL[row.status] || row.status}</span>
                    </div>
                    <p className="text-xs text-[#716C7F]">{agentName(row.agentId)} · spoke {row.originalLanguageLabel} · {formatDate(row.createdAt)}</p>
                    {row.requestText && <p className="break-words text-xs text-[#524E5E]">Caller said: “{row.requestText}”</p>}
                    {row.error && <p className="text-xs text-red-700">Last attempt: {row.error}</p>}
                  </div>
                </div>
                {open && (
                  <div className="flex shrink-0 flex-wrap gap-2">
                    <TactileButton type="button" size="sm" variant="primary" icon={PhoneCall} disabled={readOnly || Boolean(busy)} onClick={() => callNow(row)}>
                      {busy === row.id ? 'Checking…' : `Call now in ${row.requestedLanguageLabel}`}
                    </TactileButton>
                    <TactileButton type="button" size="sm" variant="secondary" disabled={readOnly || Boolean(busy)} onClick={() => setRowStatus(row, 'done')}>Mark done</TactileButton>
                    <TactileButton type="button" size="sm" variant="ghost" disabled={readOnly || Boolean(busy)} onClick={() => setRowStatus(row, 'dismissed')}>Remove</TactileButton>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <Modal isOpen={bulkOpen} onClose={() => setBulkOpen(false)} title="Call selected contacts in their language" subtitle="Creates one campaign per agent and starts it now" maxWidth="max-w-lg">
        <div className="space-y-4 text-sm text-[#524E5E]">
          <p>{selectedRows.length} contact{selectedRows.length === 1 ? '' : 's'} will be called by the same agent that took their call, each in the language they asked for:</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(selectedRows.reduce((acc, row) => ({ ...acc, [row.requestedLanguageLabel]: (acc[row.requestedLanguageLabel] || 0) + 1 }), {}))
              .map(([label, count]) => <LanguageChip key={label} label={`${label} · ${count}`} />)}
          </div>
          <p>Calling hours, retries and the Do Not Call list apply as for any campaign. If an agent can't speak one of these languages yet, nothing is created and you'll see why.</p>
          <label className="flex items-start gap-3 rounded-xl border border-[#E4E2EB] p-3">
            <input type="checkbox" className="mt-0.5 h-4 w-4 shrink-0 accent-[#6344E7]" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
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
