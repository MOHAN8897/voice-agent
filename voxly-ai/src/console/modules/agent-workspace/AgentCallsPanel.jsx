import React, { useEffect, useState } from 'react';
import { CallsModule } from '../CallsModule';
import { LeadsModule } from '../LeadsModule';
import { TelephonySettingsCard } from '../TelephonySettingsCard';
import { AgentDialBulkPanel } from './AgentDialBulkPanel';

const PANELS = [
  { id: 'history', label: 'History' },
  { id: 'outbound', label: 'Outbound' },
  { id: 'leads', label: 'Leads' },
  { id: 'settings', label: 'Call settings' },
];

/**
 * The Calls tab: logs/transcripts, outbound dial+bulk, leads, and phone hours
 * for one agent — all inside the builder, not separate console pages.
 *
 * `initialPanel` exists because the old `telephony` deep link lands on Call settings.
 */
export function AgentCallsPanel({ agentId, agentName, initialPanel = 'history' }) {
  const [panel, setPanel] = useState(initialPanel);

  useEffect(() => {
    setPanel(initialPanel);
  }, [initialPanel]);

  return (
    <div className="space-y-5">
      <div
        className="flex items-center gap-1 p-1 rounded-2xl bg-white border border-[#E4E2EB] w-fit flex-wrap"
        role="tablist"
        aria-label="Call sections"
      >
        {PANELS.map((p) => (
          <button
            key={p.id}
            type="button"
            role="tab"
            id={`agent-calls-tab-${p.id}`}
            aria-selected={panel === p.id}
            aria-controls={`agent-calls-panel-${p.id}`}
            data-testid={`agent-calls-panel-tab-${p.id}`}
            onClick={() => setPanel(p.id)}
            className={`px-4 py-2 rounded-xl text-xs font-semibold transition-colors ${
              panel === p.id ? 'bg-[#0F0E17] text-white' : 'text-[#524E5E] hover:bg-[#FAF9FD]'
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id={`agent-calls-panel-${panel}`}
        aria-labelledby={`agent-calls-tab-${panel}`}
        className="animate-in fade-in duration-150"
      >
        {panel === 'history' && (
          <CallsModule agentId={agentId} agentName={agentName} embedded />
        )}
        {panel === 'outbound' && (
          <AgentDialBulkPanel agentId={agentId} agentName={agentName} />
        )}
        {panel === 'leads' && <LeadsModule agentId={agentId} />}
        {panel === 'settings' && (
          <div className="space-y-4">
            <p className="text-[11px] text-[#524E5E]">
              When {agentName} answers, holidays and hours, and what a caller hears outside
              those windows. Enforced by the server on the next inbound call.
            </p>
            <TelephonySettingsCard agentId={agentId} />
          </div>
        )}
      </div>
    </div>
  );
}
