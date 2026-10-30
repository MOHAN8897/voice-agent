import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../../services/api';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
import { EmptyState } from '../ui/EmptyState';
import { PhoneCall, RefreshCw } from 'lucide-react';
import { useWorkspace } from '../context/WorkspaceContext';
import { NeedsYouItem } from './NeedsYouItem';

export function CallbackRequests({ agentId = null, readOnly = false }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(null);
  const [notice, setNotice] = useState('');
  const { agents = [] } = useWorkspace();
  const agentName = (id) => (id ? agents.find((agent) => String(agent.id) === String(id))?.name || '' : '');
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

  const resolve = async (row, status) => {
    setBusy(row.id);
    setError('');
    setNotice('');
    try {
      await api.request('PATCH', `/api/callback-requests/${row.id}`, { status });
      setRows((current) => current.filter((item) => item.id !== row.id));
      setNotice(status === 'converted' ? 'Marked converted and removed from pending callbacks.' : 'Removed from pending callbacks.');
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
      if (result.ok === false) throw new Error('Could not start the callback. The request is still in the list.');
      setNotice('Callback requested. Keep this request until the follow-up is complete.');
    } catch (e) {
      setError(e.message || 'Could not start the callback. The request is still in the list.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <SolidCard padding="p-0" className="min-w-0 overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-3 px-4 pt-4 sm:px-5 sm:pt-5">
        <div className="min-w-0 max-w-2xl">
          <h3 className="text-title text-ink">Callback requests</h3>
          <p className="mt-0.5 text-ui text-fg-muted">Callers who asked your agent to ring them back. Calling back replaces any automatic follow-up, and a call that has already started is never placed twice. Automatic follow-ups are in Callbacks &amp; missed calls.</p>
        </div>
        <TactileButton type="button" variant="secondary" size="sm" icon={RefreshCw} onClick={load} disabled={loading || busy !== null}>Refresh</TactileButton>
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
            return (
              <NeedsYouItem
                key={row.id}
                agentName={agent}
                icon={PhoneCall}
                tone="warning"
                needsYou
                actor={<span className="font-mono tabular-nums">{row.phone}</span>}
                text="asked for a call back"
                detail={row.requestedWhen ? `Asked for: ${row.requestedWhen}` : null}
                at={row.createdAt || null}
                meta={agent ? <span>· {agent}</span> : null}
                actions={<>
                  <TactileButton type="button" size="xs" variant="primary" icon={PhoneCall} className="min-h-[36px] sm:min-h-0" disabled={readOnly || busy !== null} onClick={() => callBack(row)}>Call back</TactileButton>
                  <TactileButton type="button" size="xs" variant="secondary" className="min-h-[36px] sm:min-h-0" disabled={readOnly || busy !== null} onClick={() => resolve(row, 'converted')}>
                    {busy === row.id ? 'Saving…' : 'Mark converted'}
                  </TactileButton>
                  <TactileButton type="button" size="xs" variant="ghost" className="min-h-[36px] sm:min-h-0" disabled={readOnly || busy !== null} onClick={() => resolve(row, 'dismissed')}>Remove</TactileButton>
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
