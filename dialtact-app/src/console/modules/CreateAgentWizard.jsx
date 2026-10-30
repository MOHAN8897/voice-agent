import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Sparkles, Megaphone, Zap } from 'lucide-react';
import { Modal } from '../ui/Modal';
import { useWorkspace } from '../context/WorkspaceContext';
import { api } from '../../services/api';
import {
  AGENT_ROLES,
  BRIEF_MIN_CHARS,
  BRIEF_PLACEHOLDER,
  CALL_MODES,
  DEFAULT_ENABLED_LANGUAGE_CODES,
  INDUSTRY_CHIPS,
  toLanguageOptions,
} from './agent-creation';

const EMPTY_DRAFT = {
  brief: '',
  language: DEFAULT_ENABLED_LANGUAGE_CODES[0],
  mode: 'instant_lead',
  role: 'sales',
  direction: 'outbound',
  industry: '',
  naturalSpokenStyle: false,
};

/** Check the brief, clarify gaps, then write and review the business script. */
export function CreateAgentWizard({ isOpen, onClose, onNavigate }) {
  const { loadWorkspaceData, agents, selectedAgentId, setSelectedAgentId } = useWorkspace();
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [phase, setPhase] = useState('brief');
  const creationRequestRef = useRef(null);
  const creatingRef = useRef(false);
  // Which languages exist is an admin setting, not a bundle constant.
  const [languageOptions, setLanguageOptions] = useState(() =>
    toLanguageOptions(null)
  );

  const set = useCallback((patch) => setDraft((prev) => ({ ...prev, ...patch })), []);

  useEffect(() => {
    if (!isOpen) return;
    setDraft(EMPTY_DRAFT);
    setError(null);
    setQuestions([]);
    setAnswers({});
    setPhase('brief');
    creationRequestRef.current = null;
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    api.agents
      .languages()
      .then((languages) => {
        if (cancelled) return;
        const options = toLanguageOptions(languages);
        setLanguageOptions(options);
        // Keep the draft on a language the platform still offers.
        setDraft((prev) =>
          options.some((o) => o.code === prev.language)
            ? prev
            : { ...prev, language: options[0]?.code || prev.language }
        );
      })
      .catch(() => {
        /* keep the bundled fallback labels */
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, set]);

  const briefWords = draft.brief.trim() ? draft.brief.trim().split(/\s+/).length : 0;
  const ready = draft.brief.trim().length >= BRIEF_MIN_CHARS && draft.brief.length <= 6000 && briefWords <= 1200;
  const answersReady = questions.every((question) => {
    const value = answers[question.field];
    return value?.answer?.trim() || (!question.required && value?.unavailable);
  });

  useEffect(() => {
    if (phase === 'questions') document.getElementById('employee-answer-0')?.focus();
  }, [phase, questions]);

  const appendIndustry = (chip) => {
    const text = chip.snippet;
    setDraft((prev) => ({
      ...prev,
      industry: chip.id,
      brief: prev.brief.trim() ? `${prev.brief.trim()}\n\n${text}` : text,
    }));
  };

  /** Clarification is read-only; create only after the brief is ready. */
  const createAgent = useCallback(async () => {
    if (creatingRef.current) return;
    if (!ready) {
      setError('Describe the job in at least 8 characters, up to 6,000 characters and 1,200 words.');
      return;
    }
    if (phase === 'questions' && !answersReady) return;
    setBusy(true);
    creatingRef.current = true;
    setError(null);
    let buildStarted = false;
    try {
      const clarificationAnswers = Object.values(answers)
        .filter((item) => item.answer.trim() || item.unavailable)
        .map((item) => ({ ...item, answer: item.unavailable ? '' : item.answer.trim() }));
      const payload = { ...draft, brief: draft.brief.trim(), clarificationAnswers };
      setPhase('checking');
      const analysis = await api.agents.analyzeEmployee(payload);
      if (analysis.status === 'needs_user_input' && analysis.questions?.length) {
        setQuestions(analysis.questions);
        setPhase('questions');
        return;
      }
      if (analysis.status !== 'ready') throw new Error('The brief could not be checked. Please try again.');
      setPhase('writing');
      const fingerprint = JSON.stringify(payload);
      if (creationRequestRef.current?.fingerprint !== fingerprint) {
        creationRequestRef.current = { fingerprint, id: crypto.randomUUID(), retryable: false };
      }
      buildStarted = true;
      const result = await api.agents.buildEmployee({
        ...payload,
        requestId: creationRequestRef.current.id,
        retryFailed: creationRequestRef.current.retryable === true,
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
      if (buildStarted && creationRequestRef.current) {
        // A transient provider failure keeps this draft; the next press resumes it
        // instead of replaying the recorded failure.
        creationRequestRef.current.retryable = e?.retryable === true;
      }
      setError(e.message || 'Could not create the agent');
      setPhase(questions.length ? 'questions' : 'brief');
    } finally {
      creatingRef.current = false;
      setBusy(false);
    }
  }, [draft, ready, answers, answersReady, phase, questions.length, loadWorkspaceData, agents, selectedAgentId, setSelectedAgentId, onClose, onNavigate]);

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
      onClose={() => { if (!busy) onClose(); }}
      title={questions.length && phase !== 'brief' ? 'A few details for your agent' : 'Create an AI employee'}
      subtitle="Tell us the job. We’ll ask about any gaps, then write and check your calling script."
      maxWidth="max-w-3xl"
      panelClassName="shadow-craft-lg"
    >
      <div data-testid="create-employee-modal" className="space-y-4">
        <fieldset disabled={busy} className="min-w-0 space-y-4">
        {questions.length > 0 && phase !== 'brief' ? (
          <div data-testid="employee-clarification-panel" className="space-y-5">
            <p className="text-sm text-[#524E5E]">These details will help us write an accurate script. If an optional detail is unavailable, your agent will say it doesn’t know.</p>
            {questions.map((question, index) => {
              const value = answers[question.field] || { field: question.field, question: question.question, answer: '', unavailable: false };
              const update = (patch) => setAnswers((previous) => ({ ...previous, [question.field]: { ...value, question: question.question, ...patch } }));
              return (
                <div key={question.field}>
                  <label htmlFor={`employee-answer-${index}`} className="block text-sm font-semibold text-[#0F0E17] mb-1.5">{question.question}</label>
                  {question.reason && <p id={`employee-reason-${index}`} className="text-xs text-[#524E5E] mb-2">{question.reason}</p>}
                  <textarea
                    id={`employee-answer-${index}`}
                    data-testid={`employee-answer-${question.field}`}
                    aria-describedby={question.reason ? `employee-reason-${index}` : undefined}
                    required={question.required}
                    disabled={value.unavailable}
                    value={value.answer}
                    onChange={(event) => update({ answer: event.target.value })}
                    maxLength={1500}
                    rows={3}
                    className="w-full rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] px-3 py-2.5 text-sm text-[#0F0E17] focus:outline-none focus:border-[#6344E7] disabled:opacity-50"
                  />
                  {!question.required && <label className="mt-2 flex items-center gap-2 text-xs text-[#524E5E]">
                    <input type="checkbox" checked={value.unavailable} onChange={(event) => update({ unavailable: event.target.checked })} data-testid={`employee-unknown-${question.field}`} />
                    This information is unavailable or doesn’t apply
                  </label>}
                </div>
              );
            })}
            <button type="button" onClick={() => { setPhase('brief'); setError(null); }} className="text-xs font-semibold text-[#6344E7] underline" data-testid="employee-edit-brief">Edit the original brief</button>
          </div>
        ) : (
        <>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-[11px] text-[#524E5E]">
            <Sparkles className="w-3.5 h-3.5 text-[#6344E7]" />
            <span>We’ll check the details before creating your agent.</span>
          </div>
          <p className="hidden sm:block text-[11px] text-[#8C879A] shrink-0">
            <kbd className="font-mono text-[#524E5E] px-1 rounded bg-[#F0EEF6] border border-[#E4E2EB]">
              ⌘
            </kbd>
            <span className="mx-1">+</span>
            <kbd className="font-mono text-[#524E5E] px-1 rounded bg-[#F0EEF6] border border-[#E4E2EB]">
              Enter
            </kbd>
            to continue
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
            maxLength={6000}
            placeholder={BRIEF_PLACEHOLDER}
            className="w-full rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] px-3.5 py-3 text-base sm:text-sm text-[#0F0E17] placeholder:text-[#8C879A] focus:outline-none focus:border-[#6344E7] resize-y leading-relaxed"
          />
          <p className="text-[10px] text-[#8C879A] mt-1">
            Write it the way you would brief a new employee — include the agent&rsquo;s name, your
            business, and what you want them to say.
            {' '}{draft.brief.length}/6,000 characters · {briefWords}/1,200 words.
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
                className={`text-[11px] font-semibold px-3 py-1.5 min-h-[36px] flex items-center rounded-full border transition-colors ${
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

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A] mb-2">
              Spoken language
            </p>
            <select
              value={draft.language}
              onChange={(e) => set({ language: e.target.value })}
              data-testid="employee-language-select"
              className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-base sm:text-xs min-h-[42px] sm:min-h-[36px]"
            >
              {languageOptions.map((lang) => (
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
              className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-base sm:text-xs min-h-[42px] sm:min-h-[36px]"
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
        </>
        )}
        </fieldset>

        {busy && <p role="status" className="text-xs text-[#524E5E]" data-testid="employee-creation-progress">{phase === 'writing' ? 'Writing and checking your script…' : 'Checking your brief and answers…'}</p>}

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
          nextLabel={phase === 'questions' ? 'Continue with these answers' : 'Check brief & create agent'}
          nextDisabled={!ready || (phase === 'questions' && !answersReady)}
          busy={busy}
          busyLabel={phase === 'writing' ? 'Writing & checking…' : 'Checking details…'}
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
        className="w-full sm:w-auto px-5 py-2.5 min-h-[44px] rounded-xl bg-[#0F0E17] text-white text-xs font-bold disabled:opacity-40 sm:ml-auto flex items-center justify-center transition-all active:scale-[0.98]"
      >
        {busy && busyLabel ? busyLabel : nextLabel}
      </button>
    </div>
  );
}
