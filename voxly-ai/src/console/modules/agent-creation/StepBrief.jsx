import React from 'react';
import { Megaphone, Zap } from 'lucide-react';
import {
  AGENT_ROLES,
  BRIEF_MIN_CHARS,
  BRIEF_PLACEHOLDER,
  CALL_MODES,
  INDUSTRY_CHIPS,
  PRIMARY_LANGUAGES,
} from './index';

/**
 * Step 1 — Describe.
 *
 * Collects exactly what the compiler needs: what the agent does, in which language,
 * and in which role it acts on the call. Nothing is published yet.
 */
export function StepBrief({ draft, onChange, onNext, onBack, busy, error }) {
  const set = (patch) => onChange({ ...draft, ...patch });
  const ready = draft.brief.trim().length >= BRIEF_MIN_CHARS;

  const appendIndustry = (chip) => {
    const text = chip.snippet;
    set({
      industry: chip.id,
      brief: draft.brief.trim() ? `${draft.brief.trim()}\n\n${text}` : text,
    });
  };

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-bold text-[#0F0E17]">What should this agent do?</h3>
        <p className="text-[11px] text-[#524E5E] mt-0.5">
          Write it the way you would brief a new employee. The next step turns this into the
          script your agent will actually follow.
        </p>
      </div>

      <div className="flex items-center justify-between gap-3 rounded-xl border border-[#E4E2EB] bg-[#FAF9FD] px-3 py-2">
        <p className="text-xs text-[#524E5E]">You only pay for the calls they make.</p>
        <span className="shrink-0 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-lg bg-[#ECFDF5] text-[#047857] border border-[#A7F3D0]">
          Included
        </span>
      </div>

      <div>
        <p className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A] mb-2">
          What kind of calls
        </p>
        <div className="grid sm:grid-cols-2 gap-2" role="radiogroup" aria-label="Call mode">
          {CALL_MODES.map((m) => {
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
                className={`flex items-start gap-2 px-3 py-2.5 rounded-xl text-left border transition-all ${
                  active
                    ? 'bg-[#0F0E17] text-white border-[#0F0E17]'
                    : 'bg-white text-[#524E5E] border-[#E4E2EB] hover:border-[#6344E7]/40'
                }`}
              >
                <Icon className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span>
                  <span className="block text-xs font-bold">{m.label}</span>
                  <span
                    className={`block text-[10px] mt-0.5 ${active ? 'text-white/70' : 'text-[#8C879A]'}`}
                  >
                    {m.description}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
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
      </div>

      <div>
        <label htmlFor="employee-brief" className="block text-xs font-bold text-[#0F0E17] mb-1.5">
          Describe the job in a few sentences
        </label>
        <textarea
          id="employee-brief"
          data-testid="employee-brief-input"
          value={draft.brief}
          onChange={(e) => set({ brief: e.target.value })}
          rows={7}
          placeholder={BRIEF_PLACEHOLDER}
          className="w-full rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] px-3.5 py-3 text-sm text-[#0F0E17] placeholder:text-[#8C879A] focus:outline-none focus:border-[#6344E7] resize-none leading-relaxed"
        />
        <p className="text-[10px] text-[#8C879A] mt-1">
          {draft.brief.trim().length} characters. {BRIEF_MIN_CHARS} minimum.
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
        onBack={onBack}
        onNext={onNext}
        nextLabel="Create agent & write script"
        nextDisabled={!ready}
        busy={busy}
        busyLabel="Writing the script…"
      />
    </div>
  );
}

export function StepFooter({
  onBack,
  onNext,
  nextLabel,
  nextDisabled = false,
  busy = false,
  busyLabel,
  backLabel = 'Back',
}) {
  return (
    <div className="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3 pt-3 border-t border-[#E4E2EB]">
      {onBack ? (
        <button
          type="button"
          onClick={onBack}
          disabled={busy}
          data-testid="create-back"
          className="text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17] disabled:opacity-50"
        >
          {backLabel}
        </button>
      ) : (
        <span />
      )}
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
