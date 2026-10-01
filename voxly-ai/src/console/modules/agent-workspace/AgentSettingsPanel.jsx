import React, { useState } from 'react';
import { Phone, Save, CheckCircle2 } from 'lucide-react';
import { SolidCard } from '../../ui/SolidCard';
import { StatusBadge } from '../../ui/StatusBadge';
import { TactileButton } from '../../ui/TactileButton';
import { useWorkspace } from '../../context/WorkspaceContext';
import { showToast } from '../../ui/ToastHost';
import { LANGUAGE_OPTIONS } from '../../../lib/voicePresets';
import { api } from '../../../services/api';

/**
 * Agent identity and number assignment.
 *
 * Every control maps to a call the console already makes: `updateAgent` for
 * name/status/language and `assignNumberToAgent` for the number. There is no
 * website, support-email or retention field here because `api.agents.update` does
 * not accept one — those belong in the script text until the API grows them.
 */
export function AgentSettingsPanel({ agent, onOpenBuyNumber }) {
  const { phoneNumbers, assignNumberToAgent, updateAgent, toggleAgentStatus } = useWorkspace();
  const [name, setName] = useState(agent?.name || '');
  const [language, setLanguage] = useState(
    (agent?.languages && agent.languages[0]) || agent?.language || 'en-US'
  );
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [assigning, setAssigning] = useState(false);
  const [error, setError] = useState(null);

  // Re-seed when the header switcher moves to a different agent.
  const agentId = agent?.id;
  const [seedFor, setSeedFor] = useState(agentId);
  if (agentId !== seedFor) {
    setSeedFor(agentId);
    setName(agent?.name || '');
    setLanguage((agent?.languages && agent.languages[0]) || agent?.language || 'en-US');
  }

  const assigned = phoneNumbers.find((n) => n.assignedAgentId === agentId);
  const currentNumberId = assigned?.id || agent?.numberId || '';
  const isActive = agent?.status === 'active';

  const saveIdentity = async () => {
    if (!agentId || saving) return;
    setSaving(true);
    setError(null);
    try {
      await updateAgent(agentId, {
        name: name.trim(),
        status: agent.status,
        languages: [language],
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
              className="mt-1 w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs text-[#0F0E17] focus:border-[#6344E7] focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="text-[11px] font-bold text-[#0F0E17]">Spoken language</span>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              data-testid="agent-settings-language"
              className="mt-1 w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs"
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
          className="w-full bg-white border border-[#E4E2EB] rounded-xl px-3 py-2 text-sm font-mono disabled:opacity-50"
        >
          <option value="">No number — browser test calls only</option>
          {phoneNumbers.map((n) => (
            <option
              key={n.id}
              value={n.id}
              disabled={n.assignedAgentId && n.assignedAgentId !== agentId}
            >
              {n.number}
              {n.assignedAgentId && n.assignedAgentId !== agentId
                ? ' (assigned elsewhere)'
                : ''}
              {!n.assignedAgentId ? ' · available' : ''}
            </option>
          ))}
        </select>
      </SolidCard>
    </div>
  );
}