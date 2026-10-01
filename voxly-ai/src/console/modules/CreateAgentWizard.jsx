import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Sparkles, Megaphone, Zap } from 'lucide-react';
import { Modal } from '../ui/Modal';
import { useWorkspace } from '../context/WorkspaceContext';
import { api } from '../../services/api';
import {
  AGENT_ROLES,
  BRIEF_MIN_CHARS,
  BRIEF_PLACEHOLDER,
  CALL_MODES,
  INDUSTRY_CHIPS,
  PRIMARY_LANGUAGES,
} from './agent-creation';

const EMPTY_DRAFT = {
  brief: '',
  language: 'en-IN',
  mode: 'instant_lead',
  role: 'sales',
  direction: 'outbound',
  industry: '',
  naturalSpokenStyle: false,
};

/**
 * One-step agent creation.
 *
 * The brief, the language and the role are all the compiler needs, so that is all
 * this screen asks for. The agent is created and published server-side, then the
 * flow drops the customer straight into the agent page, where the script, voice,
 * phone line and business hours are already editable — asking for them again in a
 * second, third and fourth step only delayed reaching a working agent.
 */
export function CreateAgentWizard({ isOpen, onClose, onNavigate }) {
  const { loadWorkspaceData, agents, selectedAgentId, setSelectedAgentId } = useWorkspace();
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const set = useCallback((patch) => setDraft((prev) => ({ ...prev, ...patch })), []);

  useEffect(() => {
    if (!isOpen) return;
    setDraft(EMPTY_DRAFT);
    setError(null);
  }, [isOpen]);

  const ready = draft.brief.trim().length >= BRIEF_MIN_CHARS;

  const appendIndustry = (chip) => {
    const text = chip.snippet;
    setDraft((prev) => ({
      ...prev,
      industry: chip.id,
      brief: prev.brief.trim() ? `${prev.brief.trim()}\n\n${text}` : text,
    }));
  };

  /** Brief → compiled script → published brain. One call, then hand over. */
  const createAgent = useCallback(async () => {
    if (!ready) {
      setError('Describe the job in a few sentences (at least 8 characters).');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await api.agents.buildEmployee({
        brief: draft.brief.trim(),
        language: draft.language,
        mode: draft.mode,
        role: draft.role,
        direction: draft.direction,
        industry: draft.industry,
        naturalSpokenStyle: draft.naturalSpokenStyle,
      });
      const agentId = result.id;
      if (!agentId) throw new Error('The agent was created but no id came back. Try again.');

      await loadWorkspaceData();
      // Land on the agent page so the next thing they see is their script, not a
      // wizard asking for settings they can change at any time.
      if (agents.some((a) => a.id === agentId)) setSelectedAgentId(agentId);
      else if (!selectedAgentId) setSelectedAgentId(agentId);
      onClose();
      onNavigate('employees', { agentId, step: 'script' });
    } catch (e) {
      setError(e.message || 'Could not create the agent');
    } finally {
      setBusy(false);
    }
  }, [draft, ready, loadWorkspaceData, agents, selectedAgentId, setSelectedAgentId, onClose, onNavigate]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && !busy) {
        e.preventDefault();
        createAgent();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, busy, createAgent]);

  const modeCards = useMemo(
    () =>
      CALL_MODES.map((m) => {
        const active = draft.mode === m.id;
        const Icon = m.id === 'bulk' ? Megaphone : Zap;
        return (
          <button
            key={m.id}
            type="button"
            role="radio"
            aria-checked={active}
            data-testid={`employee-mode-${m.id}`}
            onClick={() => set({ mode: m.id })}
            className={`flex items-center gap-2 px-3 py-2 rounded-xl text-left border transition-all ${
              active
                ? 'bg-[#0F0E17] text-white border-[#0F0E17]'
                : 'bg-white text-[#524E5E] border-[#E4E2EB] hover:border-[#6344E7]/40'
            }`}
          >
            <Icon className="w-3.5 h-3.5 shrink-0" />
            <span className="text-xs font-bold">{m.label}</span>
          </button>
        );
      }),
    [draft.mode, set]
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Create an AI employee"
      subtitle="Describe the job. We write the script and take you straight to the agent."
      maxWidth="max-w-3xl"
      panelClassName="shadow-craft-lg"
    >
      <div data-testid="create-employee-modal" className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-[11px] text-[#524E5E]">
            <Sparkles className="w-3.5 h-3.5 text-[#6344E7]" />
            <span>One step. Voice, phone number and business hours come next, on the agent page.</span>
          </div>
          <p className="hidden sm:block text-[11px] text-[#8C879A] shrink-0">
            <kbd className="font-mono text-[#524E5E] px-1 rounded bg-[#F0EEF6] border border-[#E4E2EB]">
              ⌘
            </kbd>
            <span className="mx-1">+</span>
            <kbd className="font-mono text-[#524E5E] px-1 rounded bg-[#F0EEF6] border border-[#E4E2EB]">
              Enter
            </kbd>
            to create
          </p>
        </div>

        <div>
          <label htmlFor="employee-brief" className="block text-xs font-bold text-[#0F0E17] mb-1.5">
            What should this agent do on calls?
          </label>
          <textarea
            id="employee-brief"
            data-testid="employee-brief-input"
            value={draft.brief}
            onChange={(e) => set({ brief: e.target.value })}
            rows={8}
            placeholder={BRIEF_PLACEHOLDER}
            className="w-full rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] px-3.5 py-3 text-sm text-[#0F0E17] placeholder:text-[#8C879A] focus:outline-none focus:border-[#6344E7] resize-y leading-relaxed"
          />
          <p className="text-[10px] text-[#8C879A] mt-1">
            Write it the way you would brief a new employee — include the agent&rsquo;s name, your
            business, and what you want them to say.
          </p>
        </div>

        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A] mb-2">
            Start from an industry (optional)
          </p>
          <div className="flex flex-wrap gap-2">
            {INDUSTRY_CHIPS.map((chip) => (
              <button
                key={chip.id}
                type="button"
                data-testid={`employee-industry-${chip.id}`}
                onClick={() => appendIndustry(chip)}
                className={`text-[11px] font-semibold px-3 py-1.5 rounded-full border transition-colors ${
                  draft.industry === chip.id
                    ? 'bg-[#F0EEF6] border-[#6344E7] text-[#5034CE]'
                    : 'bg-white border-[#E4E2EB] text-[#524E5E] hover:border-[#6344E7]/35'
                }`}
              >
                <span className="mr-1" aria-hidden>
                  {chip.emoji}
                </span>
                {chip.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid sm:grid-cols-3 gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A] mb-2">
              Spoken language
            </p>
            <select
              value={draft.language}
              onChange={(e) => set({ language: e.target.value })}
              data-testid="employee-language-select"
              className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs"
            >
              {PRIMARY_LANGUAGES.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A] mb-2">
              Role on the call
            </p>
            <select
              value={draft.role}
              onChange={(e) => set({ role: e.target.value })}
              data-testid="employee-role-select"
              className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs"
            >
              {AGENT_ROLES.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A] mb-2">
              Kind of calls
            </p>
            <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Call mode">
              {modeCards}
            </div>
          </div>
        </div>

        {!draft.language.startsWith('en') && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-[#E4E2EB] bg-white px-3 py-2.5">
            <label className="flex items-center gap-2 text-xs font-semibold text-[#0F0E17] cursor-pointer select-none">
              <input
                type="checkbox"
                data-testid="employee-natural-spoken-style"
                checked={draft.naturalSpokenStyle}
                onChange={(e) => set({ naturalSpokenStyle: e.target.checked })}
                className="rounded border-[#E4E2EB] accent-[#6344E7]"
              />
              Natural spoken style
            </label>
            <span className="text-[11px] text-[#8C879A]">
              Prefer conversational phrasing for the selected language
            </span>
          </div>
        )}

        {error && (
          <div
            data-testid="employee-create-error"
            className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900"
            role="alert"
          >
            {error}
          </div>
        )}

        <StepFooter
          onBack={null}
          onNext={createAgent}
          nextLabel="Create my agent"
          nextDisabled={!ready}
          busy={busy}
          busyLabel="Writing the script…"
        />
      </div>
    </Modal>
  );
}

/** Back / primary row. The primary is a real button so it is reachable by keyboard. */
function StepFooter({ onNext, nextLabel, nextDisabled = false, busy = false, busyLabel }) {
  return (
    <div className="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3 pt-3 border-t border-[#E4E2EB]">
      <span />
      <button
        type="button"
        onClick={onNext}
        disabled={busy || nextDisabled}
        data-testid="create-next"
        className="px-4 py-2.5 rounded-xl bg-[#0F0E17] text-white text-xs font-bold disabled:opacity-40 sm:ml-auto"
      >
        {busy && busyLabel ? busyLabel : nextLabel}
      </button>
    </div>
  );
}