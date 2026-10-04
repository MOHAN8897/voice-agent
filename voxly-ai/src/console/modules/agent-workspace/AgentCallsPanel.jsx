import React, { useEffect, useState } from 'react';
import { PhoneIncoming, PhoneOutgoing, History, Users } from 'lucide-react';
import { CallsModule } from '../CallsModule';
import { LeadsModule } from '../LeadsModule';
import { AgentInboundPanel } from './AgentInboundPanel';
import { AgentDialBulkPanel } from './AgentDialBulkPanel';

const PANELS = [
  { id: 'inbound', label: 'Inbound', icon: PhoneIncoming },
  { id: 'outbound', label: 'Outbound', icon: PhoneOutgoing },
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
  initialPanel = 'inbound',
  onNavigateToSettings,
}) {
  const [panel, setPanel] = useState(() => {
    // If an old link points to 'settings', gracefully land on 'inbound'
    if (initialPanel === 'settings') return 'inbound';
    return initialPanel || 'inbound';
  });

  useEffect(() => {
    if (initialPanel === 'settings') {
      setPanel('inbound');
    } else if (initialPanel) {
      setPanel(initialPanel);
    }
  }, [initialPanel]);

  return (
    <div className="space-y-5" data-testid="agent-calls-panel">
      {/* Sub-navigation tabs */}
      <div
        className="flex items-center gap-1 p-1 rounded-2xl bg-white border border-[#E4E2EB] w-fit flex-wrap shadow-craft-xs"
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
              data-testid={`agent-calls-panel-tab-${p.id}`}
              onClick={() => setPanel(p.id)}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold transition-all ${
                isActive
                  ? 'bg-[#0F0E17] text-white shadow-xs font-bold'
                  : 'text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD]'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{p.label}</span>
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
          <CallsModule agentId={agentId} agentName={agentName} embedded />
        )}
        {panel === 'leads' && <LeadsModule agentId={agentId} />}
      </div>
    </div>
  );
}
