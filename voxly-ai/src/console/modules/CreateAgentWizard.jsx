import React, { useState } from 'react';
import {
  Check,
  BookOpen,
  Sparkles,
  ArrowRight,
  ArrowLeft
} from 'lucide-react';
import { Modal } from '../ui/Modal';
import { TactileButton } from '../ui/TactileButton';
import { useWorkspace } from '../context/WorkspaceContext';

export function CreateAgentWizard({ isOpen, onClose, onNavigate }) {
  const { createAgent, phoneNumbers } = useWorkspace();
  const [step, setStep] = useState(1);

  // Wizard state
  const [formData, setFormData] = useState({
    name: '',
    role: 'Customer Support Specialist',
    department: 'Customer Care',
    description: '',
    greeting: 'Hello, thank you for calling. How can I assist you today?',
    script: 'You are an autonomous AI voice employee. Greet the caller, understand their query, and provide clear concise answers.',
    dynamicVariables: ['caller_name'],
    voiceProvider: 'Cartesia',
    voiceId: 'sonic-british-warm',
    voiceName: 'Sarah — British Warm',
    speed: 1.0,
    language: 'English (US)',
    selectedNumberId: ''
  });

  const availableNumbers = phoneNumbers.filter((n) => !n.assignedAgentId);

  const handleNext = () => {
    if (step < 6) setStep(step + 1);
  };

  const handleBack = () => {
    if (step > 1) setStep(step - 1);
  };

  const handleSubmit = async () => {
    const selectedNum = phoneNumbers.find((n) => n.id === formData.selectedNumberId);

    const created = await createAgent({
      name: formData.name || 'New Voice Agent',
      role: formData.role,
      department: formData.department,
      description: formData.description || `Autonomous ${formData.role} for voice operations.`,
      greeting: formData.greeting,
      script: formData.script,
      dynamicVariables: formData.dynamicVariables,
      assignedNumber: selectedNum ? selectedNum.number : null,
      numberId: selectedNum ? selectedNum.id : null,
      voice: {
        provider: formData.voiceProvider,
        voiceId: formData.voiceId,
        voiceName: formData.voiceName,
        speed: formData.speed,
        pitch: 0.0,
        stability: 0.75
      },
      language: formData.language
    });

    onClose();
    onNavigate('agent-studio', { agentId: created.id });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Create New AI Voice Agent"
      subtitle="Step-by-step guided setup to configure, calibrate, and deploy a voice employee."
      maxWidth="max-w-2xl"
    >
      <div className="space-y-6">
        {/* Step Indicator Bar */}
        <div className="flex items-center justify-between gap-2 pb-4 border-b border-[#E4E2EB]">
          {[
            { s: 1, label: 'Identity' },
            { s: 2, label: 'Script' },
            { s: 3, label: 'Voice' },
            { s: 4, label: 'Knowledge' },
            { s: 5, label: 'Phone' },
            { s: 6, label: 'Deploy' }
          ].map((item) => (
            <div key={item.s} className="flex items-center gap-1.5">
              <div
                className={`w-6 h-6 rounded-lg text-xs font-mono font-bold flex items-center justify-center transition-all ${
                  step === item.s
                    ? 'bg-[#0F0E17] text-white shadow-2xs'
                    : step > item.s
                    ? 'bg-[#ECFDF5] text-[#047857] border border-[#A7F3D0]'
                    : 'bg-[#F0EEF6] text-[#524E5E] border border-[#E4E2EB]'
                }`}
              >
                {step > item.s ? <Check className="w-3 h-3" /> : item.s}
              </div>
              <span
                className={`text-xs font-semibold hidden sm:inline ${
                  step === item.s ? 'text-[#0F0E17]' : 'text-[#8C879A]'
                }`}
              >
                {item.label}
              </span>
            </div>
          ))}
        </div>

        {/* Step 1: Identity */}
        {step === 1 && (
          <div className="space-y-4 animate-in fade-in duration-150">
            <div>
              <label className="block text-xs font-bold text-[#0F0E17] mb-1">
                Agent Name *
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g. Jordan, Sarah, Alex"
                className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3.5 py-2 text-xs text-[#0F0E17] placeholder-[#8C879A] focus:outline-none focus:border-[#6344E7] transition-colors"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-[#0F0E17] mb-1">
                  Role / Specialization
                </label>
                <select
                  value={formData.role}
                  onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3.5 py-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                >
                  <option value="Inbound Receptionist">Inbound Receptionist</option>
                  <option value="Outbound SDR">Outbound SDR</option>
                  <option value="Customer Support Specialist">Customer Support Specialist</option>
                  <option value="Loan Officer & Debt Advisor">Loan Officer & Debt Advisor</option>
                  <option value="Appointment Scheduler">Appointment Scheduler</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-[#0F0E17] mb-1">
                  Department
                </label>
                <input
                  type="text"
                  value={formData.department}
                  onChange={(e) => setFormData({ ...formData, department: e.target.value })}
                  placeholder="e.g. Front Desk, Sales, Support"
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3.5 py-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-[#0F0E17] mb-1">
                Description
              </label>
              <textarea
                rows={3}
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Describe what this AI agent is responsible for..."
                className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-3 text-xs text-[#0F0E17] placeholder-[#8C879A] focus:outline-none focus:border-[#6344E7] transition-colors"
              />
            </div>
          </div>
        )}

        {/* Step 2: Script & Prompt Flow */}
        {step === 2 && (
          <div className="space-y-4 animate-in fade-in duration-150">
            <div>
              <label className="block text-xs font-bold text-[#0F0E17] mb-1">
                Inbound Opening Greeting *
              </label>
              <input
                type="text"
                value={formData.greeting}
                onChange={(e) => setFormData({ ...formData, greeting: e.target.value })}
                className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3.5 py-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
              />
              <span className="text-[10px] text-[#524E5E] mt-1 block">
                This exact phrase is synthesized as soon as the caller connects.
              </span>
            </div>

            <div>
              <label className="block text-xs font-bold text-[#0F0E17] mb-1">
                Conversation Script & Prompt Directives
              </label>
              <textarea
                rows={6}
                value={formData.script}
                onChange={(e) => setFormData({ ...formData, script: e.target.value })}
                className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-3 text-xs text-[#0F0E17] font-mono leading-relaxed focus:outline-none focus:border-[#6344E7] transition-colors"
              />
            </div>
          </div>
        )}

        {/* Step 3: Voice */}
        {step === 3 && (
          <div className="space-y-4 animate-in fade-in duration-150">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-[#0F0E17] mb-1">
                  Voice Provider
                </label>
                <select
                  value={formData.voiceProvider}
                  onChange={(e) => setFormData({ ...formData, voiceProvider: e.target.value })}
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3.5 py-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                >
                  <option value="Cartesia">Cartesia Sonic (90ms Latency)</option>
                  <option value="ElevenLabs">ElevenLabs Turbo v2.5 (140ms)</option>
                  <option value="Deepgram">Deepgram Aura (110ms)</option>
                  <option value="PlayHT">PlayHT 3.0-mini (130ms)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-[#0F0E17] mb-1">
                  Primary Language
                </label>
                <select
                  value={formData.language}
                  onChange={(e) => setFormData({ ...formData, language: e.target.value })}
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3.5 py-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                >
                  <option value="English (US)">English (US)</option>
                  <option value="English (UK)">English (UK)</option>
                  <option value="Indian English">Indian English</option>
                  <option value="Telugu & English">Telugu & English</option>
                  <option value="Hindi & Hinglish">Hindi & Hinglish</option>
                  <option value="Spanish">Spanish (Latin America)</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-[#0F0E17] mb-1">
                Speaking Pace: {formData.speed}x
              </label>
              <input
                type="range"
                min="0.8"
                max="1.3"
                step="0.05"
                value={formData.speed}
                onChange={(e) => setFormData({ ...formData, speed: parseFloat(e.target.value) })}
                className="w-full accent-[#6344E7]"
              />
              <div className="flex justify-between text-[10px] text-[#524E5E] mt-1 font-mono">
                <span>0.8x (Deliberate)</span>
                <span>1.0x (Natural)</span>
                <span>1.3x (Energetic)</span>
              </div>
            </div>
          </div>
        )}

        {/* Step 4: Knowledge */}
        {step === 4 && (
          <div className="space-y-4 animate-in fade-in duration-150">
            <div className="p-6 rounded-2xl border-2 border-dashed border-[#E4E2EB] bg-[#FAF9FD] text-center">
              <BookOpen className="w-8 h-8 text-[#6344E7] mx-auto mb-2" />
              <h4 className="text-xs font-bold text-[#0F0E17]">Drag & Drop Business Documents</h4>
              <p className="text-[11px] text-[#524E5E] mt-1">
                Upload PDFs, price sheets, service lists, or FAQs. The agent will reference them dynamically during calls.
              </p>
              <button
                type="button"
                className="mt-3 px-3 py-1.5 text-xs font-semibold text-[#0F0E17] bg-white border border-[#E4E2EB] rounded-xl hover:bg-[#F0EEF6] transition-all shadow-2xs"
              >
                Browse Files (.PDF, .DOCX, .TXT)
              </button>
            </div>
          </div>
        )}

        {/* Step 5: Phone Number */}
        {step === 5 && (
          <div className="space-y-4 animate-in fade-in duration-150">
            <div>
              <label className="block text-xs font-bold text-[#0F0E17] mb-2">
                Connect Virtual Telephone Number
              </label>

              {availableNumbers.length > 0 ? (
                <div className="space-y-2">
                  {availableNumbers.map((num) => (
                    <label
                      key={num.id}
                      className={`flex items-center justify-between p-3 rounded-xl border cursor-pointer transition-all ${
                        formData.selectedNumberId === num.id
                          ? 'bg-[#6344E7]/10 border-[#6344E7] text-[#0F0E17]'
                          : 'bg-[#FAF9FD] border-[#E4E2EB] text-[#524E5E] hover:border-[#D1CFDB]'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <input
                          type="radio"
                          name="assignedNumber"
                          checked={formData.selectedNumberId === num.id}
                          onChange={() => setFormData({ ...formData, selectedNumberId: num.id })}
                          className="accent-[#6344E7]"
                        />
                        <div>
                          <div className="font-mono font-bold text-xs text-[#0F0E17]">{num.number}</div>
                          <div className="text-[10px] text-[#524E5E]">{num.locality} • {num.type}</div>
                        </div>
                      </div>
                      <span className="text-[11px] font-mono text-[#047857]">Available</span>
                    </label>
                  ))}
                </div>
              ) : (
                <div className="p-4 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-center text-xs text-[#524E5E]">
                  <p className="font-semibold text-[#0F0E17]">All existing numbers are currently assigned.</p>
                  <span className="text-[11px] text-[#524E5E] mt-1 block">
                    You can create this agent now and buy/assign a new virtual number in the Phone Numbers tab.
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Step 6: Deploy & Review */}
        {step === 6 && (
          <div className="space-y-4 animate-in fade-in duration-150">
            <div className="p-4 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-2 text-xs">
              <div className="flex justify-between py-1 border-b border-[#E4E2EB]">
                <span className="text-[#524E5E]">Agent Name</span>
                <span className="font-bold text-[#0F0E17]">{formData.name || 'Untitled Agent'}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-[#E4E2EB]">
                <span className="text-[#524E5E]">Role</span>
                <span className="font-semibold text-[#0F0E17]">{formData.role}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-[#E4E2EB]">
                <span className="text-[#524E5E]">Voice Engine</span>
                <span className="text-[#0F0E17]">{formData.voiceProvider} ({formData.language})</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-[#524E5E]">Connected Number</span>
                <span className="font-mono text-[#0F0E17]">
                  {phoneNumbers.find((n) => n.id === formData.selectedNumberId)?.number || 'Unassigned (Can bind later)'}
                </span>
              </div>
            </div>

            <p className="text-xs text-[#524E5E] text-center">
              Clicking <b>Activate Agent</b> provisions the conversational workflow and registers the agent in your fleet directory.
            </p>
          </div>
        )}

        {/* Footer Navigation Controls */}
        <div className="flex items-center justify-between pt-4 border-t border-[#E4E2EB]">
          <button
            type="button"
            onClick={handleBack}
            disabled={step === 1}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17] disabled:opacity-30 disabled:pointer-events-none transition-all"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back</span>
          </button>

          {step < 6 ? (
            <TactileButton
              variant="primary"
              size="sm"
              icon={ArrowRight}
              onClick={handleNext}
            >
              Continue
            </TactileButton>
          ) : (
            <TactileButton
              variant="primary"
              size="md"
              icon={Sparkles}
              onClick={handleSubmit}
            >
              Activate Agent
            </TactileButton>
          )}
        </div>
      </div>
    </Modal>
  );
}
