import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../../services/api';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';

export function CallbackRequests({ agentId = null }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(null);
  const [notice, setNotice] = useState('');
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
    <SolidCard>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-[#0F0E17]">Callback requests</h3>
          <p className="mt-1 text-xs text-[#524E5E]">People who asked to be contacted later. Review their requested time before calling. Calls start only when you choose Call back.</p>
        </div>
        <TactileButton type="button" variant="secondary" size="sm" onClick={load} disabled={loading || busy !== null}>Refresh</TactileButton>
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      {notice && <p role="status" className="mt-3 text-sm text-emerald-700">{notice}</p>}
      {loading ? <p role="status" className="mt-4 text-sm text-[#524E5E]">Loading callback requests…</p> : rows.length === 0 && !error ? (
        <p className="mt-4 text-sm text-[#524E5E]">No pending callback requests.</p>
      ) : (
        <ul className="mt-4 divide-y divide-[#E4E2EB]" data-testid="callback-request-list">
          {rows.map((row) => (
            <li key={row.id} className="flex flex-col justify-between gap-3 py-4 sm:flex-row sm:items-center">
              <div className="min-w-0">
                <p className="text-sm font-medium text-[#0F0E17]">{row.phone}</p>
                <p className="mt-1 break-words text-sm text-[#524E5E]">{row.requestedWhen}</p>
                {row.requestText && row.requestText !== row.requestedWhen && <p className="mt-1 break-words text-xs text-[#524E5E]">{row.requestText}</p>}
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                <TactileButton type="button" size="sm" variant="primary" disabled={busy !== null} onClick={() => callBack(row)}>Call back</TactileButton>
                <TactileButton type="button" size="sm" variant="secondary" disabled={busy !== null} onClick={() => resolve(row, 'converted')}>
                  {busy === row.id ? 'Saving…' : 'Mark converted'}
                </TactileButton>
                <TactileButton type="button" size="sm" variant="ghost" disabled={busy !== null} onClick={() => resolve(row, 'dismissed')}>Remove</TactileButton>
              </div>
            </li>
          ))}
        </ul>
      )}
    </SolidCard>
  );
}
