import React, { useMemo, useState } from 'react';
import { PhoneCall, Megaphone, Play, ShieldAlert, CheckCircle2 } from 'lucide-react';
import { SolidCard } from '../../ui/SolidCard';
import { TactileButton } from '../../ui/TactileButton';
import { useWorkspace } from '../../context/WorkspaceContext';
import { showToast } from '../../ui/ToastHost';
import { CampaignSetup } from '../CampaignSetup';
import { CallIntegrationPicker, IntegrationSelectionSummary, useCallIntegrationOptions } from '../../ui/CallIntegrationPicker';

// Workspace plan ceiling for simultaneous outbound lines.
const MAX_CONCURRENCY = 20;

/**
 * Place one outbound live-number call or launch an agent-scoped bulk campaign.
 * Features clean tab navigation ("Single Call" vs "Bulk Campaign") and regulatory compliance modal.
 */
export function AgentDialBulkPanel({ agentId, agentName }) {
  const {
    phoneNumbers,
    placeOutboundCall,
    campaigns,
    outboundFromE164,
    setPreferredOutboundFrom,
    wallet,
  } = useWorkspace();

  const assigned = useMemo(
    () => phoneNumbers.filter((n) => n.assignedAgentId === agentId && n.status !== 'released'),
    [phoneNumbers, agentId]
  );
  const agentCampaigns = useMemo(
    () => campaigns.filter((c) => c.agentId === agentId),
    [campaigns, agentId]
  );

  const [activeTab, setActiveTab] = useState('single'); // 'single' | 'bulk'
  const [toNumber, setToNumber] = useState('');
  const [fromNumber, setFromNumber] = useState(
    () => outboundFromE164 || assigned[0]?.number || assigned[0]?.e164 || ''
  );
  const [dialBusy, setDialBusy] = useState(false);
  // Integrations attached to this call; null keeps the agent's saved settings.
  const [callIntegrations, setCallIntegrations] = useState(null);
  const integrationOptions = useCallIntegrationOptions(activeTab === 'single' ? agentId : null);
  const [error, setError] = useState(null);

  const balanceUsd = Number(wallet?.balanceUsd) || 0;
  const balanceInr = Number(wallet?.balanceInr) || 0;
  const walletEmpty = balanceUsd <= 0 && balanceInr <= 0;

  const dial = async () => {
    setError(null);
    if (!toNumber.trim()) {
      setError('Enter the number to call with its country code, like +91 98765 43210.');
      return;
    }
    if (walletEmpty) {
      showToast('Add wallet funds before placing a call.', 'error');
      return;
    }
    setDialBusy(true);
    try {
      if (fromNumber) setPreferredOutboundFrom?.(fromNumber);
      await placeOutboundCall({
        agentId,
        toE164: toNumber.trim(),
        fromE164: fromNumber || null,
        integrations: callIntegrations,
      });
      showToast('Outgoing call started', 'success');
      setToNumber('');
    } catch (e) {
      setError(e.message || 'The call could not be placed');
      showToast(e.message || 'The call could not be placed', 'error');
    } finally {
      setDialBusy(false);
    }
  };

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
            <PhoneCall className="w-4 h-4 text-accent" />
            <h3 className="text-title text-ink">Place outgoing call</h3>
          </div>
          <p className="text-ui text-fg-muted">
            Call one number now. {agentName} uses their saved script, the same as any other outgoing call.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="block text-ui font-medium text-ink">
              From
              <select
                className="mt-1 w-full rounded-control border border-line px-3 py-2 text-base sm:text-ui min-h-[42px] sm:min-h-[36px] bg-surface text-ink focus:border-accent focus:outline-none"
                value={fromNumber}
                onChange={(e) => setFromNumber(e.target.value)}
                data-testid="agent-dial-from"
              >
                <option value="">Default number</option>
                {assigned.map((n) => (
                  <option key={n.id} value={n.number || n.e164}>
                    {n.number || n.e164}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-ui font-medium text-ink">
              To (with country code)
              <input
                className="mt-1 w-full rounded-control border border-line px-3 py-2 text-base sm:text-ui min-h-[42px] sm:min-h-[36px] bg-surface text-ink focus:border-accent focus:outline-none"
                placeholder="+9188…"
                value={toNumber}
                onChange={(e) => setToNumber(e.target.value)}
                data-testid="agent-dial-to"
              />
            </label>
          </div>
          <div className="border-t border-line pt-3">
            <CallIntegrationPicker scope="call" agentId={agentId} value={callIntegrations}
              onChange={setCallIntegrations} disabled={dialBusy} options={integrationOptions} />
          </div>
          <div className="rounded-control border border-line bg-canvas p-3" data-testid="agent-dial-integration-summary">
            <div className="mb-1.5 text-meta font-medium text-fg-body">This call will use</div>
            <IntegrationSelectionSummary selection={callIntegrations} options={integrationOptions.items}
              emptyText="No apps chosen for this call: the employee uses their saved app settings." />
          </div>
          <TactileButton
            variant="primary"
            size="sm"
            icon={PhoneCall}
            loading={dialBusy}
            onClick={dial}
            disabled={!agentId}
            data-testid="agent-dial-start"
            className="w-full sm:w-auto min-h-[42px] sm:min-h-[36px]"
          >
            Call now
          </TactileButton>
        </SolidCard>
      )}

      {activeTab === 'bulk' && <SolidCard><CampaignSetup initialAgentId={agentId} onComplete={() => setActiveTab('single')} /></SolidCard>}

      {error && (
        <p className="text-ui text-danger-fg" role="alert" data-testid="agent-dial-bulk-error">
          {error}
        </p>
      )}

    </div>
  );
}
