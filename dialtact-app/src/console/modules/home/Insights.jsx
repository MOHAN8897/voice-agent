import React, { useMemo, useState } from 'react';
import { Bot, ChevronDown, ChevronRight, Clock, PhoneCall, Users } from 'lucide-react';
import { MetricCard } from '../../ui/MetricCard';
import { Section } from '../../ui/SolidCard';
import { Tabs } from '../../ui/Tabs';
import { DataTable } from '../../ui/DataTable';
import { StatusBadge, Badge } from '../../ui/StatusBadge';
import { dispositionLabel, statusWord } from '../../../lib/internalLabels';
import { walletAmounts } from '../../../lib/money';

const RANGE_DAYS = { today: 1, '7d': 7, '30d': 30 };
const STORAGE_KEY = 'dialtact:home-insights-open:v1';

function readOpen() {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

/**
 * Everything the previous Overview page showed, kept intact under one
 * collapsible "Insights" section on the home feed: the five headline numbers,
 * the call activity chart (today / 7 / 30 days, incoming vs outgoing), recent
 * calls with Inspect, and recent leads.
 */
export function Insights({ agents, calls, leads, wallet, onNavigate, onInspectCall }) {
  const [open, setOpen] = useState(readOpen);
  const [range, setRange] = useState('today');

  const toggle = () => {
    setOpen((value) => {
      try {
        localStorage.setItem(STORAGE_KEY, String(!value));
      } catch {
        /* storage unavailable */
      }
      return !value;
    });
  };

  const callsInRange = useMemo(() => {
    const cutoff = Date.now() - (RANGE_DAYS[range] ?? 1) * 24 * 60 * 60 * 1000;
    return calls.filter((c) => {
      const t = new Date(c.startedAt || c.started_at || 0).getTime();
      return !Number.isNaN(t) && t >= cutoff;
    });
  }, [calls, range]);

  const hourlyData = useMemo(() => {
    const buckets = {};
    for (let h = 8; h <= 17; h += 1) {
      const label = `${String(h).padStart(2, '0')}:00`;
      buckets[label] = { hour: label, inbound: 0, outbound: 0 };
    }
    for (const c of callsInRange) {
      const d = new Date(c.startedAt || c.started_at);
      if (Number.isNaN(d.getTime())) continue;
      const label = `${String(d.getHours()).padStart(2, '0')}:00`;
      if (!buckets[label]) buckets[label] = { hour: label, inbound: 0, outbound: 0 };
      if ((c.direction || '').toLowerCase() === 'outbound') buckets[label].outbound += 1;
      else buckets[label].inbound += 1;
    }
    return Object.values(buckets).sort((a, b) => a.hour.localeCompare(b.hour));
  }, [callsInRange]);

  const maxCalls = Math.max(1, ...hourlyData.map((d) => d.inbound + d.outbound));
  const inboundTotal = hourlyData.reduce((a, b) => a + b.inbound, 0);
  const outboundTotal = hourlyData.reduce((a, b) => a + b.outbound, 0);

  const totalMinutes = useMemo(
    () =>
      calls.reduce((acc, c) => {
        const seconds = Number(c.durationSec);
        if (Number.isFinite(seconds) && seconds > 0) return acc + Math.round(seconds / 60);
        const m = parseInt(String(c.duration || '0').split('m')[0], 10);
        return acc + (Number.isFinite(m) ? m : 0);
      }, 0),
    [calls]
  );
  const money = walletAmounts(wallet);
  const activeAgents = agents.filter((a) => a.status === 'active').length;

  return (
    <section aria-labelledby="home-insights-title" className="rounded-card border border-line bg-surface shadow-craft-xs">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls="home-insights-body"
        data-testid="home-insights-toggle"
        className="flex w-full items-center justify-between gap-3 rounded-card px-4 py-3.5 sm:px-5 text-left hover:bg-canvas focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <span>
          <span id="home-insights-title" className="block text-title text-ink">Insights</span>
          <span className="block text-ui text-fg-muted">Totals, call activity by hour, recent calls and leads</span>
        </span>
        <ChevronDown className={`h-5 w-5 shrink-0 text-fg-body transition-transform motion-reduce:transition-none ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div id="home-insights-body" className="space-y-5 border-t border-line p-4 sm:p-5">
          <div className="grid grid-cols-1 min-[420px]:grid-cols-2 gap-3 lg:grid-cols-3 2xl:grid-cols-5">
            <MetricCard compact title="Total calls" value={String(calls.length)} trendLabel="Recent call history" icon={PhoneCall} />
            <MetricCard compact title="Talk time" value={`${totalMinutes} min`} trendLabel="Across recent calls" icon={Clock} />
            <MetricCard
              compact
              title="Wallet minutes"
              value={String(Number(wallet?.remainingMinutes || 0))}
              trendLabel={`${money.primary} left`}
              icon={Clock}
            />
            <MetricCard compact title="Leads in pipeline" value={String(leads.length)} trendLabel="All stages" icon={Users} onClick={() => onNavigate('leads')} />
            <MetricCard
              compact
              title="Active agents"
              value={String(activeAgents)}
              trendLabel={`${agents.length} in total`}
              icon={Bot}
              onClick={() => onNavigate('employees')}
            />
          </div>

          <Section
            className="min-w-0"
            padding="p-4 sm:p-5"
            headingLevel={3}
            title="Call activity"
            description="Incoming and outgoing calls by hour"
            actions={
              <Tabs
                label="Time range"
                value={range}
                onChange={setRange}
                size="sm"
                items={[
                  { id: 'today', label: 'Today' },
                  { id: '7d', label: '7 days' },
                  { id: '30d', label: '30 days' },
                ]}
              />
            }
          >
            <div className="flex h-44 items-end justify-between gap-1.5 pt-6" role="img" aria-label={`${inboundTotal} incoming and ${outboundTotal} outgoing calls in this range`}>
              {hourlyData.map((d) => (
                <div key={d.hour} className="group relative flex h-full flex-1 flex-col items-center justify-end gap-1.5">
                  <div className="pointer-events-none absolute -top-1 z-10 whitespace-nowrap rounded-control bg-ink px-2 py-1 text-meta text-white opacity-0 transition-opacity group-hover:opacity-100">
                    {d.hour}: {d.inbound} in · {d.outbound} out
                  </div>
                  <div className="flex h-full w-full flex-col items-center justify-end gap-0.5">
                    <div style={{ height: `${(d.outbound / maxCalls) * 100}%` }} className="w-full max-w-[18px] rounded-t-sm bg-accent" />
                    <div style={{ height: `${(d.inbound / maxCalls) * 100}%` }} className="w-full max-w-[18px] rounded-b-sm bg-ink" />
                  </div>
                  <span className="text-meta font-mono text-fg-muted hidden sm:block">{d.hour.slice(0, 2)}</span>
                </div>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-center gap-x-6 gap-y-1 border-t border-line pt-3 text-ui text-fg-body">
              <span className="flex items-center gap-2"><span className="h-3 w-3 rounded-sm bg-ink" />Incoming ({inboundTotal})</span>
              <span className="flex items-center gap-2"><span className="h-3 w-3 rounded-sm bg-accent" />Outgoing ({outboundTotal})</span>
            </div>
          </Section>

          <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
            <Section
              className="min-w-0 xl:col-span-2"
              padding="p-4 sm:p-5"
              headingLevel={3}
              title="Recent calls"
              description="Open a call to read the transcript or play the recording"
              actions={
                <button type="button" onClick={() => onNavigate('calls')} className="inline-flex items-center gap-1 text-ui font-medium text-accent-fg hover:underline">
                  All calls <ChevronRight className="h-4 w-4" />
                </button>
              }
            >
              <DataTable
                caption="Recent calls"
                columns={[
                  { key: 'contact', header: 'Contact' },
                  { key: 'agent', header: 'Agent' },
                  { key: 'direction', header: 'Direction' },
                  { key: 'duration', header: 'Duration', numeric: true },
                  { key: 'outcome', header: 'Outcome' },
                  { key: 'action', header: <span className="sr-only">Action</span> },
                ]}
                rows={calls.slice(0, 4)}
                empty={{ title: 'No calls yet', description: 'Calls your agents make or take will appear here.' }}
                renderCell={(call, column) => {
                  switch (column.key) {
                    case 'contact':
                      return (
                        <div className="min-w-0">
                          <div className="font-medium text-ink truncate">{call.customer || call.callerName}</div>
                          <div className="text-meta font-mono text-fg-muted">{call.callerPhone || '—'}</div>
                        </div>
                      );
                    case 'agent':
                      return call.agentName;
                    case 'direction':
                      return <StatusBadge status={call.direction} size="xs" />;
                    case 'duration':
                      return call.duration;
                    case 'outcome':
                      return (
                        <span className="block max-w-[200px] truncate">
                          {dispositionLabel(call.disposition) || call.summary || statusWord(call.status).label}
                        </span>
                      );
                    case 'action':
                      return (
                        <button type="button" onClick={() => onInspectCall(call.id)} className="text-ui font-medium text-accent-fg hover:underline">
                          Inspect
                        </button>
                      );
                    default:
                      return null;
                  }
                }}
              />
            </Section>

            <Section
              className="min-w-0"
              padding="p-4 sm:p-5"
              headingLevel={3}
              title="Recent leads"
              description="Leads your agents captured from calls"
              actions={
                <button type="button" onClick={() => onNavigate('leads')} className="inline-flex items-center gap-1 text-ui font-medium text-accent-fg hover:underline">
                  Pipeline <ChevronRight className="h-4 w-4" />
                </button>
              }
            >
              {leads.length === 0 ? (
                <p className="py-6 text-center text-ui text-fg-muted">No leads yet. They appear here after calls.</p>
              ) : (
                <ul className="space-y-2">
                  {leads.slice(0, 3).map((lead) => (
                    <li key={lead.id}>
                      <button
                        type="button"
                        onClick={() => onNavigate('leads', { leadName: lead.name })}
                        className="w-full rounded-control border border-line bg-canvas p-3 text-left hover:border-line-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <span className="truncate text-ui font-medium text-ink">{lead.name}</span>
                          <Badge tone={statusWord(lead.stage || 'new').tone} size="xs">{lead.stage || 'New'}</Badge>
                        </div>
                        {lead.company && <div className="truncate text-meta text-fg-body">{lead.company}</div>}
                        <div className="mt-1 flex justify-between text-meta text-fg-muted">
                          <span>{lead.phone || 'No number yet'}</span>
                          <span>{lead.updatedAt ? new Date(lead.updatedAt).toLocaleDateString('en-IN') : 'New'}</span>
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </div>
        </div>
      )}
    </section>
  );
}
