import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../../services/api';
import { outboundCallErrorMessage } from '../lib/outboundCall';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
import { EmptyState } from '../ui/EmptyState';
import { PhoneCall, RefreshCw, UserRound } from 'lucide-react';
import { Badge } from '../ui/StatusBadge';
import { useWorkspace } from '../context/WorkspaceContext';
import { NeedsYouItem } from './NeedsYouItem';
import { formatPhone } from '../../lib/phoneMask';
import { languagePrefix, phoneKey, useLanguageRequests } from '../lib/languageRequests';

export function CallbackRequests({ agentId = null, readOnly = false, onChange = null }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(null);
  const [notice, setNotice] = useState('');
  const { agents = [] } = useWorkspace();
  const agentName = (id) => (id ? agents.find((agent) => String(agent.id) === String(id))?.name || '' : '');
  const [revision, setRevision] = useState(0);
  // Callers who asked for another language carry that language on their request.
  const languages = useLanguageRequests(agentId, revision);
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const query = agentId ? `?agentId=${encodeURIComponent(agentId)}` : '';
      const data = await api.request('GET', `/api/callback-requests${query}`);
      setRows(data.requests || []);
    } catch (e) {
      setError(e.message || 'Could not load callback requests.');
    } finally {
      setLoading(false);
    }
  }, [agentId]);
  useEffect(() => { load(); }, [load]);
  const reload = () => { setRevision((value) => value + 1); load(); };

  const resolve = async (row, status) => {
    setBusy(row.id);
    setError('');
    setNotice('');
    try {
      await api.request('PATCH', `/api/callback-requests/${row.id}`, { status });
      setRows((current) => current.filter((item) => item.id !== row.id));
      onChange?.();
      setNotice(status === 'converted' ? 'Marked converted and removed from pending callbacks.'
        : row.kind === 'human_handoff' ? 'Marked handled and removed from pending requests.' : 'Removed from pending callbacks.');
    } catch (e) {
      setError(e.message || 'Could not update this callback. It is still in the list.');
    } finally {
      setBusy(null);
    }
  };

  const callBack = async (row) => {
    setBusy(row.id);
    setError('');
    setNotice('');
    try {
      const result = await api.request('POST', `/api/calls/${row.callId}/callback`, {
        agentId: row.agentId, toE164: row.phone, mode: 'manual', dialRequestId: crypto.randomUUID(),
      });
      if (result.ok === false) throw Object.assign(new Error('Could not start the callback. The request is still in the list.'), { code: result.code });
      setNotice('Callback requested. Keep this request until the follow-up is complete.');
    } catch (e) {
      setError(e?.code === 'voice_service_unavailable' ? outboundCallErrorMessage(e) : (e.message || 'Could not start the callback. The request is still in the list.'));
    } finally {
      setBusy(null);
    }
  };

  return (
    <SolidCard padding="p-0" className="min-w-0 overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-3 px-4 pt-4 sm:px-5 sm:pt-5">
        <div className="min-w-0 max-w-2xl">
          <h3 className="text-title text-ink">Callback requests</h3>
          <p className="mt-0.5 text-ui text-fg-muted">Callers who asked your agent to ring them back, or asked for a person from your team to call them. Calling back replaces any automatic follow-up, and a call that has already started is never placed twice. Automatic follow-ups are in Callbacks &amp; missed calls.</p>
        </div>
        <TactileButton type="button" variant="secondary" size="sm" icon={RefreshCw} onClick={reload} disabled={loading || busy !== null}>Refresh</TactileButton>
      </div>
      <div className="px-4 sm:px-5">
        {error && <p role="alert" className="mt-3 rounded-control border border-danger-line bg-danger-soft px-3 py-2 text-ui text-danger-fg">{error}</p>}
        {notice && <p role="status" className="mt-3 rounded-control border border-success-line bg-success-soft px-3 py-2 text-ui text-success-fg">{notice}</p>}
      </div>
      {loading ? <p role="status" className="px-4 py-6 text-ui text-fg-muted sm:px-5">Loading callback requests…</p> : rows.length === 0 && !error ? (
        <EmptyState compact icon={PhoneCall} title="No pending callback requests" description="When a caller asks to be rung back, the request shows up here." />
      ) : (
        <ul className="mt-3 divide-y divide-line border-t border-line" data-testid="callback-request-list">
          {rows.map((row) => {
            const agent = agentName(row.agentId);
            const wanted = languages.byPhone.get(phoneKey(row.phone));
            // A handoff asks for a person from the business, so the agent does not dial it.
            const handoff = row.kind === 'human_handoff' ? row.handoff || {} : null;
            const asked = row.requestedWhen && row.requestedWhen !== 'Requested during the call'
              ? `Asked for: ${row.requestedWhen}${row.resolvedWindow?.display ? ` → ${row.resolvedWindow.display}` : ''}` : null;
            return (
              <NeedsYouItem
                key={row.id}
                agentName={agent}
                icon={handoff ? UserRound : PhoneCall}
                tone="warning"
                needsYou
                data-kind={row.kind || 'callback'}
                language={wanted?.code}
                languageLabel={wanted?.label}
                languagePrefix={languagePrefix(wanted)}
                actor={<span className="font-mono tabular-nums">{formatPhone(row.phone) || row.phone}</span>}
                text={handoff ? `wants ${(handoff.contactLabel || 'a person from the business').replace(/^A /, 'a ')} to call them` : 'asked for a call back'}
                detail={handoff ? [handoff.reason && `Why: ${handoff.reason}`, asked].filter(Boolean).join(' · ') || null
                  : (row.requestedWhen ? `Asked for: ${row.requestedWhen}${row.resolvedWindow?.display ? ` → ${row.resolvedWindow.display}` : ''}` : null)}
                at={row.createdAt || null}
                meta={agent ? <span>· {agent}</span> : null}
                badges={handoff ? <Badge tone="info" size="xs">Person from your team</Badge> : null}
                actions={<>
                  {handoff ? (
                    <a href={`tel:${row.phone}`} className="inline-flex min-h-[36px] items-center justify-center gap-2 rounded-control border border-transparent bg-ink px-2.5 py-1 text-meta font-semibold text-white shadow-craft-xs hover:bg-[#232130] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent sm:min-h-0">
                      <PhoneCall size={14} aria-hidden="true" />Call them yourself
                    </a>
                  ) : (
                    <TactileButton type="button" size="xs" variant="primary" icon={PhoneCall} className="min-h-[36px] sm:min-h-0" disabled={readOnly || busy !== null} onClick={() => callBack(row)}>Call back</TactileButton>
                  )}
                  <TactileButton type="button" size="xs" variant="secondary" className="min-h-[36px] sm:min-h-0" disabled={readOnly || busy !== null} onClick={() => resolve(row, 'converted')}>
                    {busy === row.id ? 'Saving…' : 'Mark converted'}
                  </TactileButton>
                  <TactileButton type="button" size="xs" variant="ghost" className="min-h-[36px] sm:min-h-0" disabled={readOnly || busy !== null} onClick={() => resolve(row, 'dismissed')}>{handoff ? 'Mark handled' : 'Remove'}</TactileButton>
                </>}
              >
                {row.requestText && row.requestText !== row.requestedWhen && <p className="mt-0.5 text-ui text-fg-muted break-words">Caller said: “{row.requestText}”</p>}
              </NeedsYouItem>
            );
          })}
        </ul>
      )}
    </SolidCard>
  );
}
