import React, { useEffect, useState } from 'react';
import { PhoneIncoming, PhoneOutgoing, History, Users } from 'lucide-react';
import { CallsModule } from '../CallsModule';
import { LeadsModule } from '../LeadsModule';
import { AgentInboundPanel } from './AgentInboundPanel';
import { AgentDialBulkPanel } from './AgentDialBulkPanel';
import { ErrorBoundary } from '../../ui/ErrorBoundary';
import { useSessionDraft } from '../../lib/sessionDraft';
import { useLeadWorkCounts } from '../../lib/leadWorkCounts';

const PANELS = [
  { id: 'inbound', label: 'Incoming', icon: PhoneIncoming },
  { id: 'outbound', label: 'Outgoing', icon: PhoneOutgoing },
  { id: 'history', label: 'History', icon: History },
  { id: 'leads', label: 'Leads', icon: Users },
];

/**
 * The Calls tab: Inbound reception status, Outbound single+bulk dialer,
 * Call logs / audio transcripts, and Captured leads for this agent.
 *
 * (Note: Call and Telephony settings are now unified into the agent's Settings page).
 */
export function AgentCallsPanel({
  agentId,
  agentName,
  initialPanel = null,
  initialFilters = null,
  onPanelChange,
  onNavigateToSettings,
}) {
  // The sub-tab the tenant was on comes back when they return to this agent's
  // Calls tab (from another tab or another page). An explicit link wins.
  const [remembered, rememberPanel] = useSessionDraft('agent-calls-panel', agentId, { panel: null });
  const [panel, setPanelState] = useState(() => {
    // If an old link points to 'settings', gracefully land on 'inbound'
    if (initialPanel === 'settings') return 'inbound';
    return initialPanel || remembered.panel || 'history';
  });
  const setPanel = (next) => {
    setPanelState(next);
    rememberPanel({ panel: next });
    onPanelChange?.(next);
  };
  const [historyPhone, setHistoryPhone] = useState('');
  // Callbacks and language callbacks waiting for this agent, shown on the Leads tab.
  const work = useLeadWorkCounts(agentId);
  const pendingLeads = (work.followups || 0) + (work.language || 0);

  useEffect(() => {
    if (initialPanel === 'settings') {
      setPanelState('inbound');
    } else if (initialPanel) {
      setPanelState(initialPanel);
    }
  }, [initialPanel]);

  return (
    <div className="space-y-5" data-testid="agent-calls-panel">
      {/* Sub-navigation tabs */}
      <div
        className="flex max-w-full items-center gap-0.5 overflow-x-auto no-scrollbar rounded-control border border-line bg-surface-subtle p-0.5 w-fit"
        role="tablist"
        aria-label="Call sections"
      >
        {PANELS.map((p) => {
          const Icon = p.icon;
          const isActive = panel === p.id;
          return (
            <button
              key={p.id}
              type="button"
              role="tab"
              id={`agent-calls-tab-${p.id}`}
              aria-selected={isActive}
              aria-controls={`agent-calls-panel-${p.id}`}
              aria-description={p.id === 'leads' && pendingLeads > 0 ? `${pendingLeads} waiting` : undefined}
              data-testid={`agent-calls-panel-tab-${p.id}`}
              onClick={() => setPanel(p.id)}
              className={`flex shrink-0 items-center gap-1.5 px-2.5 sm:px-4 py-1.5 min-h-[36px] rounded-[8px] text-ui font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                isActive
                  ? 'bg-surface text-ink shadow-craft-xs'
                  : 'text-fg-body hover:text-ink'
              }`}
            >
              <Icon className="w-3.5 h-3.5" aria-hidden="true" />
              <span>{p.label}</span>
              {p.id === 'leads' && pendingLeads > 0 && (
                <span aria-hidden="true" data-testid="agent-calls-tab-count-leads" className="rounded-pill bg-warning-soft px-1.5 font-mono text-meta tabular-nums text-warning-fg">
                  {pendingLeads}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Tab Panels */}
      <div
        role="tabpanel"
        id={`agent-calls-panel-${panel}`}
        aria-labelledby={`agent-calls-tab-${panel}`}
        className="animate-in fade-in duration-150"
      >
        <ErrorBoundary
          key={panel}
          title="This section could not load"
          description="Something went wrong here. Try again or open another section."
        >
          {panel === 'inbound' && (
            <AgentInboundPanel
              agentId={agentId}
              agentName={agentName}
              onNavigateToSettings={onNavigateToSettings}
            />
          )}
          {panel === 'outbound' && (
            <AgentDialBulkPanel agentId={agentId} agentName={agentName} />
          )}
          {panel === 'history' && (
            <CallsModule agentId={agentId} agentName={agentName} initialSearch={historyPhone} initialStatus={initialFilters?.status} embedded />
          )}
          {panel === 'leads' && <LeadsModule agentId={agentId} agentName={agentName}
            initialStage={initialFilters?.stage} initialDays={initialFilters?.days}
            onOpenHistory={(lead) => { setHistoryPhone(lead.phone); setPanel('history'); }} />}
        </ErrorBoundary>
      </div>
    </div>
  );
}
