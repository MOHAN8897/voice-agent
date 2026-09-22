import React, { useState, useEffect } from 'react';
import {
  X,
  Sliders,
  Phone,
  Volume2,
  FileCode2,
  BookOpen,
  Blocks,
  Shield,
  Save,
  Play,
  Square,
  Plus,
  Trash2,
  CheckCircle2,
  Radio,
  Clock,
  Zap,
  Users,
  AlertCircle,
  ExternalLink,
  PhoneForwarded,
  Layers,
  Sparkles
} from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
import { StatusBadge } from '../ui/StatusBadge';
import { useWorkspace } from '../context/WorkspaceContext';
import { voiceAgent } from '../../services/voiceAgent';

export function IndividualEmployeeConsole({
  agentId,
  isOpen,
  onClose,
  onNavigate,
  onOpenBuyNumber
}) {
  const {
    agents,
    updateAgent,
    phoneNumbers,
    setBuyNumberPreselectedAgent
  } = useWorkspace();

  const agent = agents.find((a) => a.id === agentId) || agents[0];

  // Tab navigation state
  const [activeTab, setActiveTab] = useState('general'); // general | telephony | voice | script | knowledge | integrations
  const [isSaved, setIsSaved] = useState(false);
  const [isPlayingVoice, setIsPlayingVoice] = useState(false);

  // Local form state for this specific employee
  const [formData, setFormData] = useState({
    name: '',
    role: '',
    department: 'Customer Care',
    description: '',
    status: 'active',
    language: 'English (US & UK)',
    // Telephony settings
    assignedNumber: null,
    numberId: null,
    transferNumber: '+1 (415) 555-0100',
    concurrencyLimit: 10,
    maxDurationMinutes: 15,
    silenceTimeoutSeconds: 8,
    voicemailDetection: 'leave_message',
    recordingConsent: true,
    backgroundSound: 'clean',
    // Voice settings
    voice: {
      provider: 'Cartesia',
      voiceId: 'sonic-british-warm',
      voiceName: 'Sarah — British Warm',
      speed: 1.0,
      pitch: 0.0,
      stability: 0.75
    },
    bargeInSensitivity: 'normal',
    // Script & Flow
    greeting: '',
    script: '',
    dynamicVariables: [],
    objectionRules: [],
    boundaries: [],
    // Knowledge
    knowledgeSources: [],
    // Integrations
    crmSyncEnabled: true,
    calendarBookingEnabled: true,
    webhookUrl: 'https://api.summitdental.com/v1/voice-events'
  });

  // Sync state whenever selected agent changes
  useEffect(() => {
    if (agent) {
      setFormData({
        name: agent.name || '',
        role: agent.role || '',
        department: agent.department || 'Customer Care',
        description: agent.description || '',
        status: agent.status || 'active',
        language: agent.language || 'English (US & UK)',
        assignedNumber: agent.assignedNumber || null,
        numberId: agent.numberId || null,
        transferNumber: agent.transferNumber || '+1 (415) 555-0100',
        concurrencyLimit: agent.concurrencyLimit || 10,
        maxDurationMinutes: agent.maxDurationMinutes || 15,
        silenceTimeoutSeconds: agent.silenceTimeoutSeconds || 8,
        voicemailDetection: agent.voicemailDetection || 'leave_message',
        recordingConsent: agent.recordingConsent ?? true,
        backgroundSound: agent.backgroundSound || 'clean',
        voice: {
          provider: agent.voice?.provider || 'Cartesia',
          voiceId: agent.voice?.voiceId || 'sonic-british-warm',
          voiceName: agent.voice?.voiceName || 'Sarah — British Warm',
          speed: agent.voice?.speed ?? 1.0,
          pitch: agent.voice?.pitch ?? 0.0,
          stability: agent.voice?.stability ?? 0.75
        },
        bargeInSensitivity: agent.bargeInSensitivity || 'normal',
        greeting: agent.greeting || '',
        script: agent.script || '',
        dynamicVariables: agent.dynamicVariables || ['caller_name'],
        objectionRules: agent.objectionRules || [],
        boundaries: agent.boundaries || [],
        knowledgeSources: agent.knowledgeSources || ['Clinic Pricing Sheet.pdf'],
        crmSyncEnabled: agent.crmSyncEnabled ?? true,
        calendarBookingEnabled: agent.calendarBookingEnabled ?? true,
        webhookUrl: agent.webhookUrl || `https://api.summitdental.com/v1/agents/${agent.id}/events`
      });
    }
  }, [agent]);

  // Clean up audio on unmount or close
  useEffect(() => {
    return () => {
      voiceAgent.stopTTS();
      setIsPlayingVoice(false);
    };
  }, []);

  if (!isOpen || !agent) return null;

  const handleSave = () => {
    updateAgent(agent.id, formData);
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2500);
  };

  const handlePlayVoicePreview = () => {
    if (isPlayingVoice) {
      voiceAgent.stopTTS();
      setIsPlayingVoice(false);
      return;
    }

    const previewText = formData.greeting || `Hello, this is ${formData.name}. I am configured and ready to take live calls.`;
    setIsPlayingVoice(true);

    voiceAgent.playTTS(
      previewText,
      () => setIsPlayingVoice(false),
      () => setIsPlayingVoice(true),
      {
        speed: formData.voice?.speed || 1.0,
        pitch: formData.voice?.pitch || 0.0,
        voiceName: formData.voice?.voiceName || formData.name,
        provider: formData.voice?.provider
      }
    );
  };

  const handleAddObjection = () => {
    setFormData((prev) => ({
      ...prev,
      objectionRules: [
        ...prev.objectionRules,
        { trigger: 'Caller asks about...', response: 'AI response script here...' }
      ]
    }));
  };

  const handleRemoveObjection = (idx) => {
    setFormData((prev) => ({
      ...prev,
      objectionRules: prev.objectionRules.filter((_, i) => i !== idx)
    }));
  };

  const handleAddBoundary = () => {
    const boundary = prompt('Enter compliance guardrail / prohibited topic:');
    if (boundary && boundary.trim()) {
      setFormData((prev) => ({
        ...prev,
        boundaries: [...prev.boundaries, boundary.trim()]
      }));
    }
  };

  const handleRemoveBoundary = (idx) => {
    setFormData((prev) => ({
      ...prev,
      boundaries: prev.boundaries.filter((_, i) => i !== idx)
    }));
  };

  const handleAddKnowledge = () => {
    const docName = prompt('Enter knowledge document name (e.g. FAQ 2026.pdf):');
    if (docName && docName.trim()) {
      setFormData((prev) => ({
        ...prev,
        knowledgeSources: [...prev.knowledgeSources, docName.trim()]
      }));
    }
  };

  const handleRemoveKnowledge = (idx) => {
    setFormData((prev) => ({
      ...prev,
      knowledgeSources: prev.knowledgeSources.filter((_, i) => i !== idx)
    }));
  };

  const tabs = [
    { id: 'general', label: 'Identity & General', icon: Sliders },
    { id: 'telephony', label: 'Telephony & Routing', icon: Phone },
    { id: 'voice', label: 'Voice & Acoustics', icon: Volume2 },
    { id: 'script', label: 'Script & Guardrails', icon: FileCode2 },
    { id: 'knowledge', label: 'Knowledge Base', icon: BookOpen },
    { id: 'integrations', label: 'Integrations & Webhooks', icon: Blocks }
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-[#0F0E17]/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-5xl h-[90vh] bg-[#FAF9FD] rounded-2xl shadow-2xl border border-[#E4E2EB] flex flex-col overflow-hidden">
        
        {/* Header Ribbon: Employee Identity, Stats & Close */}
        <div className="p-4 sm:p-5 bg-white border-b border-[#E4E2EB] flex flex-col sm:flex-row sm:items-center justify-between gap-4 shrink-0 shadow-2xs">
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-2xl bg-[#0F0E17] text-white flex items-center justify-center font-bold text-xl shadow-xs shrink-0">
              {agent.name.charAt(0)}
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-base sm:text-lg font-bold text-[#0F0E17] tracking-tight">
                  {agent.name}
                </h2>
                <span className="text-xs text-[#524E5E] font-medium">• {agent.role}</span>
                <StatusBadge status={formData.status} size="xs" />
                <span className="text-[10px] font-mono font-medium px-2 py-0.5 rounded bg-[#F0EEF6] text-[#524E5E] border border-[#E4E2EB]">
                  ID: {agent.id}
                </span>
              </div>
              <p className="text-xs text-[#524E5E] mt-0.5">
                Independent configuration console for this individual AI voice employee.
              </p>
            </div>
          </div>

          {/* Header Quick Actions */}
          <div className="flex items-center gap-2 self-end sm:self-center">
            <TactileButton
              size="xs"
              variant="secondary"
              icon={Play}
              onClick={() => {
                onClose();
                onNavigate('talk-to-ai');
              }}
            >
              Test in WebRTC Lab
            </TactileButton>

            <button
              type="button"
              onClick={onClose}
              aria-label="Close configuration console"
              className="p-1.5 rounded-xl text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD] border border-transparent hover:border-[#E4E2EB] transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Individual Employee Telemetry Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 px-5 py-2.5 bg-white/70 border-b border-[#E4E2EB] text-xs font-mono shrink-0">
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-[#524E5E]">Calls Handled:</span>
            <span className="font-bold text-[#0F0E17]">{agent.stats?.totalCalls?.toLocaleString() || 0}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-[#524E5E]">Task Success:</span>
            <span className="font-bold text-[#15803D]">{agent.stats?.successRate || 95}%</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-[#524E5E]">Total Talk Time:</span>
            <span className="font-bold text-[#0F0E17]">{agent.stats?.totalMinutes?.toLocaleString() || 0} min</span>
          </div>
          <div className="flex items-center gap-2 truncate">
            <span className="text-[11px] text-[#524E5E]">DID Assigned:</span>
            <span className="font-bold text-[#6344E7] truncate">{formData.assignedNumber || 'None (Pool)'}</span>
          </div>
        </div>

        {/* Tab Navigation Ribbon */}
        <div className="px-5 pt-3 bg-white border-b border-[#E4E2EB] flex items-center gap-1.5 overflow-x-auto shrink-0">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-3.5 py-2.5 rounded-t-xl text-xs font-semibold whitespace-nowrap transition-all border-b-2 ${
                  isActive
                    ? 'border-[#0F0E17] text-[#0F0E17] bg-[#FAF9FD] font-bold shadow-2xs'
                    : 'border-transparent text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD]'
                }`}
              >
                <Icon className="w-3.5 h-3.5 shrink-0" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Scrollable Configuration Canvas */}
        <div className="flex-1 overflow-y-auto p-5 sm:p-6 space-y-6">
          
          {/* TAB 1: GENERAL & IDENTITY */}
          {activeTab === 'general' && (
            <div className="space-y-5 animate-in fade-in duration-150">
              <SolidCard className="space-y-4">
                <h3 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
                  Employee Persona & Identity
                </h3>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-[#0F0E17] mb-1">
                      Agent Name
                    </label>
                    <input
                      type="text"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#0F0E17] mb-1">
                      Role / Job Title
                    </label>
                    <input
                      type="text"
                      value={formData.role}
                      onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                      className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#0F0E17] mb-1">
                      Department
                    </label>
                    <select
                      value={formData.department}
                      onChange={(e) => setFormData({ ...formData, department: e.target.value })}
                      className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                    >
                      <option value="Customer Care">Customer Care & Frontdesk</option>
                      <option value="Sales & Revenue">Sales & Revenue (Outbound SDR)</option>
                      <option value="Technical Operations">Technical Support & Triage</option>
                      <option value="Financial Services">Financial Services & Billing</option>
                      <option value="General Operations">General Operations</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#0F0E17] mb-1">
                      Primary Dialect & Language
                    </label>
                    <select
                      value={formData.language}
                      onChange={(e) => setFormData({ ...formData, language: e.target.value })}
                      className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                    >
                      <option value="English (US & UK)">English (US & UK)</option>
                      <option value="Indian English">Indian English</option>
                      <option value="English, Telugu & Hindi">Multilingual (English, Telugu, Hindi)</option>
                      <option value="Spanish (Latin America)">Spanish (Latin America)</option>
                      <option value="French (European)">French (European)</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#0F0E17] mb-1">
                    Operational Description / Mission
                  </label>
                  <textarea
                    rows={3}
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-3 text-xs text-[#0F0E17] leading-relaxed focus:outline-none focus:border-[#6344E7]"
                  />
                  <p className="text-[11px] text-[#524E5E] mt-1">
                    Defines the core purpose of this employee across internal telephony dispatchers.
                  </p>
                </div>

                <div className="flex items-center justify-between p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
                  <div>
                    <span className="text-xs font-bold text-[#0F0E17] block">Active Workforce Status</span>
                    <span className="text-[11px] text-[#524E5E]">When paused, inbound callers receive after-hours voicemail triage.</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setFormData({ ...formData, status: formData.status === 'active' ? 'paused' : 'active' })}
                    className={`w-10 h-6 flex items-center rounded-full p-1 transition-colors ${
                      formData.status === 'active' ? 'bg-[#22C55E]' : 'bg-[#E4E2EB]'
                    }`}
                  >
                    <div
                      className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform ${
                        formData.status === 'active' ? 'translate-x-4' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>
              </SolidCard>
            </div>
          )}

          {/* TAB 2: TELEPHONY & CALL ROUTING */}
          {activeTab === 'telephony' && (
            <div className="space-y-5 animate-in fade-in duration-150">
              <SolidCard className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
                      Assigned Virtual Phone Number (DID)
                    </h3>
                    <p className="text-[11px] text-[#524E5E]">Carrier PSTN trunk directly allocated to this autonomous agent.</p>
                  </div>
                  <TactileButton
                    size="xs"
                    variant="secondary"
                    icon={Phone}
                    onClick={() => {
                      setBuyNumberPreselectedAgent(agent.id);
                      onOpenBuyNumber();
                    }}
                  >
                    Change / Buy DID
                  </TactileButton>
                </div>

                <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-xl bg-white border border-[#E4E2EB] flex items-center justify-center text-[#6344E7] shadow-craft-xs">
                      <Phone className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="font-mono font-bold text-sm text-[#0F0E17]">
                        {formData.assignedNumber || 'No dedicated number assigned'}
                      </div>
                      <div className="text-[11px] text-[#524E5E]">
                        Carrier: Bandwidth / Twilio Tier-1 Trunk
                      </div>
                    </div>
                  </div>
                  <StatusBadge status={formData.assignedNumber ? 'Active' : 'Idle'} size="xs" />
                </div>
              </SolidCard>

              {/* Call Control Parameters */}
              <SolidCard className="space-y-4">
                <h3 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
                  Call Parameters & Routing Controls
                </h3>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                  <div>
                    <label className="block font-semibold text-[#0F0E17] mb-1">
                      Human Transfer Escalation Number
                    </label>
                    <input
                      type="text"
                      value={formData.transferNumber}
                      onChange={(e) => setFormData({ ...formData, transferNumber: e.target.value })}
                      placeholder="+1 (415) 555-0100"
                      className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-[#0F0E17] font-mono focus:outline-none focus:border-[#6344E7]"
                    />
                    <p className="text-[10px] text-[#524E5E] mt-1">PSTN target for warm live caller handoffs.</p>
                  </div>

                  <div>
                    <label className="block font-semibold text-[#0F0E17] mb-1">
                      Max Simultaneous Concurrency Limit
                    </label>
                    <select
                      value={formData.concurrencyLimit}
                      onChange={(e) => setFormData({ ...formData, concurrencyLimit: parseInt(e.target.value) })}
                      className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-[#0F0E17] font-semibold focus:outline-none focus:border-[#6344E7]"
                    >
                      <option value="1">1 Active Call Line</option>
                      <option value="5">5 Parallel Call Channels</option>
                      <option value="10">10 Parallel Call Channels (Standard)</option>
                      <option value="25">25 Parallel Call Channels</option>
                      <option value="50">50 Enterprise Scale Channels</option>
                    </select>
                    <p className="text-[10px] text-[#524E5E] mt-1">Maximum callers this employee can talk to at once.</p>
                  </div>

                  <div>
                    <label className="block font-semibold text-[#0F0E17] mb-1">
                      Maximum Call Duration Cap
                    </label>
                    <select
                      value={formData.maxDurationMinutes}
                      onChange={(e) => setFormData({ ...formData, maxDurationMinutes: parseInt(e.target.value) })}
                      className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-[#0F0E17] font-semibold focus:outline-none focus:border-[#6344E7]"
                    >
                      <option value="5">5 Minutes</option>
                      <option value="10">10 Minutes</option>
                      <option value="15">15 Minutes (Recommended)</option>
                      <option value="30">30 Minutes</option>
                      <option value="60">60 Minutes</option>
                    </select>
                    <p className="text-[10px] text-[#524E5E] mt-1">Auto-wrap up protection for runaway calls.</p>
                  </div>

                  <div>
                    <label className="block font-semibold text-[#0F0E17] mb-1">
                      Silence Detection Threshold
                    </label>
                    <select
                      value={formData.silenceTimeoutSeconds}
                      onChange={(e) => setFormData({ ...formData, silenceTimeoutSeconds: parseInt(e.target.value) })}
                      className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-[#0F0E17] font-semibold focus:outline-none focus:border-[#6344E7]"
                    >
                      <option value="5">5 Seconds</option>
                      <option value="8">8 Seconds (Default)</option>
                      <option value="12">12 Seconds</option>
                    </select>
                    <p className="text-[10px] text-[#524E5E] mt-1">Seconds of silence before agent asks "Are you still with me?"</p>
                  </div>
                </div>

                <div className="space-y-3 pt-2">
                  <div className="flex items-center justify-between p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-xs">
                    <div>
                      <span className="font-bold text-[#0F0E17] block">Answering Machine Detection (AMD)</span>
                      <span className="text-[11px] text-[#524E5E]">Leave a personalized voicemail drop if carrier detects voicemail beep.</span>
                    </div>
                    <select
                      value={formData.voicemailDetection}
                      onChange={(e) => setFormData({ ...formData, voicemailDetection: e.target.value })}
                      className="bg-white border border-[#E4E2EB] rounded-lg px-2.5 py-1 text-xs text-[#0F0E17] font-semibold focus:outline-none focus:border-[#6344E7]"
                    >
                      <option value="leave_message">Leave Voicemail Drop</option>
                      <option value="hangup">Hang Up Instantly</option>
                      <option value="ignore">Ignore AMD & Continue</option>
                    </select>
                  </div>

                  <div className="flex items-center justify-between p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-xs">
                    <div>
                      <span className="font-bold text-[#0F0E17] block">HIPAA / PCI Call Recording Consent Disclosure</span>
                      <span className="text-[11px] text-[#524E5E]">State "This call may be recorded for quality and training purposes" on pickup.</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setFormData({ ...formData, recordingConsent: !formData.recordingConsent })}
                      className={`w-10 h-6 flex items-center rounded-full p-1 transition-colors ${
                        formData.recordingConsent ? 'bg-[#22C55E]' : 'bg-[#E4E2EB]'
                      }`}
                    >
                      <div
                        className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform ${
                          formData.recordingConsent ? 'translate-x-4' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>
                </div>
              </SolidCard>
            </div>
          )}

          {/* TAB 3: VOICE & ACOUSTICS */}
          {activeTab === 'voice' && (
            <div className="space-y-5 animate-in fade-in duration-150">
              <SolidCard className="space-y-4">
                <h3 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
                  Neural Voice Engine & Acoustic Sliders
                </h3>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                  <div>
                    <label className="block font-semibold text-[#0F0E17] mb-1">
                      Voice Engine Provider
                    </label>
                    <select
                      value={formData.voice.provider}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          voice: { ...formData.voice, provider: e.target.value }
                        })
                      }
                      className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-[#0F0E17] font-semibold focus:outline-none focus:border-[#6344E7]"
                    >
                      <option value="Cartesia">Cartesia Sonic (90ms Latency — Recommended)</option>
                      <option value="ElevenLabs">ElevenLabs Turbo v2.5 (140ms — High Realism)</option>
                      <option value="Deepgram">Deepgram Aura (110ms — Crisp Phone Articulation)</option>
                      <option value="PlayHT">PlayHT 3.0-mini (130ms)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block font-semibold text-[#0F0E17] mb-1">
                      Acoustic Ambient Environment
                    </label>
                    <select
                      value={formData.backgroundSound}
                      onChange={(e) => setFormData({ ...formData, backgroundSound: e.target.value })}
                      className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-[#0F0E17] font-semibold focus:outline-none focus:border-[#6344E7]"
                    >
                      <option value="clean">Clean Studio (Zero Noise)</option>
                      <option value="office">Subtle Executive Office Hum</option>
                      <option value="callcenter">Call Center Professional Chatter</option>
                    </select>
                  </div>
                </div>

                <div className="space-y-4 pt-2">
                  <div>
                    <div className="flex justify-between text-xs mb-1.5">
                      <span className="font-semibold text-[#0F0E17]">Speaking Speed Multiplier</span>
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
                      <span className="font-mono text-[#6344E7] font-bold">
                        {formData.voice.pitch > 0 ? `+${formData.voice.pitch}` : formData.voice.pitch}
                      </span>
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
                      <span className="font-semibold text-[#0F0E17]">Stability & Emotional Consistency</span>
                      <span className="font-mono text-[#6344E7] font-bold">{formData.voice.stability}</span>
                    </div>
                    <input
                      type="range"
                      min="0.3"
                      max="1.0"
                      step="0.05"
                      value={formData.voice.stability}
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

              {/* Live Voice Preview for this employee */}
              <SolidCard className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-bold text-[#0F0E17] flex items-center gap-2">
                      <Radio className="w-3.5 h-3.5 text-[#6344E7]" />
                      <span>Employee Voice Test Preview</span>
                    </h3>
                    <p className="text-[11px] text-[#524E5E]">Test how this employee sounds speaking the greeting with current pitch and speed.</p>
                  </div>
                  <span className={`text-[10px] font-mono px-2 py-0.5 rounded-md border font-semibold ${
                    isPlayingVoice
                      ? 'bg-[#22C55E]/15 text-[#15803D] border-[#22C55E]/30 animate-pulse'
                      : 'bg-[#F0EEF6] text-[#524E5E] border-[#E4E2EB]'
                  }`}>
                    {isPlayingVoice ? '● Audio Active' : 'Ready'}
                  </span>
                </div>

                <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
                  <p className="text-xs font-medium text-[#0F0E17] italic leading-relaxed">
                    "{formData.greeting || `Hi, my name is ${formData.name}. How can I help you?`}"
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  <TactileButton
                    variant={isPlayingVoice ? 'danger' : 'primary'}
                    size="sm"
                    icon={isPlayingVoice ? Square : Play}
                    onClick={handlePlayVoicePreview}
                  >
                    {isPlayingVoice ? 'Stop Audio' : `Hear ${formData.name} Speak`}
                  </TactileButton>

                  <TactileButton
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      onClose();
                      onNavigate('talk-to-ai');
                    }}
                  >
                    Open Live WebRTC Studio
                  </TactileButton>
                </div>
              </SolidCard>
            </div>
          )}

          {/* TAB 4: SCRIPT, PROMPTS & GUARDRAILS */}
          {activeTab === 'script' && (
            <div className="space-y-5 animate-in fade-in duration-150">
              <SolidCard className="space-y-4">
                <h3 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
                  Opening Inbound Greeting Phrase
                </h3>
                <input
                  type="text"
                  value={formData.greeting}
                  onChange={(e) => setFormData({ ...formData, greeting: e.target.value })}
                  placeholder="Hello, thank you for calling..."
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3.5 py-2.5 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                />
                <p className="text-[11px] text-[#524E5E]">
                  Synthesized immediately on SIP connect within 280ms before the caller speaks.
                </p>
              </SolidCard>

              <SolidCard className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
                    Core System Prompt & Directives
                  </h3>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-[10px] text-[#524E5E] uppercase font-bold">Inject:</span>
                    {formData.dynamicVariables.map((v) => (
                      <span
                        key={v}
                        className="px-2 py-0.5 rounded-md bg-[#F0EEF6] border border-[#E4E2EB] text-[10px] font-mono text-[#6344E7] font-semibold"
                      >
                        {`{{${v}}}`}
                      </span>
                    ))}
                  </div>
                </div>

                <textarea
                  rows={9}
                  value={formData.script}
                  onChange={(e) => setFormData({ ...formData, script: e.target.value })}
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-3.5 text-xs text-[#0F0E17] font-mono leading-relaxed focus:outline-none focus:border-[#6344E7]"
                />
              </SolidCard>

              {/* Objection Handling Rules */}
              <SolidCard className="space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
                      Objection Handling Directives ({formData.objectionRules.length})
                    </h3>
                    <p className="text-[11px] text-[#524E5E]">Rules trigger when callers express hesitation, cost questions, or skepticism.</p>
                  </div>
                  <TactileButton size="xs" variant="secondary" icon={Plus} onClick={handleAddObjection}>
                    Add Objection Rule
                  </TactileButton>
                </div>

                <div className="space-y-2.5">
                  {formData.objectionRules.map((rule, idx) => (
                    <div
                      key={idx}
                      className="p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] relative space-y-2 text-xs"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[10px] font-bold text-[#524E5E] uppercase">When Caller Mentions:</span>
                        <button
                          type="button"
                          onClick={() => handleRemoveObjection(idx)}
                          className="text-[#DC2626] hover:text-red-700 text-[10px] font-semibold"
                        >
                          Remove
                        </button>
                      </div>
                      <input
                        type="text"
                        value={rule.trigger}
                        onChange={(e) => {
                          const next = [...formData.objectionRules];
                          next[idx].trigger = e.target.value;
                          setFormData({ ...formData, objectionRules: next });
                        }}
                        className="w-full bg-white border border-[#E4E2EB] rounded-lg px-2.5 py-1 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                      />
                      <span className="text-[10px] font-bold text-[#524E5E] uppercase block">Agent Should Respond:</span>
                      <input
                        type="text"
                        value={rule.response}
                        onChange={(e) => {
                          const next = [...formData.objectionRules];
                          next[idx].response = e.target.value;
                          setFormData({ ...formData, objectionRules: next });
                        }}
                        className="w-full bg-white border border-[#E4E2EB] rounded-lg px-2.5 py-1 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                      />
                    </div>
                  ))}
                </div>
              </SolidCard>

              {/* Prohibited Boundaries */}
              <SolidCard className="space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
                      Compliance Guardrails & Prohibited Topics ({formData.boundaries.length})
                    </h3>
                    <p className="text-[11px] text-[#524E5E]">Strict negative boundaries the agent is never allowed to cross.</p>
                  </div>
                  <TactileButton size="xs" variant="secondary" icon={Plus} onClick={handleAddBoundary}>
                    Add Guardrail
                  </TactileButton>
                </div>

                <div className="space-y-2">
                  {formData.boundaries.map((b, idx) => (
                    <div
                      key={idx}
                      className="p-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] flex items-center justify-between text-xs"
                    >
                      <div className="flex items-center gap-2">
                        <Shield className="w-3.5 h-3.5 text-[#DC2626] shrink-0" />
                        <span className="text-[#0F0E17]">{b}</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleRemoveBoundary(idx)}
                        className="text-[#DC2626] hover:text-red-700 text-xs font-semibold px-2"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              </SolidCard>
            </div>
          )}

          {/* TAB 5: KNOWLEDGE BASE */}
          {activeTab === 'knowledge' && (
            <div className="space-y-5 animate-in fade-in duration-150">
              <SolidCard className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
                      Knowledge Documents Attached to {formData.name}
                    </h3>
                    <p className="text-[11px] text-[#524E5E]">PDFs, pricing guides, and clinical manuals indexed for RAG vector retrieval.</p>
                  </div>
                  <TactileButton size="xs" variant="primary" icon={Plus} onClick={handleAddKnowledge}>
                    Attach Document
                  </TactileButton>
                </div>

                <div className="space-y-2.5">
                  {formData.knowledgeSources.map((doc, idx) => (
                    <div
                      key={idx}
                      className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] flex items-center justify-between text-xs"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-white border border-[#E4E2EB] flex items-center justify-center text-[#6344E7] shadow-craft-xs">
                          <BookOpen className="w-4 h-4" />
                        </div>
                        <div>
                          <span className="font-bold text-[#0F0E17] block">{doc}</span>
                          <span className="text-[10px] text-[#524E5E] font-mono">Vectorized • 100% Retrieved in Sub-100ms</span>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleRemoveKnowledge(idx)}
                        className="text-[#DC2626] hover:text-red-700 p-1.5 rounded-lg hover:bg-red-50 transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </SolidCard>
            </div>
          )}

          {/* TAB 6: INTEGRATIONS & WEBHOOKS */}
          {activeTab === 'integrations' && (
            <div className="space-y-5 animate-in fade-in duration-150">
              <SolidCard className="space-y-4">
                <h3 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
                  Automations & CRM Synchronization
                </h3>

                <div className="space-y-3 text-xs">
                  <div className="flex items-center justify-between p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
                    <div>
                      <span className="font-bold text-[#0F0E17] block">HubSpot & Salesforce Deal Creation</span>
                      <span className="text-[11px] text-[#524E5E]">Post structured conversation summaries & BANT scores automatically.</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setFormData({ ...formData, crmSyncEnabled: !formData.crmSyncEnabled })}
                      className={`w-10 h-6 flex items-center rounded-full p-1 transition-colors ${
                        formData.crmSyncEnabled ? 'bg-[#22C55E]' : 'bg-[#E4E2EB]'
                      }`}
                    >
                      <div
                        className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform ${
                          formData.crmSyncEnabled ? 'translate-x-4' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>

                  <div className="flex items-center justify-between p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
                    <div>
                      <span className="font-bold text-[#0F0E17] block">Live Google Calendar Slot Booking</span>
                      <span className="text-[11px] text-[#524E5E]">Allow {formData.name} to check live team availability and book appointments.</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setFormData({ ...formData, calendarBookingEnabled: !formData.calendarBookingEnabled })}
                      className={`w-10 h-6 flex items-center rounded-full p-1 transition-colors ${
                        formData.calendarBookingEnabled ? 'bg-[#22C55E]' : 'bg-[#E4E2EB]'
                      }`}
                    >
                      <div
                        className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform ${
                          formData.calendarBookingEnabled ? 'translate-x-4' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>
                </div>
              </SolidCard>

              {/* Webhook Dispatcher */}
              <SolidCard className="space-y-3">
                <h3 className="text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
                  Individual Webhook Event Dispatcher
                </h3>
                <p className="text-[11px] text-[#524E5E]">Signed JSON payload dispatched on call.started, call.completed, and lead.qualified for this agent.</p>

                <div>
                  <label className="block text-xs font-semibold text-[#0F0E17] mb-1">
                    Target Endpoint URL
                  </label>
                  <input
                    type="text"
                    value={formData.webhookUrl}
                    onChange={(e) => setFormData({ ...formData, webhookUrl: e.target.value })}
                    className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-mono text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                  />
                </div>
              </SolidCard>
            </div>
          )}

        </div>

        {/* Sticky Bottom Save Bar */}
        <div className="p-4 bg-white border-t border-[#E4E2EB] flex items-center justify-between gap-3 shrink-0 shadow-xs">
          <div className="flex items-center gap-2">
            {isSaved && (
              <span className="text-xs font-semibold text-[#15803D] flex items-center gap-1.5 animate-in fade-in">
                <CheckCircle2 className="w-4 h-4 text-[#15803D]" />
                <span>Configuration saved for {formData.name}!</span>
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            <TactileButton variant="secondary" size="sm" onClick={onClose}>
              Cancel
            </TactileButton>

            <TactileButton
              variant="primary"
              size="sm"
              icon={isSaved ? CheckCircle2 : Save}
              onClick={handleSave}
            >
              {isSaved ? 'Saved!' : 'Save Employee Settings'}
            </TactileButton>
          </div>
        </div>

      </div>
    </div>
  );
}
