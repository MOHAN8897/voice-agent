import React, { useCallback, useMemo, useState, useEffect, useRef } from 'react';
import {
  FileCode2,
  Volume2,
  Save,
  Play,
  Square,
  Plus,
  Trash2,
  CheckCircle2,
  Radio,
  ArrowLeft,
  LayoutDashboard,
  History,
  Settings,
} from 'lucide-react';
import { AgentTestCallPanel } from './agent-workspace/AgentTestCallPanel';
import { SolidCard } from '../ui/SolidCard';
import { StatusBadge } from '../ui/StatusBadge';
import { TactileButton } from '../ui/TactileButton';
import { Modal } from '../ui/Modal';
import { useWorkspace } from '../context/WorkspaceContext';
import { voiceAgent } from '../../services/voiceAgent';
import { LANGUAGE_OPTIONS } from '../../lib/voicePresets';
import { PHONE_STACK_LABEL } from '../../lib/phoneLabels';
import {
  fetchPhoneVoiceOptions,
  parseStudioFieldsFromSections,
  parseVoiceConfigFromSections,
} from '../../lib/voiceStack';
import { formatPhoneVoiceLabel, groupVoicesByTier } from '../../lib/voiceDisplay';
import { loadAgentBrain } from '../../services/agentBrain';
import { api } from '../../services/api';
import { AgentOverview } from './agent-workspace/AgentOverview';
import { AgentCallsPanel } from './agent-workspace/AgentCallsPanel';
import { AgentSettingsPanel } from './agent-workspace/AgentSettingsPanel';
import { resolveEmployeeStep } from '../employeeFlowHash';

/**
 * Canonical text for the dirty check, and the payload "Discard" restores.
 *
 * These are the same thing on purpose. They used to be a hand-picked subset,
 * which meant Discard restored a form with `objectionRules`, `boundaries`,
 * `dynamicVariables` and `inboundRouting` missing — the editor then crashed on
 * the next `.map`, and a rejected edit silently erased the caller's rules.
 *
 * Snapshot and form are therefore built from one field list, so they cannot
 * drift apart again: adding an editor field to `formFromAgent` without adding it
 * here is the only way to reintroduce the bug, and it now fails visibly.
 */
const EDITABLE_FIELDS = [
  'name',
  'role',
  'greeting',
  'script',
  'language',
  'dynamicVariables',
  'objectionRules',
  'boundaries',
  'variableDefinitions',
  'voice',
  'inboundRouting',
];

/**
 * Reduce a form to just the editable fields, with every collection normalised to
 * an array. The normalisation is not cosmetic: a restored snapshot that lacks a
 * key would leave `undefined` in place of a list, and the first `.map` over it
 * would throw and take the whole workspace down.
 */
function editableSubset(form) {
  const out = {};
  for (const key of EDITABLE_FIELDS) {
    const value = form?.[key];
    if (Array.isArray(value)) {
      out[key] = value;
    } else if (value && typeof value === 'object') {
      out[key] = value;
    } else {
      out[key] = value ?? '';
    }
  }
  return out;
}

function snapForm(form) {
  if (!form) return JSON.stringify(editableSubset(EMPTY_FORM));
  return JSON.stringify(editableSubset(form));
}

/** Turn a stored snapshot back into a complete, renderable form. */
function formFromSnapshot(snapshot) {
  const parsed = JSON.parse(snapshot || '{}');
  return {
    ...editableSubset(parsed),
    // Never inherit a malformed list from an older or hand-edited snapshot.
    dynamicVariables: Array.isArray(parsed.dynamicVariables) ? parsed.dynamicVariables : [],
    objectionRules: Array.isArray(parsed.objectionRules) ? parsed.objectionRules : [],
    boundaries: Array.isArray(parsed.boundaries) ? parsed.boundaries : [],
    variableDefinitions: Array.isArray(parsed.variableDefinitions)
      ? parsed.variableDefinitions
      : [],
  };
}

/** The five workspace tabs. Test call is a header button, not a tab. */
const FLOW_TABS = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'script', label: 'Script', icon: FileCode2 },
  { id: 'calls', label: 'Calls', icon: History },
  { id: 'voice', label: 'Voice', icon: Volume2 },
  { id: 'settings', label: 'Settings', icon: Settings },
];

const EMPTY_FORM = {
  name: '',
  role: 'Sales',
  greeting: '',
  script: '',
  dynamicVariables: [],
  objectionRules: [],
  boundaries: [],
  variableDefinitions: [],
  voice: { speed: 1, pitch: 0, voiceName: '', provider: 'openai' },
  language: 'en-US',
  inboundRouting: {
    businessHours: '08:00 - 18:00 (PST)',
    afterHoursAction: 'voicemail',
    greetingPhrase: '',
  },
};

function formFromAgent(agent) {
  if (!agent) return { ...EMPTY_FORM };
  return {
    ...editableSubset({
      name: agent.name || '',
      role: agent.role || 'Sales',
      greeting: agent.greeting || '',
      script: agent.script || '',
      dynamicVariables: agent.dynamicVariables || [],
      objectionRules: agent.objectionRules || [],
      boundaries: agent.boundaries || [],
      variableDefinitions: agent.variableDefinitions || [],
      voice: { ...EMPTY_FORM.voice, ...(agent.voice || {}) },
      language: agent.language || 'en-US',
      inboundRouting: agent.inboundRouting || {
        businessHours: '08:00 - 18:00 (PST)',
        afterHoursAction: 'voicemail',
        greetingPhrase: agent.greeting || '',
      },
    }),
  };
}

export function AgentStudioModule({
  onNavigate,
  onOpenBuyNumber,
  flowStep,
  onFlowStepChange,
  onBackToFleet,
}) {
  const {
    agents,
    isLoading,
    selectedAgentId,
    setSelectedAgentId,
    selectedAgent,
    updateAgent,
  } = useWorkspace();

  const [activeTab, setActiveTab] = useState(() => resolveEmployeeStep(flowStep).step);
  const [callPanel, setCallPanel] = useState(() => resolveEmployeeStep(flowStep).callPanel || 'history');
  const [testCallOpen, setTestCallOpen] = useState(() => Boolean(resolveEmployeeStep(flowStep).openTestCall));
  // The Test call modal is a header action, so closing it must return focus to the
  // button that opened it rather than dropping the user back at the top of the page.
  const testCallButtonRef = useRef(null);
  const [phoneVoices, setPhoneVoices] = useState([]);
  const [stackLabel, setStackLabel] = useState(PHONE_STACK_LABEL);

  useEffect(() => {
    fetchPhoneVoiceOptions()
      .then((o) => {
        setPhoneVoices(o.voices || []);
        setStackLabel(o.stackLabel || PHONE_STACK_LABEL);
      })
      .catch(() => {});
  }, []);

  // A legacy ?step=telephony or ?step=test link resolves here on first mount and on
  // every later hash change, so old bookmarks still land somewhere useful.
  useEffect(() => {
    if (!flowStep) return;
    const next = resolveEmployeeStep(flowStep);
    setActiveTab(next.step);
    if (next.callPanel) setCallPanel(next.callPanel);
    if (next.openTestCall) setTestCallOpen(true);
  }, [flowStep]);

  const [isSaved, setIsSaved] = useState(false);
  const [isPlayingVoice, setIsPlayingVoice] = useState(false);
  const [voicePreviewError, setVoicePreviewError] = useState(null);
  // Which voice actually spoke, so the operator knows this is the real one.
  const [voiceSpoken, setVoiceSpoken] = useState({ voice: null, model: null });
  const [brainLoadError, setBrainLoadError] = useState(null);
  const [brainLoading, setBrainLoading] = useState(false);

  const [formData, setFormData] = useState(() => formFromAgent(selectedAgent));
  // The last-loaded (saved) state. Dirty = formData differs from this, which is
  // what the Save/Discard guard compares against.
  const [savedSnapshot, setSavedSnapshot] = useState(() => snapForm(formData));
  // A published agent must not be swapped out from under unsaved script edits.
  // Held as a plain value, not a resolver promise: a pending promise silently
  // drops the state update if the component unmounts or re-keys mid-flight, and
  // the user then gets no dialog at all and no explanation.
  const [pendingLeave, setPendingLeave] = useState(null);
  const dirty = snapForm(formData) !== savedSnapshot;

  const confirmLeave = useCallback(
    () => (dirty ? new Promise((resolve) => setPendingLeave(() => resolve)) : Promise.resolve(true)),
    [dirty]
  );

  const settleLeave = useCallback((ok) => {
    setPendingLeave((prev) => {
      if (typeof prev === 'function') prev(ok);
      return null;
    });
  }, []);

  const discardChanges = useCallback(() => {
    // Restore through the same normaliser the snapshot was built with, so a
    // restored form always has the collections the editor maps over.
    setFormData(formFromSnapshot(savedSnapshot));
    setSaveError(null);
    setIsSaved(false);
  }, [savedSnapshot]);

  const guardedAction = useCallback(
    (run) => async (...args) => {
      if (!(await confirmLeave())) return undefined;
      return run(...args);
    },
    [confirmLeave]
  );

  // Never let a refresh or a hard navigation silently discard an edited script.
  useEffect(() => {
    const onBeforeUnload = (event) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [dirty]);

  const selectAgent = useMemo(
    () => guardedAction((agentId, step) => {
      setSelectedAgentId(agentId);
      onFlowStepChange?.(step, agentId);
    }),
    [guardedAction, setSelectedAgentId, onFlowStepChange]
  );

  const selectTab = useMemo(
    () => guardedAction((id) => {
      setActiveTab(id);
      onFlowStepChange?.(id);
    }),
    [guardedAction, onFlowStepChange]
  );

  // Agent list rows do not include script — load draft brain once per selection (not on every list refresh).
  useEffect(() => {
    const agentId = selectedAgentId || selectedAgent?.id;
    if (!agentId) return;

    let cancelled = false;
    setBrainLoading(true);
    setBrainLoadError(null);

    const agent =
      selectedAgent?.id === agentId
        ? selectedAgent
        : agents.find((a) => a.id === agentId) || selectedAgent;
    const base = formFromAgent(agent);

    loadAgentBrain(agentId)
      .then((data) => {
        if (cancelled) return;
        const studio = parseStudioFieldsFromSections(data?.draft?.sections);
        const cfg = parseVoiceConfigFromSections(data?.draft?.sections);
        const voiceMeta = (phoneVoices.length ? phoneVoices : []).find(
          (v) => v.id === cfg.realtimeVoice
        );
        const loaded = {
          ...base,
          script: studio.script || '',
          greeting: studio.greeting || base.greeting,
          variableDefinitions: studio.variableDefinitions?.length
            ? studio.variableDefinitions
            : base.variableDefinitions,
          language: cfg.language || base.language,
          voice: {
            ...base.voice,
            realtimeVoice: cfg.realtimeVoice || base.voice?.realtimeVoice,
            voiceId: cfg.realtimeVoice || base.voice?.voiceId || 'marin',
            voiceName: voiceMeta?.label || base.voice?.voiceName || cfg.realtimeVoice,
            speed: cfg.speed ?? base.voice?.speed ?? 1,
          },
        };
        setFormData(loaded);
        // What the server just sent IS the saved baseline, so switching agents
        // never reports a phantom "unsaved changes".
        setSavedSnapshot(snapForm(loaded));
      })
      .catch((err) => {
        if (!cancelled) {
          setBrainLoadError(err?.message || 'Could not load calling script');
          setFormData(base);
          setSavedSnapshot(snapForm(base));
        }
      })
      .finally(() => {
        if (!cancelled) setBrainLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedAgentId, phoneVoices]);

  useEffect(() => {
    if (!selectedAgent) return;
    setFormData((prev) => ({
      ...prev,
      name: selectedAgent.name || prev.name,
      role: selectedAgent.role || prev.role,
    }));
  }, [selectedAgent?.id, selectedAgent?.name, selectedAgent?.role]);

  // Handle Save
  const [saveError, setSaveError] = useState(null);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!selectedAgent?.id) return;
    setSaveError(null);
    setSaving(true);
    try {
      await updateAgent(selectedAgent.id, formData);
      // Re-baseline: after a successful publish there is nothing left to guard.
      setSavedSnapshot(snapForm(formData));
      setIsSaved(true);
      setTimeout(() => setIsSaved(false), 2500);
    } catch (e) {
      setSaveError(e.message || 'Could not save agent');
    } finally {
      setSaving(false);
    }
    return true;
  };

  // Variable chip insertion into script cursor
  const handleInsertVariable = (varName) => {
    setFormData((prev) => ({
      ...prev,
      script: `${prev.script}\n{{${varName}}}`
    }));
  };

  const handleAddObjection = () => {
    setFormData((prev) => ({
      ...prev,
      objectionRules: [
        ...prev.objectionRules,
        { trigger: 'Customer concern here...', response: 'AI response script here...' }
      ]
    }));
  };

  const handleRemoveObjection = (index) => {
    setFormData((prev) => ({
      ...prev,
      objectionRules: prev.objectionRules.filter((_, i) => i !== index)
    }));
  };

  // Cleanup audio preview on unmount
  useEffect(() => {
    return () => {
      voiceAgent.stopTTS();
      setIsPlayingVoice(false);
    };
  }, []);

  const handlePlayVoicePreview = async () => {
    if (isPlayingVoice) {
      voiceAgent.stopTTS();
      setIsPlayingVoice(false);
      return;
    }

    const previewText =
      formData.greeting ||
      `Hi there! I am ${formData.name}. I am calibrated and ready to take your calls.`;
    setVoicePreviewError(null);
    setVoiceSpoken({ voice: null, model: null });
    setIsPlayingVoice(true);

    // Speak through the real live model the caller will reach. The previous
    // implementation used window.speechSynthesis — an unrelated OS voice — so the
    // preview could be approved while the shipped voice was something else.
    try {
      const { blob, voice, model } = await api.telephony.previewVoice({
        text: previewText,
        voiceId: formData.voice?.voiceId || formData.voice?.id || null,
      });
      setVoiceSpoken({ voice: voice || null, model: model || null });
      const played = await voiceAgent.playAudioBuffer(
        blob,
        () => setIsPlayingVoice(false),
        () => setIsPlayingVoice(true)
      );
      if (!played) {
        setIsPlayingVoice(false);
        setVoicePreviewError('The preview audio could not be played. Check your sound output.');
      }
    } catch (e) {
      setIsPlayingVoice(false);
      setVoicePreviewError(
        e?.message || 'Could not reach the voice service to preview this voice.'
      );
    }
  };

  if (!isLoading && agents.length === 0) {
    return (
      <SolidCard className="p-10 text-center space-y-4 max-w-lg mx-auto">
        <FileCode2 className="w-10 h-10 text-[#6344E7] mx-auto" />
        <h2 className="text-lg font-bold text-[#0F0E17]">No agents yet</h2>
        <p className="text-sm text-[#524E5E]">
          Create an AI employee first, then edit scripts, voice, and telephony routing here in Script Studio.
        </p>
        <TactileButton onClick={() => onNavigate?.('employees', { openCreate: true })}>
          Create your first AI employee
        </TactileButton>
      </SolidCard>
    );
  }

  if (!selectedAgent) {
    return (
      <SolidCard className="p-10 text-center space-y-3 max-w-lg mx-auto">
        <p className="text-sm text-[#524E5E]">{isLoading ? 'Loading agents…' : 'Select an agent to edit.'}</p>
      </SolidCard>
    );
  }

  return (
    <div className="space-y-6">
      {saveError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900">{saveError}</div>
      )}
      {/* Unsaved-changes guard. Every leave path (tab, agent switch, back, unload)
          funnels through confirmLeave, so nothing silently discards a script. */}
      {dirty && (
        <div
          data-testid="agent-studio-unsaved"
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900"
        >
          <span className="font-semibold">Unsaved changes</span>
          <span className="flex items-center gap-2">
            <button
              type="button"
              onClick={discardChanges}
              data-testid="agent-studio-discard"
              className="rounded-lg border border-amber-300 px-2.5 py-1 font-semibold"
            >
              Discard
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              data-testid="agent-studio-save-inline"
              className="rounded-lg bg-[#0F0E17] px-2.5 py-1 font-semibold text-white disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save & publish'}
            </button>
          </span>
        </div>
      )}

      <Modal
        isOpen={Boolean(pendingLeave)}
        onClose={() => settleLeave(false)}
        title="Unsaved script changes"
        subtitle="Your edits have not been published yet."
        maxWidth="max-w-md"
      >
        <div className="space-y-4" data-testid="agent-studio-leave-dialog">
          <p className="text-xs text-[#524E5E]">
            Leaving now discards the script edits you have not saved.
          </p>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <button
              type="button"
              onClick={discardChanges}
              data-testid="leave-discard"
              className="mr-auto rounded-xl px-3 py-2 text-xs font-semibold text-[#B42318] hover:bg-[#FEF2F2]"
            >
              Discard changes
            </button>
            <button
              type="button"
              onClick={() => settleLeave(false)}
              data-testid="leave-cancel"
              className="rounded-xl px-3 py-2 text-xs font-semibold text-[#524E5E] hover:bg-[#FAF9FD]"
            >
              Keep editing
            </button>
            <button
              type="button"
              disabled={saving}
              data-testid="leave-save"
              onClick={async () => {
                const ok = await handleSave();
                if (ok) settleLeave(true);
              }}
              className="rounded-xl bg-[#6344E7] px-3 py-2 text-xs font-bold text-white disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save & publish'}
            </button>
          </div>
        </div>
      </Modal>
      {/* Workbench Header: Agent Switcher, Status & Save */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl bg-white border border-[#E4E2EB] shadow-craft-xs">
        {/* Left: Agent Avatar & Selector */}
        <div className="flex items-center gap-3.5">
          {onBackToFleet && (
            <button
              type="button"
              onClick={() => void (async () => {
                  if (await confirmLeave()) onBackToFleet?.();
                })()}
              data-testid="agent-studio-back"
              className="p-2 rounded-xl border border-[#E4E2EB] text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD]"
              title="Back to fleet"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
          )}
          <div className="w-12 h-12 rounded-2xl bg-[#F0EEF6] border border-[#E4E2EB] flex items-center justify-center text-[#0F0E17] font-bold text-lg shadow-2xs">
            {selectedAgent.name.charAt(0)}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <select
                value={selectedAgentId}
                onChange={(e) => void selectAgent(e.target.value)}
                data-testid="agent-studio-switcher"
                className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2.5 py-1 text-sm font-bold text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
              >
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} ({a.role})
                  </option>
                ))}
              </select>
              <StatusBadge status={selectedAgent.status} size="xs" />
            </div>
            <div className="text-xs text-[#524E5E] mt-1">
              Assigned: <span className="font-mono font-semibold text-[#0F0E17]">{selectedAgent.assignedNumber || 'None (Pool)'}</span>
            </div>
          </div>
        </div>

        {/* Right Action Buttons */}
        <div className="flex items-center gap-2.5">
          <TactileButton
            variant="secondary"
            size="sm"
            icon={Radio}
            onClick={(e) => {
              testCallButtonRef.current = e.currentTarget;
              setTestCallOpen(true);
            }}
            data-testid="agent-test-call"
          >
            Test call
          </TactileButton>

          <TactileButton
            variant="primary"
            size="sm"
            icon={isSaved ? CheckCircle2 : Save}
            onClick={handleSave}
            disabled={saving}
            data-testid="agent-save"
          >
            {isSaved ? 'Saved!' : saving ? 'Saving…' : 'Save & Publish'}
          </TactileButton>
        </div>
      </div>

      {/* Tabs Navigation Bar */}
      <div
        className="flex items-center gap-1 p-1.5 rounded-2xl bg-white border border-[#E4E2EB] overflow-x-auto shadow-craft-xs"
        role="tablist"
        aria-label="Agent workspace"
      >
        {FLOW_TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`agent-tab-${tab.id}`}
              aria-selected={isActive}
              aria-controls={`agent-panel-${tab.id}`}
              data-testid={`agent-tab-${tab.id}`}
              onClick={() => selectTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
                isActive
                  ? 'bg-[#0F0E17] text-white shadow-xs font-bold'
                  : 'text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD]'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* TAB: OVERVIEW */}
      {activeTab === 'overview' && (
        <div
          role="tabpanel"
          id="agent-panel-overview"
          aria-labelledby="agent-tab-overview"
          className="animate-in fade-in duration-150"
        >
          <AgentOverview agent={selectedAgent} onOpenTab={selectTab} />
        </div>
      )}

      {/* TAB: SCRIPT & CONVERSATION FLOW */}
      {activeTab === 'script' && (
        <div
          role="tabpanel"
          id="agent-panel-script"
          aria-labelledby="agent-tab-script"
          className="space-y-6 animate-in fade-in duration-150"
        >
          <SolidCard>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
              <div>
                <h3 className="text-xs font-bold text-[#0F0E17]">Calling script</h3>
                <p className="text-[11px] text-[#524E5E]">
                  What your agent says on a call. Published to the cached brain on save.
                </p>
                {brainLoading && (
                  <p className="text-[11px] text-[#6344E7] mt-1">Loading script from your agent brain…</p>
                )}
                {brainLoadError && (
                  <p className="text-[11px] text-red-600 mt-1">{brainLoadError}</p>
                )}
              </div>

              {/* Variable-injection chips are hidden here on purpose. `{{token}}`
                  is a compiler contract, not something a caller should say, and
                  putting insert buttons beside the script invited operators to
                  paste them into text the agent would speak aloud. Definitions
                  live in Settings; the script stays prose. */}
            </div>

            <textarea
              rows={10}
              value={formData.script}
              onChange={(e) => setFormData({ ...formData, script: e.target.value })}
              className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-4 text-xs text-[#0F0E17] font-mono leading-relaxed focus:outline-none focus:border-[#6344E7] transition-colors"
            />

            {/* Only show what is real. Token counts and latency are internal
                engineering metrics; the server does not report them here, so
                guessing would be worse than saying nothing. */}
            <div className="flex items-center justify-between text-[11px] text-[#8C879A] mt-2">
              <span>
                {formData.script.trim()
                  ? `${formData.script.trim().split(/\s+/).length} words`
                  : 'Script is empty'}
              </span>
              <button
                type="button"
                onClick={() => void selectTab('test')}
                className="font-semibold text-[#5034CE] hover:underline"
              >
                Test this script
              </button>
            </div>
          </SolidCard>

          {/* Objection Handling Rules */}
          <SolidCard>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-xs font-bold text-[#0F0E17]">Objection Handling Rules</h3>
                <p className="text-[11px] text-[#524E5E]">Deterministic responses triggered when customer raises specific hesitations.</p>
              </div>
              <button
                type="button"
                onClick={handleAddObjection}
                className="text-xs font-semibold text-[#6344E7] hover:text-[#5034CE] flex items-center gap-1"
              >
                <Plus className="w-3 h-3" />
                <span>Add Objection Rule</span>
              </button>
            </div>

            <div className="space-y-3">
              {/* Defensive: a malformed form must degrade to an empty list, not
                  crash the whole agent workspace with an unhandled TypeError. */}
              {(formData.objectionRules || []).map((rule, idx) => (
                <div
                  key={idx}
                  className="p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] grid grid-cols-1 sm:grid-cols-2 gap-3 relative group"
                >
                  <div>
                    <span className="text-[10px] text-[#8C879A] uppercase font-bold block mb-1">
                      If Caller Mentions / Asks:
                    </span>
                    <input
                      type="text"
                      value={rule.trigger}
                      onChange={(e) => {
                        const next = [...formData.objectionRules];
                        next[idx].trigger = e.target.value;
                        setFormData({ ...formData, objectionRules: next });
                      }}
                      className="w-full bg-white border border-[#E4E2EB] rounded-lg px-2.5 py-1 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                    />
                  </div>

                  <div>
                    <span className="text-[10px] text-[#8C879A] uppercase font-bold block mb-1">
                      Agent Response Script:
                    </span>
                    <input
                      type="text"
                      value={rule.response}
                      onChange={(e) => {
                        const next = [...formData.objectionRules];
                        next[idx].response = e.target.value;
                        setFormData({ ...formData, objectionRules: next });
                      }}
                      className="w-full bg-white border border-[#E4E2EB] rounded-lg px-2.5 py-1 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                    />
                  </div>

                  <button
                    type="button"
                    onClick={() => handleRemoveObjection(idx)}
                    className="absolute top-2 right-2 p-1 text-[#DC2626] opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Remove rule"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </SolidCard>
        </div>
      )}

      {/* TAB: VOICE & ACOUSTIC TUNING */}
      {activeTab === 'voice' && (
        <div
          role="tabpanel"
          id="agent-panel-voice"
          aria-labelledby="agent-tab-voice"
          className="space-y-6 animate-in fade-in duration-150"
        >
          <SolidCard>
            <p className="text-[11px] text-[#524E5E] mb-3">
              {stackLabel} — these voices apply to incoming calls, outgoing calls, and browser practice
              calls after you save & publish.
            </p>
            <h3 className="text-xs font-bold text-[#0F0E17] mb-4">Speaking voice</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-[#0F0E17] mb-1">Voice</label>
                <select
                  value={formData.voice?.realtimeVoice || formData.voice?.voiceId || 'marin'}
                  onChange={(e) => {
                    const id = e.target.value;
                    const meta = phoneVoices.find((v) => v.id === id);
                    setFormData({
                      ...formData,
                      voice: {
                        ...formData.voice,
                        provider: 'phone_ai',
                        realtimeVoice: id,
                        voiceId: id,
                        voiceName: formatPhoneVoiceLabel(meta),
                      },
                    });
                  }}
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-2.5 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                >
                  {(() => {
                    // Grouped by how the voice sounds, not by which vendor serves it.
                    // Naming the suppliers invited tenants to compare our rate against
                    // their own API bill; the choice they are making is tone and fit.
                    const fallback = [{ id: 'marin', label: 'Marin', gender: 'female', tone: 'Warm & clear' }];
                    const groups = groupVoicesByTier(
                      phoneVoices.length ? phoneVoices : fallback
                    );
                    return groups.map((group) => (
                      <optgroup key={group.label} label={group.label}>
                        {group.voices.map((p) => (
                          <option key={p.id} value={p.id}>{formatPhoneVoiceLabel(p)}</option>
                        ))}
                      </optgroup>
                    ));
                  })()}
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-[#0F0E17] mb-1">Language</label>
                <select
                  value={formData.language}
                  onChange={(e) => setFormData({ ...formData, language: e.target.value })}
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-2.5 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                >
                  {LANGUAGE_OPTIONS.map((l) => (
                    <option key={l.code} value={l.code}>{l.label}</option>
                  ))}
                </select>
              </div>
            </div>
          </SolidCard>

          <SolidCard>
            <h3 className="text-xs font-bold text-[#0F0E17] mb-4">Acoustic Calibration Sliders</h3>
            <div className="space-y-5">
              <div>
                <div className="flex justify-between text-xs mb-1.5">
                  <span className="font-semibold text-[#0F0E17]">Speaking Speed</span>
                  <span className="font-mono text-[#6344E7] font-bold">{formData.voice.speed}x</span>
                </div>
                <input
                  type="range"
                  min="0.8"
                  max="1.3"
                  step="0.02"
                  value={formData.voice.speed}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      voice: { ...formData.voice, speed: parseFloat(e.target.value) }
                    })
                  }
                  className="w-full accent-[#6344E7]"
                />
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1.5">
                  <span className="font-semibold text-[#0F0E17]">Pitch Modulation</span>
                  <span className="font-mono text-[#6344E7] font-bold">{formData.voice.pitch > 0 ? `+${formData.voice.pitch}` : formData.voice.pitch}</span>
                </div>
                <input
                  type="range"
                  min="-0.15"
                  max="0.15"
                  step="0.01"
                  value={formData.voice.pitch}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      voice: { ...formData.voice, pitch: parseFloat(e.target.value) }
                    })
                  }
                  className="w-full accent-[#6344E7]"
                />
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1.5">
                  <span className="font-semibold text-[#0F0E17]">Stability & Consistency</span>
                  <span className="font-mono text-[#6344E7] font-bold">{formData.voice?.stability || 0.75}</span>
                </div>
                <input
                  type="range"
                  min="0.3"
                  max="1.0"
                  step="0.05"
                  value={formData.voice?.stability || 0.75}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      voice: { ...formData.voice, stability: parseFloat(e.target.value) }
                    })
                  }
                  className="w-full accent-[#6344E7]"
                />
              </div>
            </div>
          </SolidCard>

          {/* Interactive Voice Test & Preview Card */}
          <SolidCard className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold text-[#0F0E17] flex items-center gap-2">
                  <Radio className="w-3.5 h-3.5 text-[#6344E7]" />
                  <span>Acoustic Voice Preview & Live Test</span>
                </h3>
                <p className="text-[11px] text-[#524E5E]">
                  Hear the greeting in the exact live voice a caller will reach — same model, same voice.
                </p>
              </div>

              <span className={`text-[10px] font-mono px-2 py-0.5 rounded-md border font-semibold ${
                isPlayingVoice
                  ? 'bg-[#22C55E]/15 text-[#15803D] border-[#22C55E]/30 animate-pulse'
                  : 'bg-[#F0EEF6] text-[#524E5E] border-[#E4E2EB]'
              }`}>
                {isPlayingVoice ? '● Audio Playing' : 'Ready'}
              </span>
              {voiceSpoken.voice && (
                <span
                  data-testid="voice-preview-spoke"
                  className="text-[10px] font-mono px-2 py-0.5 rounded-md border bg-[#F0EEF6] text-[#524E5E] border-[#E4E2EB]"
                >
                  spoke {voiceSpoken.voice} · {voiceSpoken.model}
                </span>
              )}
            </div>

            <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-3">
              <div className="text-xs font-medium text-[#0F0E17] leading-relaxed italic">
                "{formData.greeting || `Hi there! I am ${formData.name}. I am calibrated and ready to take your calls.`}"
              </div>

              {/* Sound visualizer animation when playing */}
              {isPlayingVoice && (
                <div className="flex items-center gap-1 h-5 px-3 py-1 rounded-lg bg-white border border-[#E4E2EB]">
                  {[12, 22, 16, 26, 14, 20, 10, 24, 18, 14, 22, 16].map((h, i) => (
                    <span
                      key={i}
                      className="w-1 bg-[#6344E7] rounded-full animate-pulse"
                      style={{ height: `${h}px`, animationDelay: `${i * 70}ms` }}
                    />
                  ))}
                  <span className="text-[10px] font-mono text-[#524E5E] ml-auto">Playing live voice…</span>
                </div>
              )}

              {voicePreviewError && (
                <p
                  role="alert"
                  data-testid="voice-preview-error"
                  className="text-[11px] text-[#B91C1C]"
                >
                  {voicePreviewError}
                </p>
              )}
            </div>

            <div className="flex items-center gap-3 pt-1">
              <TactileButton
                variant={isPlayingVoice ? 'danger' : 'primary'}
                size="sm"
                icon={isPlayingVoice ? Square : Play}
                onClick={handlePlayVoicePreview}
              >
                {isPlayingVoice ? 'Stop Audio' : 'Preview Voice'}
              </TactileButton>

              <TactileButton
                variant="secondary"
                size="sm"
                icon={Radio}
                onClick={() => setTestCallOpen(true)}
              >
                Test call
              </TactileButton>
            </div>
          </SolidCard>
        </div>
      )}

      {/* TAB: CALLS (history | leads | call settings) */}
      {activeTab === 'calls' && (
        <div
          role="tabpanel"
          id="agent-panel-calls"
          aria-labelledby="agent-tab-calls"
          className="space-y-4 animate-in fade-in duration-150"
        >
          <div className="rounded-xl border border-[#E4E2EB] bg-[#F0EEF6]/50 px-3 py-2.5 text-xs text-[#524E5E]">
            Phone calls use your published script and wallet credits. Incoming and outgoing calls use the
            same {stackLabel} engine as the browser practice call.
          </div>
          <AgentCallsPanel
            agentId={selectedAgent.id}
            agentName={selectedAgent.name}
            initialPanel={callPanel}
          />
        </div>
      )}

      {/* TAB: SETTINGS */}
      {activeTab === 'settings' && (
        <div
          role="tabpanel"
          id="agent-panel-settings"
          aria-labelledby="agent-tab-settings"
          className="animate-in fade-in duration-150"
        >
          <AgentSettingsPanel agent={selectedAgent} onOpenBuyNumber={onOpenBuyNumber} />
        </div>
      )}

      {/* Test call is a header action, not a tab. Focus returns to the button on close. */}
      {testCallOpen && (
        <Modal
          isOpen={testCallOpen}
          onClose={() => {
            setTestCallOpen(false);
            requestAnimationFrame(() => testCallButtonRef.current?.focus());
          }}
          title={`Test call — ${selectedAgent.name}`}
          subtitle="Browser mic or live-number dial (wallet-billed). Empty wallet prompts a Razorpay top-up."
          maxWidth="max-w-lg"
        >
          <div data-testid="agent-test-call-panel">
            <AgentTestCallPanel agent={selectedAgent} />
          </div>
        </Modal>
      )}
    </div>
  );
}
