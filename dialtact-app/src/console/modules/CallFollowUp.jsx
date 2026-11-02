import React, { useEffect, useState } from 'react';
import { CalendarClock, UserRound } from 'lucide-react';
import { api } from '../../services/api';
import { Badge, StatusBadge } from '../ui/StatusBadge';
import { LeadPriority } from './LeadPriority';
import { relativeTime } from '../../lib/money';

const digits = (value) => String(value || '').replace(/\D/g, '').slice(-10);

/**
 * What this call left to do, from the same records Leads uses: the callback the
 * caller asked for on this call and the lead for this caller's number. Shown next
 * to the recording and transcript so a call can be followed up from History.
 */
export function CallFollowUp({ call }) {
  const [requests, setRequests] = useState([]);
  const [lead, setLead] = useState(null);
  const phone = digits(call?.callerPhone);

  useEffect(() => {
    if (!call?.id || !call.connected) {
      setRequests([]);
      return undefined;
    }
    let cancelled = false;
    const query = call.agentId ? `?agentId=${encodeURIComponent(call.agentId)}` : '';
    api.request('GET', `/api/callback-requests${query}`)
      .then((data) => {
        if (!cancelled) setRequests((data?.requests || []).filter((row) => String(row.callId) === String(call.id)));
      })
      .catch(() => { if (!cancelled) setRequests([]); });
    return () => { cancelled = true; };
  }, [call?.id, call?.agentId, call?.connected]);

  useEffect(() => {
    if (phone.length < 10) {
      setLead(null);
      return undefined;
    }
    let cancelled = false;
    api.leads.listPage({ search: phone, limit: 5 })
      .then((page) => {
        if (!cancelled) setLead((page?.leads || []).find((row) => digits(row.phone) === phone) || null);
      })
      .catch(() => { if (!cancelled) setLead(null); });
    return () => { cancelled = true; };
  }, [phone]);

  if (!lead && requests.length === 0) return null;
  return (
    <div className="space-y-3 rounded-control border border-line bg-canvas p-3.5" data-testid="call-follow-up">
      <div className="text-ui font-semibold text-ink">Follow-up</div>

      {requests.map((row) => {
        const handoff = row.kind === 'human_handoff';
        const when = row.requestedWhen
          ? `${row.requestedWhen}${row.resolvedWindow?.display ? ` → ${row.resolvedWindow.display}` : ''}`
          : null;
        return (
          <div key={row.id} className="space-y-1 rounded-control border border-warning-line bg-warning-soft p-3" data-testid="call-callback-request">
            <p className="flex flex-wrap items-center gap-2 text-ui font-medium text-ink">
              {handoff ? <UserRound className="h-4 w-4 text-warning-fg" aria-hidden="true" /> : <CalendarClock className="h-4 w-4 text-warning-fg" aria-hidden="true" />}
              {handoff ? 'Asked for a person from your team to call back' : 'Asked for a call back'}
              <Badge tone="warning" size="xs">Waiting</Badge>
            </p>
            {when && <p className="text-meta text-fg-body">Asked for: {when}</p>}
            {row.requestText && row.requestText !== row.requestedWhen && (
              <p className="text-meta text-fg-muted break-words">Caller said: “{row.requestText}”</p>
            )}
            <p className="text-meta text-fg-muted">
              {row.createdAt ? `Requested ${relativeTime(row.createdAt)}. ` : ''}Call back or close it in Leads, under Callbacks &amp; missed calls.
            </p>
          </div>
        );
      })}

      {lead && (
        <div className="space-y-1.5" data-testid="call-lead">
          <p className="flex flex-wrap items-center gap-2 text-ui text-fg-body">
            <span className="font-medium text-ink">{lead.name}</span>
            <StatusBadge status={lead.stage} size="xs" />
          </p>
          <LeadPriority lead={lead} />
          {lead.notes && <p className="text-meta text-fg-body break-words whitespace-pre-line">{lead.notes}</p>}
        </div>
      )}
    </div>
  );
}
