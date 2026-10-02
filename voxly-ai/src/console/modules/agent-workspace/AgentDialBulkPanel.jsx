import React, { useMemo, useState } from 'react';
import { PhoneCall, Megaphone, Play } from 'lucide-react';
import { SolidCard } from '../../ui/SolidCard';
import { TactileButton } from '../../ui/TactileButton';
import { useWorkspace } from '../../context/WorkspaceContext';
import { showToast } from '../../ui/ToastHost';

const MAX_CONCURRENCY = 20; // SaaS platform ceiling; Telnyx account may be 10 until support raises channels

function parseContactLines(text) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [phone, ...rest] = line.split(/[,;\t]/);
      return { phone: phone.trim(), name: rest.join(' ').trim() || undefined };
    })
    .filter((c) => c.phone);
}

/**
 * Place one outbound live-number call or launch an agent-scoped bulk campaign.
 * Uses existing outbound + campaigns APIs — no new dial path.
 */
export function AgentDialBulkPanel({ agentId, agentName }) {
  const {
    phoneNumbers,
    placeOutboundCall,
    createCampaign,
    campaigns,
    startCampaign,
    toggleCampaignStatus,
    outboundFromE164,
    setPreferredOutboundFrom,
    wallet,
  } = useWorkspace();

  const assigned = useMemo(
    () => phoneNumbers.filter((n) => n.assignedAgentId === agentId && n.outboundEnabled !== false),
    [phoneNumbers, agentId]
  );
  const agentCampaigns = useMemo(
    () => campaigns.filter((c) => c.agentId === agentId),
    [campaigns, agentId]
  );

  const [toNumber, setToNumber] = useState('');
  const [fromNumber, setFromNumber] = useState(
    () => outboundFromE164 || assigned[0]?.number || assigned[0]?.e164 || ''
  );
  const [dialBusy, setDialBusy] = useState(false);
  const [bulkName, setBulkName] = useState(`${agentName || 'Agent'} campaign`);
  const [contactLines, setContactLines] = useState('');
  const [concurrency, setConcurrency] = useState(3);
  const [maxAttempts, setMaxAttempts] = useState(2);
  const [retryDelayMin, setRetryDelayMin] = useState(30);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [error, setError] = useState(null);

  const balanceUsd = Number(wallet?.balanceUsd) || 0;
  const balanceInr = Number(wallet?.balanceInr) || 0;
  const walletEmpty = balanceUsd <= 0 && balanceInr <= 0;

  const dial = async () => {
    setError(null);
    if (!toNumber.trim()) {
      setError('Enter a destination number in E.164 (+91…).');
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
      });
      showToast('Outgoing call started', 'success');
      setToNumber('');
    } catch (e) {
      setError(e.message || 'Could not place call');
      showToast(e.message || 'Could not place call', 'error');
    } finally {
      setDialBusy(false);
    }
  };

  const launchBulk = async () => {
    setError(null);
    const contacts = parseContactLines(contactLines);
    if (!contacts.length) {
      setError('Paste at least one phone number (one per line).');
      return;
    }
    if (walletEmpty) {
      showToast('Add wallet funds before starting a campaign.', 'error');
      return;
    }
    if (!fromNumber && !assigned.length) {
      // Fall back to any workspace outbound line — SaaS single-DID tenants often
      // dial before pinning the number to one agent.
      const pool = phoneNumbers.find((n) => n.outboundEnabled !== false);
      if (!pool) {
        setError('Assign an outbound-enabled number to this agent first.');
        return;
      }
    }
    setBulkBusy(true);
    try {
      if (fromNumber) setPreferredOutboundFrom?.(fromNumber);
      await createCampaign({
        name: bulkName.trim() || `${agentName} campaign`,
        agentId,
        concurrencyLimit: Math.min(MAX_CONCURRENCY, Math.max(1, Number(concurrency) || 1)),
        maxAttemptsPerContact: Math.min(5, Math.max(1, Number(maxAttempts) || 1)),
        retryDelayMinutes: Math.max(5, Number(retryDelayMin) || 30),
        fromE164: fromNumber || undefined,
        contacts,
        autoStart: true,
      });
      showToast(`Campaign started · ${contacts.length} contacts`, 'success');
      setContactLines('');
    } catch (e) {
      setError(e.message || 'Could not start campaign');
      showToast(e.message || 'Could not start campaign', 'error');
    } finally {
      setBulkBusy(false);
    }
  };

  return (
    <div className="space-y-5" data-testid="agent-dial-bulk">
      <SolidCard className="space-y-3">
        <div className="flex items-center gap-2">
          <PhoneCall className="w-4 h-4 text-[#6344E7]" />
          <h3 className="text-xs font-bold text-[#0F0E17]">Place outgoing call</h3>
        </div>
        <p className="text-[11px] text-[#524E5E]">
          One live-number dial using {agentName}&apos;s published script. Same path as fleet Calls.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="block text-[11px] font-semibold text-[#0F0E17]">
            From
            <select
              className="mt-1 w-full rounded-xl border border-[#E4E2EB] px-3 py-2 text-xs"
              value={fromNumber}
              onChange={(e) => setFromNumber(e.target.value)}
              data-testid="agent-dial-from"
            >
              <option value="">Default line</option>
              {assigned.map((n) => (
                <option key={n.id} value={n.number || n.e164}>
                  {n.number || n.e164}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-[11px] font-semibold text-[#0F0E17]">
            To (E.164)
            <input
              className="mt-1 w-full rounded-xl border border-[#E4E2EB] px-3 py-2 text-xs"
              placeholder="+9188…"
              value={toNumber}
              onChange={(e) => setToNumber(e.target.value)}
              data-testid="agent-dial-to"
            />
          </label>
        </div>
        <TactileButton
          variant="primary"
          size="sm"
          icon={PhoneCall}
          loading={dialBusy}
          onClick={dial}
          disabled={!agentId}
          data-testid="agent-dial-start"
        >
          Call now
        </TactileButton>
      </SolidCard>

      <SolidCard className="space-y-3">
        <div className="flex items-center gap-2">
          <Megaphone className="w-4 h-4 text-[#6344E7]" />
          <h3 className="text-xs font-bold text-[#0F0E17]">Bulk outbound</h3>
        </div>
        <p className="text-[11px] text-[#524E5E]">
          Paste numbers (one per line, optional name after comma). Concurrent dials are capped
          based on your plan and wallet balance. Retries use the delay below when a contact does not connect.
        </p>
        <label className="block text-[11px] font-semibold text-[#0F0E17]">
          Campaign name
          <input
            className="mt-1 w-full rounded-xl border border-[#E4E2EB] px-3 py-2 text-xs"
            value={bulkName}
            onChange={(e) => setBulkName(e.target.value)}
            data-testid="agent-bulk-name"
          />
        </label>
        <label className="block text-[11px] font-semibold text-[#0F0E17]">
          Contacts
          <textarea
            className="mt-1 w-full rounded-xl border border-[#E4E2EB] px-3 py-2 text-xs font-mono min-h-[100px]"
            placeholder={'+918897908470, Alex\n+14155552671'}
            value={contactLines}
            onChange={(e) => setContactLines(e.target.value)}
            data-testid="agent-bulk-contacts"
          />
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <label className="block text-[11px] font-semibold text-[#0F0E17]">
            Concurrent calls
            <input
              type="number"
              min={1}
              max={MAX_CONCURRENCY}
              className="mt-1 w-full rounded-xl border border-[#E4E2EB] px-3 py-2 text-xs"
              value={concurrency}
              onChange={(e) => setConcurrency(e.target.value)}
              data-testid="agent-bulk-concurrency"
            />
          </label>
          <label className="block text-[11px] font-semibold text-[#0F0E17]">
            Max attempts
            <input
              type="number"
              min={1}
              max={5}
              className="mt-1 w-full rounded-xl border border-[#E4E2EB] px-3 py-2 text-xs"
              value={maxAttempts}
              onChange={(e) => setMaxAttempts(e.target.value)}
              data-testid="agent-bulk-attempts"
            />
          </label>
          <label className="block text-[11px] font-semibold text-[#0F0E17]">
            Retry delay (min)
            <input
              type="number"
              min={5}
              className="mt-1 w-full rounded-xl border border-[#E4E2EB] px-3 py-2 text-xs"
              value={retryDelayMin}
              onChange={(e) => setRetryDelayMin(e.target.value)}
              data-testid="agent-bulk-retry-delay"
            />
          </label>
        </div>
        <TactileButton
          variant="primary"
          size="sm"
          icon={Play}
          loading={bulkBusy}
          onClick={launchBulk}
          disabled={!agentId}
          data-testid="agent-bulk-start"
        >
          Start campaign
        </TactileButton>

        {agentCampaigns.length > 0 && (
          <div className="pt-3 border-t border-[#E4E2EB] space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A]">
              This agent&apos;s campaigns
            </p>
            {agentCampaigns.slice(0, 8).map((c) => (
              <div
                key={c.id}
                className="flex items-center justify-between gap-2 text-xs"
                data-testid={`agent-campaign-row-${c.id}`}
              >
                <span className="font-semibold text-[#0F0E17] truncate">
                  {c.name} · {c.status} · ×{c.concurrency ?? c.concurrencyLimit ?? '—'}
                </span>
                <div className="flex gap-1 shrink-0">
                  {c.status !== 'running' && (
                    <button
                      type="button"
                      className="px-2 py-1 rounded-lg border border-[#E4E2EB] hover:bg-[#FAF9FD]"
                      onClick={() => startCampaign(c.id).catch((e) => showToast(e.message, 'error'))}
                    >
                      Start
                    </button>
                  )}
                  <button
                    type="button"
                    className="px-2 py-1 rounded-lg border border-[#E4E2EB] hover:bg-[#FAF9FD]"
                    onClick={() => toggleCampaignStatus(c.id).catch((e) => showToast(e.message, 'error'))}
                  >
                    {c.status === 'running' ? 'Pause' : 'Toggle'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </SolidCard>

      {error && (
        <p className="text-[11px] text-red-600" data-testid="agent-dial-bulk-error">
          {error}
        </p>
      )}
    </div>
  );
}
