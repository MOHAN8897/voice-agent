import React, { useMemo, useState } from 'react';
import { Phone, Save, CheckCircle2 } from 'lucide-react';
import { SolidCard } from '../../ui/SolidCard';
import { StatusBadge } from '../../ui/StatusBadge';
import { TactileButton } from '../../ui/TactileButton';
import { useWorkspace } from '../../context/WorkspaceContext';
import { showToast } from '../../ui/ToastHost';
import { LANGUAGE_OPTIONS } from '../../../lib/voicePresets';
import { api } from '../../../services/api';
import { TelephonySettingsCard } from '../TelephonySettingsCard';

/**
 * Agent identity and number assignment.
 *
 * Every control maps to a call the console already makes: `updateAgent` for
 * name/status/language and `assignNumberToAgent` for the number. There is no
 * website, support-email or retention field here because `api.agents.update` does
 * not accept one — those belong in the script text until the API grows them.
 */
export function AgentSettingsPanel({ agent, onOpenBuyNumber }) {
  const { phoneNumbers, agents, assignNumberToAgent, updateAgent, toggleAgentStatus } = useWorkspace();
  const [name, setName] = useState(agent?.name || '');
  const [language, setLanguage] = useState(
    (agent?.languages && agent.languages[0]) || agent?.language || 'en-US'
  );
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const [error, setError] = useState(null);
  const [compliance, setCompliance] = useState(null);
  const [complianceLoading, setComplianceLoading] = useState(false);
  const [complianceError, setComplianceError] = useState(null);
  const [recordingDisclosureEnabled, setRecordingDisclosureEnabled] = useState(
    Boolean(agent?.recordingDisclosureEnabled)
  );
  const [recordingDisclosureText, setRecordingDisclosureText] = useState(
    agent?.recordingDisclosureText || 'This call may be recorded for quality and training purposes.'
  );
  const [disclosureSaving, setDisclosureSaving] = useState(false);
  const [disclosureSaved, setDisclosureSaved] = useState(false);

  // Re-seed when the header switcher moves to a different agent.
  const agentId = agent?.id;
  const [seedFor, setSeedFor] = useState(agentId);
  if (agentId !== seedFor) {
    setSeedFor(agentId);
    setName(agent?.name || '');
    setLanguage((agent?.languages && agent.languages[0]) || agent?.language || 'en-US');
    setRecordingDisclosureEnabled(Boolean(agent?.recordingDisclosureEnabled));
    setRecordingDisclosureText(
      agent?.recordingDisclosureText || 'This call may be recorded for quality and training purposes.'
    );
  }

  // Compliance is per agent, so it is fetched on selection rather than held in
  // the workspace. A failure here must not blank the rest of the settings panel.
  React.useEffect(() => {
    if (!agentId) {
      setCompliance(null);
      return undefined;
    }
    let cancelled = false;
    setComplianceLoading(true);
    setComplianceError(null);
    api.telephony
      .getAgentCompliance(agentId)
      .then((row) => {
        if (!cancelled) setCompliance(row);
      })
      .catch((e) => {
        if (cancelled) return;
        setComplianceError(e?.message || 'Could not load compliance obligations');
      })
      .finally(() => {
        if (!cancelled) setComplianceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId]);

  const toggleCompliance = async (key, next) => {
    if (!agentId) return;
    const previous = compliance;
    // Optimistic: a checkbox that waits on the network feels broken.
    setCompliance((prev) =>
      prev ? { ...prev, acknowledged: { ...prev.acknowledged, [key]: next } } : prev
    );
    try {
      const saved = await api.telephony.saveAgentCompliance(agentId, {
        acknowledged: { ...(previous?.acknowledged || {}), [key]: next },
      });
      setCompliance(saved);
    } catch (e) {
      setCompliance(previous);
      showToast(e?.message || 'Could not save compliance setting', 'error');
    }
  };

  const assigned = phoneNumbers.find((n) => n.assignedAgentId === agentId);
  const currentNumberId = assigned?.id || agent?.numberId || '';
  const isActive = agent?.status === 'active';

  /**
   * A number is only genuinely taken if its owner is an agent that still exists.
   *
   * `assignedAgentId` could survive the owner being deleted (the row is archived,
   * not removed, when call history blocks a hard delete), which made freed numbers
   * render as "(assigned elsewhere)" and — worse — be disabled, so the pool looked
   * empty. Treating an unknown owner as unassigned keeps the pool truthful even if
   * the server ever regresses; the real fix is in delete_agent and the FK.
   */
  const knownAgentIds = useMemo(() => new Set((agents || []).map((a) => a.id)), [agents]);
  const ownerOf = (n) =>
    n.assignedAgentId && knownAgentIds.has(n.assignedAgentId) ? n.assignedAgentId : null;
  const isTakenByOther = (n) => {
    const owner = ownerOf(n);
    return Boolean(owner && owner !== agentId);
  };

  const saveIdentity = async () => {
    if (!agentId || saving) return;
    setSaving(true);
    setError(null);
    try {
      await updateAgent(agentId, {
        name: name.trim(),
        status: agent.status,
        languages: [language],
        recordingDisclosureEnabled,
        recordingDisclosureText: recordingDisclosureText.trim(),
      });
      // Keep voice-section language in sync so web + phone stacks both pick it up.
      try {
        const brain = await api.agents.getBusinessBrain(agentId);
        const voice = brain?.voice || {};
        await api.agents.saveVoice(agentId, {
          voiceId: voice.voiceId || voice.realtimeVoice || 'marin',
          speed: voice.speed ?? 1,
          language,
        });
      } catch {
        /* language on agent row still applies via saas_stack preference */
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
      showToast('Language and identity saved for web and phone calls', 'success');
    } catch (e) {
      setError(e.message || 'Could not save agent');
    } finally {
      setSaving(false);
    }
  };

  const toggleStatus = async () => {
    if (!agentId || saving) return;
    setSaving(true);
    setError(null);
    try {
      await toggleAgentStatus(agentId, isActive ? 'paused' : 'active');
      showToast(isActive ? 'Agent paused' : 'Agent activated', 'success');
    } catch (e) {
      setError(e.message || 'Could not change status');
    } finally {
      setSaving(false);
    }
  };

  const onAssign = async (nextId) => {
    if (!agentId || assigning) return;
    setAssigning(true);
    setError(null);
    try {
      if (assigned && assigned.id !== nextId) await assignNumberToAgent(assigned.id, '');
      if (nextId) await assignNumberToAgent(nextId, agentId, agent.name);
    } catch (e) {
      setError(e.message || 'Could not assign number');
    } finally {
      setAssigning(false);
    }
  };

  const saveDisclosureSettings = async () => {
    if (!agentId || disclosureSaving) return;
    setDisclosureSaving(true);
    setError(null);
    try {
      await updateAgent(agentId, {
        recordingDisclosureEnabled,
        recordingDisclosureText:
          recordingDisclosureText.trim() || 'This call may be recorded for quality and training purposes.',
      });
      setDisclosureSaved(true);
      setTimeout(() => setDisclosureSaved(false), 2500);
      showToast('Recording disclosure saved', 'success');
    } catch (e) {
      setError(e.message || 'Could not save recording disclosure');
      showToast(e.message || 'Could not save recording disclosure', 'error');
    } finally {
      setDisclosureSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      {error && (
        <div
          role="alert"
          data-testid="agent-settings-error"
          className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900"
        >
          {error}
        </div>
      )}

      <SolidCard>
        <h3 className="text-xs font-bold text-[#0F0E17] mb-4">Identity</h3>
        <div className="grid sm:grid-cols-2 gap-4">
          <label className="block">
            <span className="text-[11px] font-bold text-[#0F0E17]">Agent name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={255}
              data-testid="agent-settings-name"
              className="mt-1 w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-base sm:text-xs min-h-[42px] sm:min-h-[36px] text-[#0F0E17] focus:border-[#6344E7] focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="text-[11px] font-bold text-[#0F0E17]">Spoken language</span>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              data-testid="agent-settings-language"
              className="mt-1 w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-base sm:text-xs min-h-[42px] sm:min-h-[36px] text-[#0F0E17]"
            >
              {LANGUAGE_OPTIONS.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
            <span className="block text-[10px] text-[#8C879A] mt-1">
              Sets the language the agent speaks and its opening line.
            </span>
          </label>
        </div>
        <div className="flex items-center justify-between gap-3 mt-4">
          <StatusBadge status={isActive ? 'Active' : 'Paused'} size="xs" />
          <TactileButton
            variant="primary"
            size="sm"
            icon={saved ? CheckCircle2 : Save}
            onClick={saveIdentity}
            loading={saving}
            disabled={!name.trim()}
            data-testid="agent-settings-save"
          >
            {saved ? 'Saved' : 'Save identity'}
          </TactileButton>
        </div>
      </SolidCard>

      <SolidCard>
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-xs font-bold text-[#0F0E17]">Live / Pause</h3>
            <p className="text-[11px] text-[#524E5E] mt-0.5">
              Off = agent keeps script and number but will not take browser or phone calls.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={isActive}
            data-testid="agent-settings-toggle-status"
            onClick={toggleStatus}
            disabled={saving}
            className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full border transition-colors disabled:opacity-50 ${
              isActive
                ? 'bg-emerald-500 border-emerald-600'
                : 'bg-[#D1CFDB] border-[#C4C0D0]'
            }`}
          >
            <span
              className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${
                isActive ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
            <span className="sr-only">{isActive ? 'Live' : 'Paused'}</span>
          </button>
        </div>
        <p className="mt-2 text-[11px] font-semibold text-[#0F0E17]">
          {isActive ? 'Live — accepting calls' : 'Paused — calls blocked'}
        </p>
      </SolidCard>

      <SolidCard>
        <div className="flex items-center justify-between gap-3 mb-4">
          <div>
            <h3 className="text-xs font-bold text-[#0F0E17]">Phone number</h3>
            <p className="text-[11px] text-[#524E5E] mt-0.5">
              The line callers reach, and the caller ID this agent dials from.
            </p>
          </div>
          <TactileButton
            variant="secondary"
            size="sm"
            icon={Phone}
            onClick={onOpenBuyNumber}
            data-testid="agent-settings-buy-number"
          >
            Buy a number
          </TactileButton>
        </div>
        <select
          value={currentNumberId}
          onChange={(e) => onAssign(e.target.value)}
          disabled={assigning}
          data-testid="agent-settings-number"
          aria-label="Assigned phone number"
          className="w-full bg-white border border-[#E4E2EB] rounded-xl px-3 py-2 text-base sm:text-xs min-h-[42px] sm:min-h-[36px] font-mono text-[#0F0E17] disabled:opacity-50"
        >
          <option value="">No number — browser test calls only</option>
          {phoneNumbers.map((n) => {
            const taken = isTakenByOther(n);
            const owner = ownerOf(n);
            return (
              <option key={n.id} value={n.id} disabled={taken}>
                {n.number}
                {taken ? ' (assigned elsewhere)' : ''}
                {!owner ? ' · available' : ''}
              </option>
            );
          })}
        </select>
      </SolidCard>

      {/* Call Settings & Operating Schedule */}
      {agentId && (
        <div className="space-y-2">
          <TelephonySettingsCard agentId={agentId} />
        </div>
      )}

      {/* Call Recording & Disclosure */}
      <SolidCard className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-xs font-bold text-[#0F0E17]">Call Recording &amp; Disclosure</h3>
            <p className="text-[11px] text-[#524E5E] mt-0.5">
              The agent will naturally deliver this disclosure during its first response turn after the caller speaks.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={recordingDisclosureEnabled}
            data-testid="agent-recording-disclosure-toggle"
            onClick={() => setRecordingDisclosureEnabled(!recordingDisclosureEnabled)}
            disabled={disclosureSaving}
            className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full border transition-colors disabled:opacity-50 ${
              recordingDisclosureEnabled
                ? 'bg-[#FF5C35] border-[#FF5C35]'
                : 'bg-[#D1CFDB] border-[#C4C0D0]'
            }`}
          >
            <span
              className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${
                recordingDisclosureEnabled ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
            <span className="sr-only">Enable recording disclosure</span>
          </button>
        </div>

        {recordingDisclosureEnabled && (
          <div className="space-y-3 pt-2 border-t border-[#E4E2EB]">
            <label className="block">
              <span className="text-[11px] font-bold text-[#0F0E17]">Disclosure script:</span>
              <textarea
                value={recordingDisclosureText}
                onChange={(e) => setRecordingDisclosureText(e.target.value)}
                rows={2}
                data-testid="agent-recording-disclosure-text"
                placeholder="This call may be recorded for quality and training purposes."
                className="mt-1 w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs text-[#0F0E17] focus:border-[#6344E7] focus:outline-none"
              />
            </label>
            <p className="text-[10px] text-[#8C879A]">
              Spoken conversationally after the customer responds to the opening greeting. Zero legal disclaimers play in the sub-500ms prewarm greeting.
            </p>
          </div>
        )}

        <div className="flex justify-end pt-1">
          <TactileButton
            variant="secondary"
            size="sm"
            icon={disclosureSaved ? CheckCircle2 : Save}
            onClick={saveDisclosureSettings}
            loading={disclosureSaving}
            data-testid="agent-recording-disclosure-save"
          >
            {disclosureSaved ? 'Saved' : 'Save disclosure'}
          </TactileButton>
        </div>
      </SolidCard>

      {/* Compliance. Advisory only — these toggles record what the operator has
          confirmed and never change how a call is placed. */}
      <SolidCard>
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h3 className="text-xs font-bold text-[#0F0E17]">Compliance</h3>
            <p className="text-[11px] text-[#524E5E] mt-0.5">
              Obligations for the market this agent numbers in. Confirm each one you meet.
            </p>
          </div>
          {compliance && (
            <span
              data-testid="agent-compliance-regulation"
              className="shrink-0 rounded-full bg-[#F0EEF6] border border-[#E4E2EB] px-2.5 py-1 text-[10px] font-semibold text-[#524E5E]"
            >
              {compliance.country} · {compliance.regulation}
            </span>
          )}
        </div>

        {complianceLoading && (
          <p className="text-[11px] text-[#8C879A]">Loading obligations…</p>
        )}
        {complianceError && (
          <p className="text-[11px] text-red-600" data-testid="agent-compliance-error">
            {complianceError}
          </p>
        )}

        {compliance && (
          <>
            <p className="text-[11px] text-[#524E5E] mb-3">{compliance.summary}</p>
            <ul className="space-y-2">
              {(compliance.acknowledged ? Object.entries(compliance.acknowledged) : []).map(
                ([key, on]) => (
                  <li key={key} className="flex items-start justify-between gap-3">
                    <label className="flex items-start gap-2 text-[12px] text-[#0F0E17] capitalize">
                      <input
                        type="checkbox"
                        checked={Boolean(on)}
                        onChange={(e) => toggleCompliance(key, e.target.checked)}
                        data-testid={`agent-compliance-${key}`}
                        className="mt-0.5 h-4 w-4 shrink-0"
                      />
                      <span>{key.replace(/_/g, ' ')}</span>
                    </label>
                  </li>
                )
              )}
            </ul>
            <p className="text-[10px] text-[#8C879A] mt-3">
              Recorded against this agent. These are notes for your compliance review — they do
              not change how calls are placed.
            </p>
          </>
        )}
      </SolidCard>
    </div>
  );
}