import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Sparkles } from 'lucide-react';
import { Modal } from '../ui/Modal';
import { TactileButton } from '../ui/TactileButton';
import { useWorkspace } from '../context/WorkspaceContext';
import { api } from '../../services/api';
import { showToast } from '../ui/ToastHost';
import { Stepper } from './agent-creation/Stepper';
import { StepBrief } from './agent-creation/StepBrief';
import { StepScript } from './agent-creation/StepScript';
import { StepConfigure } from './agent-creation/StepConfigure';
import { StepReady } from './agent-creation/StepReady';
import { AGENT_CREATION_STEPS, BRIEF_MIN_CHARS, DEFAULT_BUSINESS_HOURS } from './agent-creation';

const EMPTY_DRAFT = {
  brief: '',
  language: 'en-IN',
  mode: 'instant_lead',
  role: 'sales',
  direction: 'inbound',
  industry: '',
  naturalSpokenStyle: false,
  agentId: null,
  agentName: '',
  generatedScript: '',
  variables: [],
  scriptDirty: false,
  telephony: null,
  telephonyDirty: false,
  voiceDirty: false,
  voiceId: '',
  speed: 1,
};

/**
 * Four-step agent creation.
 *
 * 1. Describe  — what the agent should do (compiled server-side).
 * 2. Review   — the generated brief and calling script, editable.
 * 3. Configure — voice, phone line, inbound/outbound, business hours, greeting.
 * 4. Ready     — confirm and test.
 *
 * The agent is created and published at the end of step 1, matching the back
 * panel's compile flow. Steps 2-4 only edit, so a user who abandons the flow still
 * has a working agent rather than a half-built one.
 */
export function CreateAgentWizard({ isOpen, onClose, onNavigate, onOpenBuyNumber }) {
  const { loadWorkspaceData, phoneNumbers, agents, wallet, selectedAgentId } = useWorkspace();
  const [step, setStep] = useState(0);
  const [maxReached, setMaxReached] = useState(0);
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [voices, setVoices] = useState([]);

  useEffect(() => {
    if (!isOpen) return;
    setStep(0);
    setMaxReached(0);
    setDraft(EMPTY_DRAFT);
    setError(null);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    api.telephony
      .getVoiceOptions()
      .then((data) => {
        if (cancelled) return;
        setVoices(data?.voices || []);
      })
      .catch(() => {
        if (!cancelled) setVoices([]);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  const goTo = useCallback((index) => {
    setStep(index);
    setMaxReached((prev) => Math.max(prev, index));
    setError(null);
  }, []);

  const advance = useCallback(() => {
    goTo(Math.min(step + 1, AGENT_CREATION_STEPS.length - 1));
  }, [goTo, step]);

  /** Step 1 → 2: compile the brief and load the generated script. */
  const createAndCompile = useCallback(async () => {
    if (draft.brief.trim().length < BRIEF_MIN_CHARS) {
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

      // The compiler response carries the script; fall back to the stored brain
      // when a deployment does not return it inline.
      let script = result.script || '';
      let variables = result.variables || [];
      let agentName = result.employeeName || '';
      if (!script) {
        const brain = await api.agents.getBusinessBrain(agentId).catch(() => null);
        script = brain?.callingScript || '';
        variables = brain?.variables || [];
      }
      if (!agentName) {
        const created = await api.agents.get(agentId).catch(() => null);
        agentName = created?.name || '';
      }

      setDraft((prev) => ({
        ...prev,
        agentId,
        agentName,
        generatedScript: script,
        variables,
      }));
      await loadWorkspaceData();
      advance();
    } catch (e) {
      setError(e.message || 'Could not create the agent');
    } finally {
      setBusy(false);
    }
  }, [draft, advance, loadWorkspaceData]);

  /** Step 2: persist an edited script back to the published brain. */
  const saveScriptEdit = useCallback(async () => {
    if (!draft.agentId || !draft.scriptDirty) return true;
    setBusy(true);
    setError(null);
    try {
      await api.agents.saveCallingScript(draft.agentId, draft.generatedScript);
      setDraft((prev) => ({ ...prev, scriptDirty: false }));
      return true;
    } catch (e) {
      setError(e.message || 'Could not save the script');
      return false;
    } finally {
      setBusy(false);
    }
  }, [draft.agentId, draft.scriptDirty, draft.generatedScript]);

  const handleScriptNext = useCallback(async () => {
    const ok = await saveScriptEdit();
    if (ok) advance();
  }, [saveScriptEdit, advance]);

  /** Step 3: save voice into the brain and telephony settings to the profile API. */
  const saveConfiguration = useCallback(async () => {
    if (!draft.agentId) return false;
    setBusy(true);
    setError(null);
    try {
      if (draft.voiceDirty) {
        await api.agents.saveVoice(draft.agentId, {
          voiceId: draft.voiceId,
          speed: draft.speed,
          language: draft.language,
        });
      }
      const profile = draft.telephony || {};
      if (draft.telephonyDirty || draft.telephony) {
        await api.agents.saveTelephonyProfile(draft.agentId, {
          greetingPhrase: profile.greetingPhrase || '',
          businessHours: profile.businessHours || {},
          timezone: profile.timezone || 'Asia/Kolkata',
          afterHoursAction: profile.afterHoursAction || 'voicemail',
          transferNumber: profile.transferNumber || '',
          inboundEnabled: profile.inboundEnabled !== false,
          outboundEnabled: profile.outboundEnabled !== false,
        });
      }
      await loadWorkspaceData();
      advance();
      return true;
    } catch (e) {
      setError(e.message || 'Could not save the settings');
      return false;
    } finally {
      setBusy(false);
    }
  }, [draft, advance, loadWorkspaceData]);

  const handleFinish = useCallback(() => {
    const agentId = draft.agentId;
    onClose();
    if (agentId) {
      onNavigate('employees', { agentId, step: 'script' });
    }
  }, [draft.agentId, onClose, onNavigate]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && step === 0 && !busy) {
        e.preventDefault();
        createAndCompile();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, busy, createAndCompile, step]);

  const stepProps = useMemo(
    () => ({ draft, onChange: setDraft, busy, error }),
    [draft, busy, error]
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Create an AI employee"
      subtitle="Describe the job. We write the script, then you set up how callers reach it."
      maxWidth="max-w-3xl"
      panelClassName="shadow-craft-lg"
    >
      <div data-testid="create-employee-modal" className="space-y-5">
        <div className="flex items-center justify-between gap-3">
          <Stepper current={step} maxReached={maxReached} onJumpTo={goTo} />
          {step === 0 && (
            <p className="hidden sm:block text-[11px] text-[#8C879A]">
              <kbd className="font-mono text-[#524E5E] px-1 rounded bg-[#F0EEF6] border border-[#E4E2EB]">
                ⌘
              </kbd>
              <span className="mx-1">+</span>
              <kbd className="font-mono text-[#524E5E] px-1 rounded bg-[#F0EEF6] border border-[#E4E2EB]">
                Enter
              </kbd>
              to create
            </p>
          )}
        </div>

        {step === 0 && (
          <StepBrief
            {...stepProps}
            onNext={createAndCompile}
            onBack={null}
            busy={busy}
          />
        )}

        {step === 1 && (
          <StepScript
            {...stepProps}
            onNext={handleScriptNext}
            onBack={() => goTo(0)}
            onRegenerate={createAndCompile}
            busy={busy}
          />
        )}

        {step === 2 && (
          <StepConfigure
            {...stepProps}
            onNext={saveConfiguration}
            onBack={() => goTo(1)}
            onOpenBuyNumber={onOpenBuyNumber}
            busy={busy}
            voices={voices}
            phoneNumbers={phoneNumbers}
            agents={agents}
            walletBalanceInr={wallet?.balanceInr ?? 0}
            selectedAgentId={selectedAgentId}
          />
        )}

        {step === 3 && (
          <StepReady
            {...stepProps}
            onBack={() => goTo(2)}
            onTestCall={() => {
              const agentId = draft.agentId;
              onClose();
              onNavigate('employees', { agentId, step: 'test' });
            }}
            onOpenStudio={handleFinish}
            onOpenCalls={() => {
              const agentId = draft.agentId;
              onClose();
              onNavigate('calls', { agentId });
            }}
            onOpenBuyNumber={onOpenBuyNumber}
            onFinish={handleFinish}
            busy={busy}
          />
        )}

        {/* Hidden submit keeps the primary action reachable by keyboard/AT. */}
        <button type="button" className="hidden" aria-hidden="true" tabIndex={-1}>
          <TactileButton variant="brand" size="md" icon={Sparkles}>
            Build my employee
          </TactileButton>
        </button>
      </div>
    </Modal>
  );
}

export { DEFAULT_BUSINESS_HOURS };
