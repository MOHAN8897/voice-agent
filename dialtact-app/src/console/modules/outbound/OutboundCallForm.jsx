import React, { useMemo, useRef, useState } from 'react';
import { AlertCircle, CreditCard, Mic, PhoneCall, Zap } from 'lucide-react';
import { useWorkspace } from '../../context/WorkspaceContext';
import { useSessionDraft } from '../../lib/sessionDraft';
import { TactileButton } from '../../ui/TactileButton';
import { showToast } from '../../ui/ToastHost';
import { CallIntegrationPicker, IntegrationSelectionSummary, useCallIntegrationOptions } from '../../ui/CallIntegrationPicker';
import { walletAmounts } from '../../../lib/money';
import {
  defaultOutboundLine,
  isFundsError,
  normalizeDestination,
  outboundCallErrorMessage,
  outboundLines,
  phoneCallRate,
  walletIsEmpty,
} from '../../lib/outboundCall';

const FIELD =
  'mt-1 w-full min-w-0 rounded-control border border-line bg-surface px-3 py-2 text-base sm:text-ui min-h-[42px] sm:min-h-[38px] text-ink placeholder:text-fg-subtle focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15 disabled:opacity-50';

const newDialRequestId = () =>
  (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `dial-${Date.now()}-${Math.random().toString(16).slice(2)}`);

/**
 * State and rules for one outgoing call, shared by every place that dials.
 *
 * draftName/draftSubject: where the form's draft lives in this tab's
 * sessionStorage (useSessionDraft); `extraDraft` adds a place's own fields (a
 * sub-tab, say) to the same draft. lockedAgentId: the agent is fixed by context
 * (agent workspace); otherwise the form offers an agent picker.
 */
export function useOutboundCall({ draftName, draftSubject = 'all', lockedAgentId = null, extraDraft = {}, onRequireFunds = null, enabled = true } = {}) {
  const {
    agents = [],
    phoneNumbers = [],
    wallet,
    outboundFromE164,
    setPreferredOutboundFrom,
    placeOutboundCall,
    openAddFunds,
    toggleAgentStatus,
  } = useWorkspace();
  const [draft, patchDraft] = useSessionDraft(draftName, draftSubject, {
    ...extraDraft,
    agentId: '',
    toNumber: '',
    fromNumber: null, // null: not chosen yet, use the default line
    callIntegrations: null, // null: the agent's saved app settings
    integrationsAgentId: '',
  });

  // A remembered agent that no longer exists falls back to the first one.
  const agentId = lockedAgentId
    || (agents.some((a) => a.id === draft.agentId) ? draft.agentId : agents[0]?.id || '');
  const agent = agents.find((a) => a.id === agentId) || null;
  const lines = useMemo(() => outboundLines(phoneNumbers, agent), [phoneNumbers, agent]);
  const defaultLine = defaultOutboundLine(lines, outboundFromE164);
  // A remembered line that was released falls back to the default line.
  const fromNumber = draft.fromNumber === '' ? ''
    : lines.some((l) => l.value === draft.fromNumber) ? draft.fromNumber : defaultLine;
  const effectiveFrom = fromNumber || defaultLine;
  // Apps chosen for one agent never ride along on another agent's call.
  const callIntegrations = draft.integrationsAgentId === agentId ? draft.callIntegrations : null;
  const integrationOptions = useCallIntegrationOptions(enabled ? agentId : null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const dialRef = useRef(false);
  const rate = phoneCallRate(wallet, agent);
  const empty = walletIsEmpty(wallet);
  const paused = Boolean(agent?.status && !['active', 'live'].includes(agent.status));

  const requireFunds = (reason) => {
    if (onRequireFunds) onRequireFunds(reason);
    else openAddFunds?.(reason);
  };

  const set = {
    agentId: (value) => patchDraft({ agentId: value }),
    toNumber: (value) => { patchDraft({ toNumber: value }); if (error) setError(''); },
    fromNumber: (value) => {
      patchDraft({ fromNumber: value });
      // The chosen line is also this tab's preferred caller ID elsewhere.
      if (value) setPreferredOutboundFrom?.(value);
    },
    callIntegrations: (value) => patchDraft({ callIntegrations: value, integrationsAgentId: agentId }),
  };

  /** Validate and place the call. Resolves to the server result, or null when not placed. */
  const place = async () => {
    if (dialRef.current) return null;
    setError('');
    if (!agentId) { setError('Create an agent before placing calls.'); return null; }
    if (paused) { setError('This agent is paused. Turn them on before calling.'); return null; }
    if (!lines.length) { setError('Turn on outgoing calls for one of your phone numbers before calling.'); return null; }
    const destination = normalizeDestination(draft.toNumber);
    if (!destination.ok) { setError(destination.error); return null; }
    if (empty) {
      setError('Your wallet is empty. Add funds to place calls.');
      requireFunds('Add funds to your wallet before placing a call.');
      return null;
    }
    dialRef.current = true;
    setBusy(true);
    try {
      if (effectiveFrom) setPreferredOutboundFrom?.(effectiveFrom);
      const result = await placeOutboundCall({
        agentId,
        toE164: destination.e164,
        fromE164: effectiveFrom || null,
        integrations: callIntegrations,
        dialRequestId: newDialRequestId(),
      });
      showToast(`Calling ${destination.e164}`, 'success');
      // Placed: the number and per-call apps are done; the agent and line stay.
      patchDraft({ toNumber: '', callIntegrations: null, integrationsAgentId: '' });
      return { ...result, toE164: destination.e164 };
    } catch (err) {
      const message = outboundCallErrorMessage(err);
      setError(message);
      showToast(message, 'error');
      if (isFundsError(err)) requireFunds(message);
      const failure = new Error(message);
      failure.code = err?.code;
      failure.status = err?.status;
      throw failure;
    } finally {
      dialRef.current = false;
      setBusy(false);
    }
  };

  const turnOn = async () => {
    if (!agent?.id) return;
    try {
      await toggleAgentStatus?.(agent.id, 'active');
      setError('');
    } catch (err) {
      showToast(err?.message || 'The agent could not be turned on.', 'error');
    }
  };

  return {
    draft, patchDraft, agents, agent, agentId, lockedAgentId, lines, defaultLine, fromNumber,
    toNumber: draft.toNumber, callIntegrations, integrationOptions, wallet, rate, empty, paused,
    busy, error, setError, set, place, turnOn, requireFunds,
  };
}

/**
 * The outgoing-call form. Every dialer renders this, so they offer the same
 * options: agent (unless fixed), caller line, number with country code, apps for
 * this call, cost and wallet, recording notice and paused-agent guard.
 *
 * `ids` keeps each place's existing test ids on its fields.
 */
export function OutboundCallForm({ call, ids = {}, submitLabel = 'Call now', busyLabel = 'Calling…', onPlaced, onFailed, intro = null, showCost = true, noLinesHint = '', compact = false }) {
  const {
    agents, agent, agentId, lockedAgentId, lines, fromNumber, toNumber, callIntegrations, integrationOptions,
    wallet, rate, empty, paused, busy, error, set, place, turnOn, requireFunds,
  } = call;
  const amounts = walletAmounts(wallet);
  const minutes = rate && !empty
    ? Math.floor((Number(wallet?.balanceInr) || 0) > 0 ? Number(wallet.balanceInr) / rate.inr : (Number(wallet?.balanceUsd) || 0) / rate.usd)
    : null;

  const submit = async () => {
    try {
      const result = await place();
      if (result) onPlaced?.(result);
    } catch (err) {
      onFailed?.(err);
    }
  };

  return (
    <div className="space-y-3.5" data-testid={ids.root || 'outbound-call-form'} data-outbound-form="">
      {intro}

      {empty && (
        <div data-testid={ids.paymentWall || 'outbound-payment-wall'}
          className="flex flex-col gap-3 rounded-control border border-warning-line bg-warning-soft p-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-ui text-warning-fg">Your wallet is empty. Add funds to place calls and receive callbacks.</p>
          <TactileButton variant="brand" size="sm" icon={CreditCard} onClick={() => requireFunds('Add funds to place calls.')}
            data-testid={ids.paymentWallAdd || 'outbound-payment-wall-add'}>
            Add funds
          </TactileButton>
        </div>
      )}

      <div className={`grid grid-cols-1 gap-3 ${compact ? '' : lockedAgentId ? 'sm:grid-cols-2' : 'sm:grid-cols-2 lg:grid-cols-3'}`}>
        {!lockedAgentId && (
          <label className="block min-w-0 text-ui font-medium text-ink">
            Agent
            <select value={agentId} onChange={(e) => set.agentId(e.target.value)} className={FIELD} aria-label="Agent"
              data-testid={ids.agent || 'outbound-agent'} data-outbound-field="agent" disabled={busy}>
              {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </label>
        )}
        <div className="min-w-0">
          {lines.length > 0 ? (
            <label className="block text-ui font-medium text-ink">
              Call from
              <select value={fromNumber} onChange={(e) => set.fromNumber(e.target.value)} disabled={busy} aria-label="Call from"
                className={`${FIELD} font-mono tabular-nums`} data-testid={ids.from || 'outbound-from'} data-outbound-field="from">
                <option value="">Automatic: the agent’s own line first</option>
                {lines.map((line) => <option key={line.value} value={line.value}>{line.label}</option>)}
              </select>
            </label>
          ) : (
            <p className="text-ui font-medium text-ink">Call from</p>
          )}
          {lines.length > 0 ? (
            <p className="mt-1 text-meta text-fg-muted">The number that shows on the phone that rings.</p>
          ) : (
            <div className="mt-1 space-y-1.5">
              <div className="rounded-control border border-warning-line bg-warning-soft p-3 text-ui text-warning-fg space-y-1" data-testid="outbound-no-lines">
                <div className="flex items-center gap-1.5 font-semibold">
                  <AlertCircle className="w-4 h-4 shrink-0" aria-hidden="true" />
                  <span>None of your numbers can make outgoing calls yet</span>
                </div>
                <p className="leading-normal">Turn on outgoing calls for a number in <strong>Phone numbers</strong>{noLinesHint}.</p>
              </div>
              {ids.fromHidden && <input type="hidden" value="" data-testid={ids.fromHidden} />}
            </div>
          )}
        </div>
        <div className="min-w-0">
          <label className="block text-ui font-medium text-ink">
            Phone number to call
            <input type="tel" inputMode="tel" autoComplete="tel" value={toNumber} disabled={busy} aria-label="Phone number to call"
              onChange={(e) => set.toNumber(e.target.value)} placeholder="+91 98765 43210"
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); submit(); } }}
              className={`${FIELD} font-mono tabular-nums`} data-testid={ids.to || 'outbound-to'} data-outbound-field="to"
              aria-invalid={Boolean(error) || undefined} aria-describedby={`${ids.to || 'outbound-to'}-hint`} />
          </label>
          <p id={`${ids.to || 'outbound-to'}-hint`} className="mt-1 text-meta text-fg-muted">
            With its country code: +91 for India, +1 for the US.
          </p>
        </div>
      </div>

      {agentId && (
        <div className="border-t border-line pt-3">
          <CallIntegrationPicker scope="call" agentId={agentId} value={callIntegrations}
            onChange={set.callIntegrations} disabled={busy} options={integrationOptions} />
        </div>
      )}
      <div className="rounded-control border border-line bg-canvas p-3" data-testid={ids.integrationSummary || 'outbound-integration-summary'}>
        <div className="mb-1.5 text-meta font-medium text-fg-body">This call will use</div>
        <IntegrationSelectionSummary selection={callIntegrations} options={integrationOptions.items}
          emptyText="No apps chosen for this call: the agent uses its saved app settings." />
      </div>

      <ul className="space-y-1.5 text-ui text-fg-body" data-testid={ids.facts || 'outbound-call-facts'}>
        {showCost && (
          <li className="flex flex-wrap items-center gap-1.5" data-testid="outbound-call-cost">
            <Zap className="w-3.5 h-3.5 text-fg-subtle" aria-hidden="true" />
            <span>Phone call rate</span>
            <span className="font-mono font-semibold tabular-nums text-ink">
              {rate ? `₹${rate.inr.toFixed(2)}/min ($${rate.usd.toFixed(3)}/min)` : 'Price not available'}
            </span>
            <span className="text-fg-muted">
              · Wallet <span className="font-mono tabular-nums">{amounts.primary}</span>{minutes !== null ? ` · about ${minutes} min` : ''}
            </span>
          </li>
        )}
        {agent?.recordingDisclosureEnabled && (
          <li className="flex items-start gap-1.5" data-testid="outbound-recording-notice">
            <Mic className="mt-0.5 w-3.5 h-3.5 shrink-0 text-fg-subtle" aria-hidden="true" />
            <span>The call opens with your recording notice, and it is recorded.</span>
          </li>
        )}
        <li className="text-meta text-fg-muted">The agent uses its saved script and voice. Do-not-call lists and calling hours still apply.</li>
      </ul>

      {paused && (
        <div className="rounded-control border border-warning-line bg-warning-soft p-2.5 text-ui text-warning-fg flex flex-wrap items-center justify-between gap-2" data-testid="outbound-agent-paused">
          <span>{agent?.name || 'This agent'} is paused. Turn them on to make real calls.</span>
          <button type="button" onClick={turnOn} disabled={busy} className="font-semibold text-accent-fg hover:underline shrink-0 rounded-control focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
            Turn on
          </button>
        </div>
      )}

      {error && (
        <p className="rounded-control border border-danger-line bg-danger-soft px-3 py-2 text-ui text-danger-fg" role="alert" data-testid={ids.error || 'outbound-call-error'}>
          {error}
        </p>
      )}

      <TactileButton variant="brand" size="md" icon={PhoneCall} loading={busy} onClick={submit}
        disabled={!agentId || paused || !lines.length}
        data-testid={ids.submit || 'outbound-call-submit'} className="w-full sm:w-auto justify-center min-h-[44px]">
        {busy ? busyLabel : submitLabel}
      </TactileButton>
    </div>
  );
}
