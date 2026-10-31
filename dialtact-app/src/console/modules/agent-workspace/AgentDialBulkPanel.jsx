import React from 'react';
import { PhoneCall, Megaphone } from 'lucide-react';
import { SolidCard } from '../../ui/SolidCard';
import { CampaignSetup } from '../CampaignSetup';
import { OutboundCallForm, useOutboundCall } from '../outbound/OutboundCallForm';

/**
 * Place one outbound live-number call or launch an agent-scoped bulk campaign.
 * The single call is the shared outgoing-call form, the same one the test call
 * (phone) and the Calls page use, with this agent fixed.
 */
export function AgentDialBulkPanel({ agentId, agentName }) {
  // What the tenant chose here survives sub-tab and page switches (per agent, this
  // tab only) and is cleared after the call is placed.
  const call = useOutboundCall({
    draftName: 'agent-outgoing',
    draftSubject: agentId,
    lockedAgentId: agentId,
    extraDraft: { activeTab: 'single' }, // 'single' | 'bulk'
  });
  const activeTab = call.draft.activeTab === 'bulk' ? 'bulk' : 'single';
  const setActiveTab = (value) => call.patchDraft({ activeTab: value });
  const setError = call.setError;

  return (
    <div className="space-y-4" data-testid="agent-dial-bulk">
      {/* Clean Tab Switcher */}
      <div className="flex border-b border-line gap-6 text-ui font-medium" role="group" aria-label="Kind of outgoing call">
        <button
          type="button"
          onClick={() => { setActiveTab('single'); setError(null); }}
          className={`pb-2.5 min-h-[40px] transition-colors border-b-2 flex items-center gap-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-t-control ${
            activeTab === 'single'
              ? 'border-ink text-ink'
              : 'border-transparent text-fg-body hover:text-ink'
          }`}
          data-testid="agent-outbound-tab-single"
        >
          <PhoneCall className="w-3.5 h-3.5" />
          Single call
        </button>
        <button
          type="button"
          onClick={() => { setActiveTab('bulk'); setError(null); }}
          className={`pb-2.5 min-h-[40px] transition-colors border-b-2 flex items-center gap-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-t-control ${
            activeTab === 'bulk'
              ? 'border-ink text-ink'
              : 'border-transparent text-fg-body hover:text-ink'
          }`}
          data-testid="agent-outbound-tab-bulk"
        >
          <Megaphone className="w-3.5 h-3.5" />
          Bulk campaign
        </button>
      </div>

      {/* Single Call Tab */}
      {activeTab === 'single' && (
        <SolidCard className="space-y-3">
          <div className="flex items-center gap-2">
            <PhoneCall className="w-4 h-4 text-accent" aria-hidden="true" />
            <h3 className="text-title text-ink">Place outgoing call</h3>
          </div>
          <p className="text-ui text-fg-muted">
            Call one number now. {agentName} uses their saved script, the same as any other outgoing call.
          </p>
          <OutboundCallForm
            call={call}
            ids={{
              root: 'agent-dial-form',
              from: 'agent-dial-from',
              to: 'agent-dial-to',
              submit: 'agent-dial-start',
              integrationSummary: 'agent-dial-integration-summary',
              error: 'agent-dial-bulk-error',
            }}
          />
        </SolidCard>
      )}

      {activeTab === 'bulk' && <SolidCard><CampaignSetup initialAgentId={agentId} draftKey={`agent-campaign:${agentId}`} onComplete={() => setActiveTab('single')} /></SolidCard>}


    </div>
  );
}
