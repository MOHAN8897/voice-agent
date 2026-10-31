import React, { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, BarChart3, Clock, Download, PhoneCall, Target, Wallet } from 'lucide-react';
import { PageHeader } from '../../ui/PageHeader';
import { MetricCard } from '../../ui/MetricCard';
import { Section } from '../../ui/SolidCard';
import { Tabs } from '../../ui/Tabs';
import { Toolbar, SelectFilter } from '../../ui/Toolbar';
import { TactileButton } from '../../ui/TactileButton';
import { EmptyState } from '../../ui/EmptyState';
import { Skeleton } from '../../ui/Skeleton';
import { useWorkspace } from '../../context/WorkspaceContext';
import { api } from '../../../services/api';
import { formatInr, formatUsd } from '../../../lib/money';
import { statusWord, tagLabel } from '../../../lib/internalLabels';
import { BarList, DayBars } from './charts';
import { ExportDialog } from './ExportDialog';

const RANGES = [
  { id: 'today', label: 'Today' },
  { id: '7d', label: '7 days' },
  { id: '30d', label: '30 days' },
  { id: 'custom', label: 'Custom' },
];

const OUTCOME_LABELS = {
  answered: 'Answered', no_answer: 'No answer', busy: 'Busy', declined: 'Declined',
  unreachable: 'Unreachable', failed: 'Failed', voicemail: 'Voicemail', in_progress: 'On a call now',
};
const SOURCE_LABELS = {
  inbound_call: 'Incoming call', outbound_call: 'Outgoing call', campaign: 'Campaign',
  ai_call: 'AI employee', manual: 'Added by hand',
};
const DNC_SOURCE_LABELS = {
  operator_ui: 'Added by hand', manual: 'Added by hand', live_call_opt_out: 'Caller asked on a call',
  bulk_upload: 'Upload', subscriber: 'Workspace API',
};
const LANGUAGES = {
  te: 'Telugu', hi: 'Hindi', ta: 'Tamil', kn: 'Kannada', ml: 'Malayalam', mr: 'Marathi',
  bn: 'Bengali', gu: 'Gujarati', pa: 'Punjabi', 'en-in': 'English', en: 'English',
};
const languageLabel = (code) => LANGUAGES[String(code || '').toLowerCase()] || LANGUAGES[String(code || '').toLowerCase().split('-')[0]] || code;

function istToday() {
  return new Date(Date.now() + 330 * 60 * 1000).toISOString().slice(0, 10);
}

function duration(sec) {
  const s = Math.round(Number(sec) || 0);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`;
}

function pct(v) {
  return v == null ? '—' : `${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 1 })}%`;
}

function toRows(map = {}, labels = {}) {
  return Object.entries(map)
    .map(([key, value]) => ({ key, label: labels[key] || statusWord(key).label, value: Number(value) || 0 }))
    .sort((a, b) => b.value - a.value);
}

function Stat({ label, value, testId }) {
  return (
    <div className="min-w-0 rounded-control bg-surface-subtle px-3 py-2.5" data-testid={testId}>
      <div className="truncate text-meta text-fg-muted">{label}</div>
      <div className="font-mono text-title tabular-nums text-ink">{value}</div>
    </div>
  );
}

/**
 * Workspace analytics (route `analytics`, opened from Home → Activity). One period,
 * one agent filter, every number from `GET /api/app/analytics`; exports for the
 * underlying rows open from the header.
 */
export function AnalyticsModule({ onNavigate }) {
  const { agents = [] } = useWorkspace();
  const [range, setRange] = useState('7d');
  const [since, setSince] = useState(() => {
    const d = new Date(Date.now() + 330 * 60 * 1000 - 13 * 86400000);
    return d.toISOString().slice(0, 10);
  });
  const [until, setUntil] = useState(istToday);
  const [agentId, setAgentId] = useState('');
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [exportOpen, setExportOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = { range, agentId };
      if (range === 'custom') Object.assign(params, { since, until });
      setData(await api.analytics.workspace(params));
    } catch (err) {
      setError(err.message || 'Could not load analytics.');
    } finally {
      setLoading(false);
    }
  }, [range, since, until, agentId]);

  useEffect(() => { load(); }, [load]);

  const money = (v) => (data?.spend?.currency === 'INR' ? formatInr(v) : formatUsd(v));
  const agentOptions = [{ value: '', label: 'All agents' }, ...agents.map((a) => ({ value: a.id, label: a.name }))];
  const calls = data?.calls;
  const exportPreset = { dataset: 'calls', range: range === 'custom' ? 'custom' : range, since, until, agentId };

  return (
    <div className="space-y-6" data-testid="analytics-page">
      <PageHeader
        title="Workspace analytics"
        description="How your calls, leads, callbacks and spend are going. Days are India time."
        actions={(
          <>
            {onNavigate && (
              <TactileButton variant="ghost" size="sm" icon={ArrowLeft} onClick={() => onNavigate('overview')}>Home</TactileButton>
            )}
            <TactileButton variant="secondary" size="sm" icon={Download} onClick={() => setExportOpen(true)} data-testid="analytics-export">
              Export data
            </TactileButton>
          </>
        )}
      />

      <Toolbar>
        <Tabs label="Period" value={range} onChange={setRange} items={RANGES} />
        {range === 'custom' && (
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-ui text-fg-body"><span className="sr-only">From</span>
              <input type="date" value={since} max={until} onChange={(e) => setSince(e.target.value)} data-testid="analytics-since"
                className="h-9 rounded-control border border-line bg-surface px-2 text-base sm:text-ui text-ink" />
            </label>
            <span className="text-ui text-fg-muted">to</span>
            <label className="text-ui text-fg-body"><span className="sr-only">To</span>
              <input type="date" value={until} min={since} onChange={(e) => setUntil(e.target.value)} data-testid="analytics-until"
                className="h-9 rounded-control border border-line bg-surface px-2 text-base sm:text-ui text-ink" />
            </label>
          </div>
        )}
        <Toolbar.Spacer />
        {agents.length > 0 && <SelectFilter label="Agent" value={agentId} onChange={setAgentId} options={agentOptions} />}
      </Toolbar>

      {error && (
        <p role="status" className="rounded-control bg-warning-soft px-3 py-2 text-ui text-warning-fg">
          {error} <button type="button" className="font-medium underline" onClick={load}>Try again</button>
        </p>
      )}

      {loading && !data ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28 rounded-card" />)}
        </div>
      ) : !data ? (
        <EmptyState icon={BarChart3} title="Analytics are not available" description="Try again in a moment." />
      ) : (
        <div className={`space-y-6 transition-opacity ${loading ? 'opacity-60' : ''}`} aria-busy={loading}>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" data-testid="analytics-kpis">
            <MetricCard title="Calls" value={calls.total.toLocaleString('en-IN')} icon={PhoneCall}
              subtitle={`${calls.minutes.toLocaleString('en-IN')} minutes talked`} />
            <MetricCard title="Connect rate" value={pct(calls.connectRate)} icon={Target}
              subtitle={`${(calls.outcomes.answered || 0).toLocaleString('en-IN')} answered`} />
            <MetricCard title="Average call" value={duration(calls.avgDurationSec)} icon={Clock}
              subtitle="Answered calls only" />
            <MetricCard title="Spend" value={money(data.spend.total)} icon={Wallet}
              subtitle="Wallet charges in this period" />
          </div>

          <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
            <Section title="Calls per day" description="Every call that rang, answered or not.">
              <DayBars data={calls.perDay} valueKey="calls" label="Calls" secondary={{ key: 'answered', label: 'Answered' }} testId="analytics-calls-per-day" />
            </Section>
            <Section title="Call outcomes">
              <BarList label="Call outcomes" testId="analytics-outcomes"
                rows={Object.keys(OUTCOME_LABELS).map((k) => ({ key: k, label: OUTCOME_LABELS[k], value: calls.outcomes[k] || 0 }))
                  .filter((r) => r.value > 0 || r.key !== 'in_progress')} />
            </Section>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Section title="Leads" description={`${data.leads.total.toLocaleString('en-IN')} new · ${data.leads.converted.toLocaleString('en-IN')} converted · ${pct(data.leads.conversionRate)} conversion`}>
              <div className="grid gap-6 sm:grid-cols-2">
                <div>
                  <h3 className="mb-2 text-ui font-semibold text-ink">By stage</h3>
                  <BarList label="Leads by stage" rows={toRows(data.leads.byStage)} testId="analytics-lead-stages" />
                </div>
                <div>
                  <h3 className="mb-2 text-ui font-semibold text-ink">By source</h3>
                  <BarList label="Leads by source" rows={toRows(data.leads.bySource, SOURCE_LABELS)} />
                </div>
              </div>
            </Section>
            <Section title="Top tags" description="What callers talked about most.">
              <BarList label="Top tags" testId="analytics-tags" empty="No tagged calls in this period."
                rows={data.topTags.map((t) => ({ key: t.tag, label: tagLabel(t.tag), value: t.count }))} />
            </Section>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <Section title="Callback requests">
              <div className="grid grid-cols-3 gap-2" data-testid="analytics-callbacks">
                <Stat label="Requested" value={data.callbacks.requested} />
                <Stat label="Completed" value={data.callbacks.completed} />
                <Stat label="Pending" value={data.callbacks.pending} />
              </div>
            </Section>
            <Section title="Language callbacks">
              <div className="grid grid-cols-3 gap-2">
                <Stat label="Requested" value={data.languageCallbacks.requested} />
                <Stat label="Completed" value={data.languageCallbacks.completed} />
                <Stat label="Pending" value={data.languageCallbacks.pending} />
              </div>
              {data.languageCallbacks.byLanguage.length > 0 && (
                <div className="mt-4">
                  <BarList label="Language callbacks by language"
                    rows={data.languageCallbacks.byLanguage.map((l) => ({ key: l.language, label: languageLabel(l.language), value: l.requested, hint: `${l.pending} pending` }))} />
                </div>
              )}
            </Section>
            <Section title="Follow-ups">
              <div className="grid grid-cols-3 gap-2" data-testid="analytics-followups">
                <Stat label="Scheduled" value={data.followups.scheduled} />
                <Stat label="Done" value={data.followups.done} />
                <Stat label="Failed" value={data.followups.failed} />
              </div>
              {data.followups.cancelled > 0 && (
                <p className="mt-2 text-meta text-fg-muted">{data.followups.cancelled} cancelled or blocked by do-not-call.</p>
              )}
            </Section>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Section title="Spend per day" description="Wallet charges, by the day they were taken.">
              <DayBars data={data.spend.perDay} valueKey="amount" label="Spend" format={money} testId="analytics-spend-per-day" />
              <h3 className="mb-2 mt-5 text-ui font-semibold text-ink">By agent</h3>
              <BarList label="Spend by agent" format={money}
                rows={data.spend.byAgent.map((a) => ({ key: a.agentId || 'other', label: a.name, value: a.amount }))} />
            </Section>
            <Section title="Do-not-call list" description={`${data.dnc.active.toLocaleString('en-IN')} numbers on the list · ${data.dnc.added.toLocaleString('en-IN')} added in this period`}>
              <DayBars data={data.dnc.perDay} valueKey="added" label="Numbers added" testId="analytics-dnc-per-day" />
              {Object.keys(data.dnc.bySource).length > 0 && (
                <div className="mt-5">
                  <BarList label="Added by" rows={toRows(data.dnc.bySource, DNC_SOURCE_LABELS)} />
                </div>
              )}
            </Section>
          </div>
        </div>
      )}

      {exportOpen && <ExportDialog isOpen={exportOpen} onClose={() => setExportOpen(false)} preset={exportPreset} />}
    </div>
  );
}
