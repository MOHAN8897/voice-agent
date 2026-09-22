import React, { useState, useEffect } from 'react';
import {
  Megaphone,
  Plus,
  Play,
  Pause,
  FileSpreadsheet
} from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { StatusBadge } from '../ui/StatusBadge';
import { TactileButton } from '../ui/TactileButton';
import { Modal } from '../ui/Modal';
import { useWorkspace } from '../context/WorkspaceContext';

export function CampaignsModule() {
  const {
    campaigns,
    createCampaign,
    toggleCampaignStatus,
    startCampaign,
    fetchCampaignAnalytics,
    agents,
  } = useWorkspace();
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [launchError, setLaunchError] = useState(null);
  const [analytics, setAnalytics] = useState({});

  // Wizard state
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState({
    name: '',
    objective: 'Reactivate past customers with personalized promotion',
    agentId: agents[0]?.id || '',
    contactsCount: 1500,
    concurrencyLimit: 20,
    callingHours: '09:00 - 18:00 (Local Recipient Time)',
    contactLines: '',
  });

  useEffect(() => {
    if (!campaigns.length) return;
    campaigns.forEach((c) => {
      fetchCampaignAnalytics(c.id)
        .then((a) => setAnalytics((prev) => ({ ...prev, [c.id]: a })))
        .catch(() => {});
    });
  }, [campaigns, fetchCampaignAnalytics]);

  const handleLaunch = async () => {
    setLaunchError(null);
    try {
      const contacts = formData.contactLines
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
        .map((phone) => ({ phone }));
      await createCampaign({
        name: formData.name || 'New Outbound Campaign',
        objective: formData.objective,
        agentId: formData.agentId,
        totalContacts: contacts.length,
        concurrencyLimit: formData.concurrencyLimit,
        callingHours: formData.callingHours,
        contacts,
        autoStart: true,
      });
      setIsCreateModalOpen(false);
      setStep(1);
    } catch (e) {
      setLaunchError(e.message || 'Could not create campaign');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">
            Bulk Outbound Campaigns ({campaigns.length})
          </h2>
          <p className="text-xs text-[#524E5E] mt-0.5">
            Automate phone outreach at scale with AI agents, smart pacing, and Answering Machine Detection (AMD).
          </p>
        </div>

        <TactileButton
          onClick={() => setIsCreateModalOpen(true)}
          variant="primary"
          icon={Plus}
          size="md"
        >
          New Campaign
        </TactileButton>
      </div>

      {/* Campaigns List */}
      <div className="space-y-4">
        {campaigns.map((camp) => {
          const stats = analytics[camp.id] || {};
          const total = stats.attempts ?? camp.totalContacts ?? 0;
          const connected = stats.connects ?? camp.connectedCalls ?? 0;
          const agent = agents.find((a) => a.id === camp.agentId);
          return (
          <SolidCard key={camp.id} className="space-y-4">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-[#E4E2EB]">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-[#F0EEF6] border border-[#E4E2EB] flex items-center justify-center text-[#6344E7] shadow-2xs">
                  <Megaphone className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-bold text-[#0F0E17]">{camp.name}</h3>
                    <StatusBadge status={camp.status} size="xs" />
                  </div>
                  <div className="text-xs text-[#524E5E] mt-0.5">
                    Agent: <span className="font-semibold text-[#0F0E17]">{agent?.name || camp.agentName || '—'}</span>
                  </div>
                </div>
              </div>

              {/* Pause / Resume Action */}
              <div className="flex items-center gap-2">
                {camp.status === 'draft' && (
                  <TactileButton size="sm" variant="primary" icon={Play} onClick={() => startCampaign(camp.id)}>
                    Start dialer
                  </TactileButton>
                )}
                <TactileButton
                  size="sm"
                  variant={camp.status === 'running' ? 'secondary' : 'primary'}
                  icon={camp.status === 'running' ? Pause : Play}
                  onClick={() => toggleCampaignStatus(camp.id)}
                >
                  {camp.status === 'running' ? 'Pause Campaign' : 'Resume Dialing'}
                </TactileButton>
              </div>
            </div>

            {/* Metrics Ribbon */}
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-center font-mono">
              <div>
                <span className="text-[10px] text-[#8C879A] uppercase block">Total Contacts</span>
                <span className="text-sm font-bold text-[#0F0E17]">{Number(total).toLocaleString()}</span>
              </div>
              <div>
                <span className="text-[10px] text-[#8C879A] uppercase block">Answer Rate</span>
                <span className="text-sm font-bold text-[#047857]">
                  {total ? Math.round((connected / total) * 100) : 0}%
                </span>
              </div>
              <div>
                <span className="text-[10px] text-[#8C879A] uppercase block">Connected Calls</span>
                <span className="text-sm font-bold text-[#0F0E17]">{connected}</span>
              </div>
              <div>
                <span className="text-[10px] text-[#8C879A] uppercase block">Leads Generated</span>
                <span className="text-sm font-bold text-[#6344E7]">{camp.leadsGenerated}</span>
              </div>
              <div>
                <span className="text-[10px] text-[#8C879A] uppercase block">Cost Incurred</span>
                <span className="text-sm font-bold text-[#0F0E17]">{camp.costIncurred}</span>
              </div>
            </div>

            {/* Progress Bar & Concurrency Gauge */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs text-[#524E5E]">
                <span>Contacts loaded ({connected} / {total})</span>
                <span className="font-mono font-bold text-[#0F0E17]">
                  {total ? Math.round((connected / total) * 100) : 0}%
                </span>
              </div>
              <div className="h-2 w-full bg-[#F0EEF6] rounded-full overflow-hidden border border-[#E4E2EB]">
                <div
                  style={{ width: `${total ? Math.round((connected / total) * 100) : 0}%` }}
                  className="h-full bg-[#6344E7] rounded-full transition-all"
                />
              </div>
              <div className="flex justify-between text-[11px] text-[#8C879A] font-mono pt-1">
                <span>Concurrency: {camp.concurrencyLimit} simultaneous lines</span>
                <span>{camp.callingHours}</span>
              </div>
            </div>
          </SolidCard>
          );
        })}
      </div>

      {/* CREATE CAMPAIGN WIZARD MODAL */}
      <Modal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        title="Launch Outbound Dialing Campaign"
        subtitle="Configure target audience, assign voice agent, and set pacing parameters."
        maxWidth="max-w-xl"
      >
        <div className="space-y-5 text-xs">
          {launchError && <p className="text-red-700 text-xs">{launchError}</p>}
          {step === 1 && (
            <div className="space-y-4">
              <div>
                <label className="block font-bold text-[#0F0E17] mb-1">Campaign Title *</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g. Q4 Dental Hygiene Recall"
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-2.5 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                />
              </div>

              <div>
                <label className="block font-bold text-[#0F0E17] mb-1">Select AI Employee</label>
                <select
                  value={formData.agentId}
                  onChange={(e) => setFormData({ ...formData, agentId: e.target.value })}
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-2.5 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                >
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} — {a.role}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block font-bold text-[#0F0E17] mb-1 flex items-center gap-2">
                  <FileSpreadsheet className="w-3.5 h-3.5" /> Contact phones (one per line)
                </label>
                <textarea
                  rows={5}
                  value={formData.contactLines}
                  onChange={(e) => setFormData({ ...formData, contactLines: e.target.value })}
                  placeholder="+919876543210&#10;+14155550199"
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-2.5 text-xs font-mono"
                />
              </div>

              <div className="flex justify-end pt-2">
                <TactileButton variant="primary" size="sm" onClick={() => setStep(2)}>
                  Next: Pacing & Compliance
                </TactileButton>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <div>
                <label className="block font-bold text-[#0F0E17] mb-1">
                  Max Concurrent Lines: {formData.concurrencyLimit} calls
                </label>
                <input
                  type="range"
                  min="5"
                  max="50"
                  step="5"
                  value={formData.concurrencyLimit}
                  onChange={(e) => setFormData({ ...formData, concurrencyLimit: parseInt(e.target.value) })}
                  className="w-full accent-[#6344E7]"
                />
                <span className="text-[10px] text-[#524E5E] mt-1 block font-mono">
                  Controls how many calls dial simultaneously. Paced to avoid carrier line congestion.
                </span>
              </div>

              <div>
                <label className="block font-bold text-[#0F0E17] mb-1">
                  TCPA Calling Hours Window
                </label>
                <input
                  type="text"
                  value={formData.callingHours}
                  onChange={(e) => setFormData({ ...formData, callingHours: e.target.value })}
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-2.5 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                />
              </div>

              <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-1 font-mono text-[11px]">
                <div className="flex justify-between text-[#524E5E]">
                  <span>Total Contacts</span>
                  <span className="text-[#0F0E17] font-bold">1,500</span>
                </div>
                <div className="flex justify-between text-[#524E5E]">
                  <span>Est. Talk Time</span>
                  <span className="text-[#0F0E17] font-bold">~3,200 min</span>
                </div>
                <div className="flex justify-between text-[#524E5E]">
                  <span>Est. Total Cost</span>
                  <span className="font-bold text-[#047857]">$152.00 USD</span>
                </div>
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-[#E4E2EB]">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17]"
                >
                  Back
                </button>
                <TactileButton variant="primary" size="md" onClick={handleLaunch}>
                  Launch Outbound Campaign
                </TactileButton>
              </div>
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
}
