import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PhoneCall, TrendingUp, PhoneOff, Clock, Users, ArrowRight } from 'lucide-react';
import { SolidCard } from '../../ui/SolidCard';
import { StatusBadge } from '../../ui/StatusBadge';
import { TactileButton } from '../../ui/TactileButton';
import { MetricCard } from '../../ui/MetricCard';
import { EmptyState } from '../../ui/EmptyState';
import { formatInr } from '../../../lib/money';
import { humanizeToken, statusWord } from '../../../lib/internalLabels';
import { api } from '../../../services/api';
import { useWorkspace } from '../../context/WorkspaceContext';
import { callStatus, statusLabel } from '../../../lib/callStatus';
import { AgentCallWarnings } from './AgentCallWarnings';

const RANGE_DAYS = { Today: 1, '7 days': 7, '30 days': 30 };

function formatMinutes(seconds) {
  const value = Math.max(0, Math.round(Number(seconds) || 0));
  if (value < 60) return `${value}s`;
  const mins = Math.floor(value / 60);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

function KpiCard({ icon, label, value, hint }) {
  return <MetricCard compact icon={icon} title={label} value={value} subtitle={hint} className="min-w-0" />;
}

function directionWord(direction) {
  const d = String(direction || '').toLowerCase();
  if (d.startsWith('in')) return 'Incoming';
  if (d.startsWith('out')) return 'Outgoing';
  return d ? humanizeToken(d) : 'Call';
}

function formatMoney(amount, currency) {
  if (amount == null) return '—';
  if (!currency || String(currency).toUpperCase() === 'INR') return formatInr(amount);
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency }).format(amount);
}

/**
 * Per-agent dashboard.
 *
 * Every number here comes from `/api/calls/stats?agentId=…` or from call/lead objects
 * already in the workspace. Nothing is estimated or invented — an agent with no
 * history says so rather than showing zeroes that look like a failed call.
 */
export function AgentOverview({ agent, onOpenTab }) {
  const loadSequence = useRef(0);
  // Name rows from the workspace's agents instead of an extra GET /api/agents per load.
  const { agents } = useWorkspace();
  const agentMapRef = useRef({});
  agentMapRef.current = useMemo(() => Object.fromEntries((agents || []).map((a) => [a.id, a])), [agents]);
  const [range, setRange] = useState('7 days');
  const [stats, setStats] = useState(null);
  const [recent, setRecent] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const agentId = agent?.id;
  const days = RANGE_DAYS[range] ?? 7;
  const since = useMemo(() => { const date = new Date(); if (range === 'Today') date.setHours(0, 0, 0, 0); else date.setTime(date.getTime() - days * 864e5); return date.toISOString(); }, [range, days]);

  const load = useCallback(async () => {
    if (!agentId) return;
    const request = ++loadSequence.current;
    setLoading(true);
    setError(null);
    try {
      const [statsRes, callRows] = await Promise.all([
        api.calls.stats({ agentId, since }),
        api.calls.list({ agentId, since, limit: 25, agentMap: agentMapRef.current }),
      ]);
      if (request !== loadSequence.current) return;
      setStats(statsRes);
      setRecent(callRows || []);
    } catch (e) {
      if (request !== loadSequence.current) return;
      setError(e.message || 'Could not load call history');
    } finally {
      if (request === loadSequence.current) setLoading(false);
    }
  }, [agentId, since]);

  useEffect(() => {
    load();
    return () => { loadSequence.current += 1; };
  }, [load]);

  if (error) {
    return (
      <SolidCard className="text-center space-y-3" role="alert">
        <p className="text-copy text-danger-fg">{error}</p>
        <TactileButton variant="secondary" size="sm" onClick={load}>
          Try again
        </TactileButton>
      </SolidCard>
    );
  }

  if (loading && !stats) {
    return (
      <SolidCard className="text-center" aria-busy="true">
        <p className="text-copy text-fg-muted">Loading {agent?.name || 'this employee'}’s activity…</p>
      </SolidCard>
    );
  }

  const total = Number(stats?.total) || 0;
  const connected = Number(stats?.connected) || 0;
  const missed = Number(stats?.missed) || 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h3 className="text-title text-ink">{agent?.name}</h3>
          <p className="text-ui text-fg-muted mt-0.5">
            Calls and leads for this employee only.
          </p>
        </div>
        <div
          className="inline-flex items-center gap-0.5 p-0.5 rounded-control bg-surface-subtle border border-line w-fit"
          role="group"
          aria-label="Date range"
        >
          {Object.keys(RANGE_DAYS).map((r) => (
            <button
              key={r}
              type="button"
              aria-pressed={range === r}
              data-testid={`agent-overview-range-${r.replace(' ', '')}`}
              onClick={() => setRange(r)}
              className={`px-3 py-1.5 min-h-[32px] rounded-[8px] text-ui font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                range === r ? 'bg-surface text-ink shadow-craft-xs' : 'text-fg-body hover:text-ink'
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      <AgentCallWarnings agent={agent} onOpenTab={onOpenTab} />

      {total === 0 ? (
        <SolidCard padding="p-0">
          <EmptyState
            compact
            icon={PhoneCall}
            title="No calls in this range"
            description={`${agent?.name || 'This employee'} has not taken or made any calls in the last ${days} day${days === 1 ? '' : 's'}. Place a test call, or give them a phone number to start taking calls.`}
          />
        </SolidCard>
      ) : (
        <div className="grid grid-cols-1 min-[420px]:grid-cols-2 lg:grid-cols-4 gap-3">
          <KpiCard icon={PhoneCall} label="Calls" value={total} hint={`last ${days} day${days === 1 ? '' : 's'}`} />
          <KpiCard icon={TrendingUp} label="Connect rate" value={stats?.connectRate != null ? `${stats.connectRate}%` : total ? `${Math.round(connected * 100 / total)}%` : '—'} hint={`${connected} of ${total} answered · may include voicemail`} />
          <KpiCard icon={PhoneOff} label="Missed" value={missed} hint="Not answered" />
          <KpiCard
            icon={Clock}
            label="Average call"
            value={formatMinutes(stats?.avgDurationSec)}
            hint={`${stats?.completedConnected ?? connected} completed calls`}
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 lg:grid-cols-4" data-testid="agent-conversion-metrics">
        <KpiCard icon={Users} label="New leads" value={stats?.leadCount ?? '—'} hint="Created in this period" />
        <KpiCard icon={TrendingUp} label="Lead conversion" value={stats?.conversionRate != null ? `${stats.conversionRate}%` : '—'} hint={`${stats?.convertedLeads ?? 0} of ${stats?.leadCount ?? 0} leads marked converted by you`} />
        <KpiCard icon={TrendingUp} label="Cost per lead" value={stats?.cost?.costPerLead != null ? formatMoney(stats.cost.costPerLead, stats.cost.currency) : '—'} hint={stats?.cost?.complete === false ? 'Waiting for settled call charges' : 'Call charges divided by new leads'} />
        <KpiCard icon={Clock} label="Spent on calls" value={stats?.cost ? formatMoney(stats.cost.settledSpend, stats.cost.currency) : '—'} hint={stats?.cost?.complete === false ? 'Some charges are still pending' : 'Charged to your wallet for these calls'} />
      </div>
      <p className="text-ui leading-relaxed text-fg-muted">Test calls are not counted. Answered calls can include voicemail. Conversion counts leads created in this period that you have marked as converted. {range === 'Today' ? `Today starts at midnight in ${Intl.DateTimeFormat().resolvedOptions().timeZone}.` : ''}</p>
      <div className="grid lg:grid-cols-2 gap-4">
        <SolidCard>
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-title text-ink">Recent calls</h4>
            <button
              type="button"
              onClick={() => onOpenTab?.('calls', 'history')}
              className="text-ui font-medium text-accent-fg hover:underline inline-flex items-center gap-1"
            >
              All calls <ArrowRight className="w-3 h-3" />
            </button>
          </div>
          {recent.length === 0 ? (
            <p className="text-ui text-fg-muted py-4 text-center">No calls yet.</p>
          ) : (
            <div className="divide-y divide-line">
              {recent.slice(0, 6).map((c) => (
                <div key={c.id} className="flex items-center justify-between gap-3 py-2 text-ui">
                  <div className="min-w-0">
                    <div className="font-medium text-ink truncate" title={c.callerName || c.callerPhone || undefined}>
                      {c.callerName || c.callerPhone || 'Unknown caller'}
                    </div>
                    <div className="text-meta text-fg-muted">
                      {directionWord(c.direction)} · <span className="font-mono tabular-nums">{c.duration || '—'}</span>
                    </div>
                  </div>
                  <StatusBadge status={statusLabel(callStatus(c))} size="xs" />
                </div>
              ))}
            </div>
          )}
        </SolidCard>

        <SolidCard>
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-title text-ink">Leads from this employee</h4>
            <button
              type="button"
              onClick={() => onOpenTab?.('calls', 'leads')}
              className="text-ui font-medium text-accent-fg hover:underline inline-flex items-center gap-1"
            >
              Pipeline <ArrowRight className="w-3 h-3" />
            </button>
          </div>
          {!stats?.leadCount ? <p className="py-4 text-center text-ui text-fg-muted" data-testid="agent-overview-no-leads">No new leads recorded in this period.</p> : <><p className="mb-3 text-heading text-ink"><span className="font-mono tabular-nums">{stats.leadCount}</span> <span className="text-ui font-normal text-fg-muted">new leads in this period</span></p><div className="flex flex-wrap gap-2">{Object.entries(stats.leadStageCounts || {}).map(([stage, count]) => <span key={stage} className="rounded-control border border-line bg-canvas px-3 py-2 text-ui text-fg-body">{statusWord(stage).label} · <span className="font-mono tabular-nums text-ink">{count}</span></span>)}</div></>}

        </SolidCard>
      </div>
    </div>
  );
}
