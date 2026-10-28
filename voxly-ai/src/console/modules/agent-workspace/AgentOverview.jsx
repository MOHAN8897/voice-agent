import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PhoneCall, TrendingUp, PhoneOff, Clock, Users, ArrowRight } from 'lucide-react';
import { SolidCard } from '../../ui/SolidCard';
import { StatusBadge } from '../../ui/StatusBadge';
import { TactileButton } from '../../ui/TactileButton';
import { api } from '../../../services/api';
import { callStatus, statusLabel } from '../../../lib/callStatus';

const RANGE_DAYS = { Today: 1, '7 days': 7, '30 days': 30 };

function formatMinutes(seconds) {
  const value = Math.max(0, Math.round(Number(seconds) || 0));
  if (value < 60) return `${value}s`;
  const mins = Math.floor(value / 60);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

function KpiCard({ icon: Icon, label, value, hint }) {
  return (
    <div className="p-4 rounded-2xl bg-white border border-[#E4E2EB]">
      <div className="flex items-center gap-2 mb-2">
        <Icon className="w-3.5 h-3.5 text-[#6344E7]" />
        <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A]">
          {label}
        </span>
      </div>
      <div className="text-2xl font-bold text-[#0F0E17] tabular-nums">{value}</div>
      {hint && <div className="text-[11px] text-[#8C879A] mt-0.5">{hint}</div>}
    </div>
  );
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
        api.calls.list({ agentId, since, limit: 25 }),
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
      <SolidCard className="p-6 text-center space-y-3">
        <p className="text-sm text-red-700">{error}</p>
        <TactileButton variant="secondary" size="sm" onClick={load}>
          Try again
        </TactileButton>
      </SolidCard>
    );
  }

  if (loading && !stats) {
    return (
      <SolidCard className="p-8 text-center">
        <p className="text-sm text-[#524E5E]">Loading {agent?.name || 'agent'} activity…</p>
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
          <h3 className="text-sm font-bold text-[#0F0E17]">{agent?.name}</h3>
          <p className="text-[11px] text-[#524E5E] mt-0.5">
            Call activity and pipeline for this agent only.
          </p>
        </div>
        <div
          className="flex items-center gap-1 p-1 rounded-xl bg-white border border-[#E4E2EB] w-fit"
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
              className={`px-3 py-1.5 rounded-lg text-[11px] font-bold transition-colors ${
                range === r ? 'bg-[#0F0E17] text-white' : 'text-[#524E5E] hover:bg-[#FAF9FD]'
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      {total === 0 ? (
        <SolidCard className="p-8 text-center space-y-2">
          <PhoneCall className="w-8 h-8 text-[#6344E7] mx-auto" />
          <p className="text-sm font-bold text-[#0F0E17]">No calls in this range</p>
          <p className="text-xs text-[#524E5E] max-w-md mx-auto">
            {agent?.name} has not taken or placed any calls in the last {days} day
            {days === 1 ? '' : 's'}. Place a test call, or attach a phone number to start
            receiving calls.
          </p>
        </SolidCard>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <KpiCard icon={PhoneCall} label="Calls" value={total} hint={`last ${days} day${days === 1 ? '' : 's'}`} />
          <KpiCard icon={TrendingUp} label="Connect rate" value={stats?.connectRate != null ? `${stats.connectRate}%` : total ? `${Math.round(connected * 100 / total)}%` : '—'} hint={`${connected} connected / ${total} attempts · may include voicemail`} />
          <KpiCard icon={PhoneOff} label="Missed" value={missed} hint="not answered" />
          <KpiCard
            icon={Clock}
            label="Avg duration"
            value={formatMinutes(stats?.avgDurationSec)}
            hint={`${stats?.completedConnected ?? connected} completed connections`}
          />
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" data-testid="agent-conversion-metrics">
        <KpiCard icon={Users} label="New leads" value={stats?.leadCount ?? '—'} hint="Created in this period" />
        <KpiCard icon={TrendingUp} label="Lead conversion" value={stats?.conversionRate != null ? `${stats.conversionRate}%` : '—'} hint={`${stats?.convertedLeads ?? 0} tenant-confirmed / ${stats?.leadCount ?? 0} period leads`} />
        <KpiCard icon={TrendingUp} label="Cost per lead" value={stats?.cost?.costPerLead != null ? new Intl.NumberFormat(undefined, { style: 'currency', currency: stats.cost.currency }).format(stats.cost.costPerLead) : '—'} hint={stats?.cost?.complete === false ? 'Waiting for settled call charges' : 'Period call charges / new leads'} />
        <KpiCard icon={Clock} label="Settled call spend" value={stats?.cost ? new Intl.NumberFormat(undefined, { style: 'currency', currency: stats.cost.currency }).format(stats.cost.settledSpend) : '—'} hint={stats?.cost?.complete === false ? 'Partial · some charges are pending' : 'Actual wallet charges in this call cohort'} />
      </div>
      <p className="text-xs leading-relaxed text-[#716C7F]">Test calls are excluded. Connected means an answered connection, which can include voicemail. Conversion uses leads created in this period and their current tenant-confirmed status. {range === 'Today' ? `Today starts at midnight in ${Intl.DateTimeFormat().resolvedOptions().timeZone}.` : ''}</p>
      <div className="grid lg:grid-cols-2 gap-4">
        <SolidCard>
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-xs font-bold text-[#0F0E17]">Recent calls</h4>
            <button
              type="button"
              onClick={() => onOpenTab?.('calls', 'history')}
              className="text-[11px] font-semibold text-[#5034CE] hover:underline inline-flex items-center gap-1"
            >
              All calls <ArrowRight className="w-3 h-3" />
            </button>
          </div>
          {recent.length === 0 ? (
            <p className="text-xs text-[#8C879A] py-4 text-center">No calls yet.</p>
          ) : (
            <div className="divide-y divide-[#E4E2EB]">
              {recent.slice(0, 6).map((c) => (
                <div key={c.id} className="flex items-center justify-between gap-3 py-2 text-xs">
                  <div className="min-w-0">
                    <div className="font-semibold text-[#0F0E17] truncate">
                      {c.callerName || c.callerPhone || 'Unknown caller'}
                    </div>
                    <div className="text-[10px] text-[#8C879A]">
                      {String(c.direction || '').toLowerCase()} · {c.duration || '—'}
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
            <h4 className="text-xs font-bold text-[#0F0E17]">Leads from this agent</h4>
            <button
              type="button"
              onClick={() => onOpenTab?.('calls', 'leads')}
              className="text-[11px] font-semibold text-[#5034CE] hover:underline inline-flex items-center gap-1"
            >
              Pipeline <ArrowRight className="w-3 h-3" />
            </button>
          </div>
          {!stats?.leadCount ? <p className="py-4 text-center text-xs text-[#8C879A]" data-testid="agent-overview-no-leads">No new leads recorded in this period.</p> : <><p className="mb-3 text-2xl font-bold">{stats.leadCount} <span className="text-xs font-normal text-[#716C7F]">new leads in this period</span></p><div className="flex flex-wrap gap-2">{Object.entries(stats.leadStageCounts || {}).map(([stage, count]) => <span key={stage} className="rounded-lg border border-[#E4E2EB] bg-[#FAF9FD] px-3 py-2 text-xs capitalize">{stage.replace(/_/g, ' ')} · {count}</span>)}</div></>}

        </SolidCard>
      </div>
    </div>
  );
}
