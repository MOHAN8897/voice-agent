import React, { useState, useEffect, useRef } from 'react';
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
import { formatPhoneVoiceLabel, groupPhoneVoices } from '../../lib/voiceDisplay';
import { loadAgentBrain } from '../../services/agentBrain';
import { AgentOverview } from './agent-workspace/AgentOverview';
import { AgentCallsPanel } from './agent-workspace/AgentCallsPanel';
import { AgentSettingsPanel } from './agent-workspace/AgentSettingsPanel';
import { resolveEmployeeStep } from '../employeeFlowHash';

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

  const selectTab = (id) => {
    setActiveTab(id);
    onFlowStepChange?.(id);
  };
  const [isSaved, setIsSaved] = useState(false);
  const [isPlayingVoice, setIsPlayingVoice] = useState(false);
  const [brainLoadError, setBrainLoadError] = useState(null);
  const [brainLoading, setBrainLoading] = useState(false);

  const [formData, setFormData] = useState(() => formFromAgent(selectedAgent));

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
        setFormData({
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
        });
      })
      .catch((err) => {
        if (!cancelled) {
          setBrainLoadError(err?.message || 'Could not load calling script');
          setFormData(base);
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
      setIsSaved(true);
      setTimeout(() => setIsSaved(false), 2500);
    } catch (e) {
      setSaveError(e.message || 'Could not save agent');
    } finally {
      setSaving(false);
    }
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

  const handlePlayVoicePreview = () => {
    if (isPlayingVoice) {
      voiceAgent.stopTTS();
      setIsPlayingVoice(false);
      return;
    }

    const previewText = formData.greeting || `Hi there! I am ${formData.name}. I am calibrated and ready to take your calls.`;
    setIsPlayingVoice(true);

    voiceAgent.playTTS(
      previewText,
      () => {
        setIsPlayingVoice(false);
      },
      () => {
        setIsPlayingVoice(true);
      },
      {
        speed: formData.voice?.speed || 1.0,
        pitch: formData.voice?.pitch || 0.0,
        voiceName: formData.voice?.voiceName || formData.name,
        provider: formData.voice?.provider
      }
    );
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
      {/* Workbench Header: Agent Switcher, Status & Save */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl bg-white border border-[#E4E2EB] shadow-craft-xs">
        {/* Left: Agent Avatar & Selector */}
        <div className="flex items-center gap-3.5">
          {onBackToFleet && (
            <button
              type="button"
              onClick={onBackToFleet}
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
                onChange={(e) => setSelectedAgentId(e.target.value)}
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
                  Same single section as dev Test Studio — identity, offer, opening, and role. Published to the cached brain on save.
                </p>
                {brainLoading && (
                  <p className="text-[11px] text-[#6344E7] mt-1">Loading script from your agent brain…</p>
                )}
                {brainLoadError && (
                  <p className="text-[11px] text-red-600 mt-1">{brainLoadError}</p>
                )}
              </div>

              {/* Dynamic Variables Chips */}
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-[10px] text-[#8C879A] uppercase font-bold tracking-wider mr-1">
                  Inject:
                </span>
                {(formData.variableDefinitions?.length
                  ? formData.variableDefinitions.map((v) => v.key)
                  : ['caller_name', 'callback_phone', 'business_name']
                ).map((v) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => handleInsertVariable(v)}
                    className="px-2.5 py-1 rounded-lg bg-[#F0EEF6] border border-[#E4E2EB] hover:border-[#6344E7] text-[10px] font-mono text-[#6344E7] hover:text-[#5034CE] transition-all font-semibold"
                    title={
                      formData.variableDefinitions?.find((d) => d.key === v)?.description || ''
                    }
                  >
                    + {`{{${v}}}`}
                  </button>
                ))}
              </div>
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
                onClick={() => setActiveTab('test')}
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
              {formData.objectionRules.map((rule, idx) => (
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
                    const { openai, gemini } = groupPhoneVoices(phoneVoices);
                    const fallback = [{ id: 'marin', label: 'Marin', gender: 'female', tone: 'Warm & clear' }];
                    const o = openai.length ? openai : fallback;
                    return (
                      <>
                        <optgroup label="OpenAI (phone default)">
                          {o.map((p) => (
                            <option key={p.id} value={p.id}>{formatPhoneVoiceLabel(p)}</option>
                          ))}
                        </optgroup>
                        {gemini.length > 0 && (
                          <optgroup label="Gemini Live">
                            {gemini.map((p) => (
                              <option key={p.id} value={p.id}>{formatPhoneVoiceLabel(p)}</option>
                            ))}
                          </optgroup>
                        )}
                      </>
                    );
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
                <p className="text-[11px] text-[#524E5E]">Hear this voice speak the opening greeting using the calibrated speed and pitch.</p>
              </div>

              <span className={`text-[10px] font-mono px-2 py-0.5 rounded-md border font-semibold ${
                isPlayingVoice
                  ? 'bg-[#22C55E]/15 text-[#15803D] border-[#22C55E]/30 animate-pulse'
                  : 'bg-[#F0EEF6] text-[#524E5E] border-[#E4E2EB]'
              }`}>
                {isPlayingVoice ? '● Audio Playing' : 'Ready'}
              </span>
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
                  <span className="text-[10px] font-mono text-[#524E5E] ml-auto">Synthesizing Speech...</span>
                </div>
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
