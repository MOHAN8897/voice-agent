import React, { useCallback, useEffect, useState } from 'react';
import { Sparkles, Zap, Megaphone } from 'lucide-react';
import { Modal } from '../ui/Modal';
import { TactileButton } from '../ui/TactileButton';
import { useWorkspace } from '../context/WorkspaceContext';
import { api } from '../../services/api';
import { EMPLOYEE_MODES, INDUSTRY_CHIPS, PRIMARY_LANGUAGES } from '../../lib/employeeCreate';

export function CreateAgentWizard({ isOpen, onClose, onNavigate }) {
  const { loadWorkspaceData } = useWorkspace();
  const [mode, setMode] = useState('instant_lead');
  const [language, setLanguage] = useState('en-IN');
  const [naturalSpokenStyle, setNaturalSpokenStyle] = useState(false);
  const [brief, setBrief] = useState('');
  const [industry, setIndustry] = useState('');
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    setBrief('');
    setMode('instant_lead');
    setLanguage('en-IN');
    setNaturalSpokenStyle(false);
    setIndustry('');
  }, [isOpen]);

  const appendIndustry = (chip) => {
    setIndustry(chip.id);
    const text = chip.snippet;
    setBrief((prev) => (prev.trim() ? `${prev.trim()}\n\n${text}` : text));
  };

  const runBuild = useCallback(async () => {
    if (brief.trim().length < 8) {
      setError('Describe the job in a few sentences (at least 8 characters).');
      return;
    }
    setBuilding(true);
    setError(null);
    try {
      const result = await api.agents.buildEmployee({
        brief: brief.trim(),
        language,
        mode,
        industry,
        naturalSpokenStyle: naturalSpokenStyle,
      });
      await loadWorkspaceData();
      onClose();
      onNavigate('employees', { agentId: result.id, step: 'script' });
    } catch (e) {
      setError(e.message || 'Could not build employee');
    } finally {
      setBuilding(false);
    }
  }, [brief, language, mode, industry, naturalSpokenStyle, loadWorkspaceData, onClose, onNavigate]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        if (!building) runBuild();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, building, runBuild]);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Build my employee"
      subtitle="Describe the job in a few sentences. Script and brain publish automatically — tune voice and phone lines in the builder."
      maxWidth="max-w-2xl"
      panelClassName="shadow-craft-lg"
    >
      <div data-testid="create-employee-modal" className="space-y-5">
        <div className="flex items-center justify-between gap-3 rounded-xl border border-[#E4E2EB] bg-[#FAF9FD] px-3 py-2">
          <p className="text-xs text-[#524E5E]">You only pay for the calls they make.</p>
          <span className="shrink-0 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-lg bg-[#ECFDF5] text-[#047857] border border-[#A7F3D0]">
            Included
          </span>
        </div>

        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Call mode">
          {EMPLOYEE_MODES.map((m) => {
            const Icon = m.icon === 'megaphone' ? Megaphone : Zap;
            const active = mode === m.id;
            return (
              <button
                key={m.id}
                type="button"
                role="tab"
                aria-selected={active}
                data-testid={`employee-mode-${m.id}`}
                onClick={() => setMode(m.id)}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold border transition-all ${
                  active
                    ? 'bg-[#0F0E17] text-white border-[#0F0E17] shadow-2xs'
                    : 'bg-white text-[#524E5E] border-[#E4E2EB] hover:border-[#6344E7]/40 hover:text-[#0F0E17]'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {m.label}
              </button>
            );
          })}
        </div>

        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A] mb-2">Primary language</p>
          <div className="flex flex-wrap gap-1.5">
            {PRIMARY_LANGUAGES.map((lang) => {
              const active = language === lang.code;
              return (
                <button
                  key={lang.code}
                  type="button"
                  data-testid={`employee-lang-${lang.code}`}
                  onClick={() => setLanguage(lang.code)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition-colors ${
                    active
                      ? 'bg-[#6344E7]/10 border-[#6344E7] text-[#5034CE]'
                      : 'bg-[#FAF9FD] border-[#E4E2EB] text-[#524E5E] hover:border-[#D1CFDB]'
                  }`}
                  title={lang.sub}
                >
                  {lang.label}
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <label htmlFor="employee-brief" className="block text-xs font-bold text-[#0F0E17] mb-1.5">
            What should this employee do on calls?
          </label>
          <textarea
            id="employee-brief"
            data-testid="employee-brief-input"
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            rows={7}
            placeholder="Example: We are Sai Constructions, Hyderabad. Greet leads about flats, ask budget and 2/3 BHK, book a site visit, thank them and confirm WhatsApp follow-up."
            className="w-full rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] px-3.5 py-3 text-sm text-[#0F0E17] placeholder:text-[#8C879A] focus:outline-none focus:border-[#6344E7] resize-none leading-relaxed"
          />
        </div>

        <div className="flex flex-wrap gap-2">
          {INDUSTRY_CHIPS.map((chip) => (
            <button
              key={chip.id}
              type="button"
              data-testid={`employee-industry-${chip.id}`}
              onClick={() => appendIndustry(chip)}
              className={`text-[11px] font-semibold px-3 py-1.5 rounded-full border transition-colors ${
                industry === chip.id
                  ? 'bg-[#F0EEF6] border-[#6344E7] text-[#5034CE]'
                  : 'bg-white border-[#E4E2EB] text-[#524E5E] hover:border-[#6344E7]/35'
              }`}
            >
              <span className="mr-1" aria-hidden>{chip.emoji}</span>
              {chip.label}
            </button>
          ))}
        </div>

        {!language.startsWith('en') && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-[#E4E2EB] bg-white px-3 py-2.5">
            <label className="flex items-center gap-2 text-xs font-semibold text-[#0F0E17] cursor-pointer select-none">
              <input
                type="checkbox"
                data-testid="employee-natural-spoken-style"
                checked={naturalSpokenStyle}
                onChange={(e) => setNaturalSpokenStyle(e.target.checked)}
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

        <div className="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3 pt-2 border-t border-[#E4E2EB]">
          <p className="text-[11px] text-[#8C879A] hidden sm:block">
            <kbd className="font-mono text-[#524E5E] px-1 rounded bg-[#F0EEF6] border border-[#E4E2EB]">⌘</kbd>
            <span className="mx-1">+</span>
            <kbd className="font-mono text-[#524E5E] px-1 rounded bg-[#F0EEF6] border border-[#E4E2EB]">Enter</kbd>
            to build
          </p>
          <div className="flex gap-2 sm:ml-auto">
            <TactileButton variant="ghost" size="sm" onClick={onClose} disabled={building}>
              Cancel
            </TactileButton>
            <TactileButton
              variant="brand"
              size="md"
              icon={Sparkles}
              loading={building}
              data-testid="employee-build-submit"
              onClick={runBuild}
            >
              Build my employee
            </TactileButton>
          </div>
        </div>

        <p className="text-[10px] text-center text-[#8C879A]">
          Uses {'{{tags}}'} in the script for caller and business fields. Voice, knowledge, and numbers are set in the builder.
        </p>
      </div>
    </Modal>
  );
}
