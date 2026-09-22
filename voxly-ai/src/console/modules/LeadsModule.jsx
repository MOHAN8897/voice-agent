import React, { useState } from 'react';
import {
  PhoneCall,
  LayoutGrid,
  List
} from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { StatusBadge } from '../ui/StatusBadge';
import { TactileButton } from '../ui/TactileButton';
import { Modal } from '../ui/Modal';
import { useWorkspace } from '../context/WorkspaceContext';

export function LeadsModule() {
  const {
    leads,
    updateLeadStage,
    updateLeadNotes,
    triggerCallToLead,
    createLead,
    phoneNumbers,
    outboundFromE164,
    setPreferredOutboundFrom,
  } = useWorkspace();
  const [viewMode, setViewMode] = useState('kanban'); // 'kanban' | 'table'
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedLead, setSelectedLead] = useState(null);
  const [callNotice, setCallNotice] = useState(null);
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [addForm, setAddForm] = useState({ name: '', phone: '', email: '', notes: '' });
  const [addError, setAddError] = useState(null);

  const stages = ['New', 'Contacted', 'Qualified', 'Meeting Booked', 'Unqualified'];

  const filteredLeads = leads.filter((l) => {
    const q = searchQuery.toLowerCase();
    return (
      (l.name || '').toLowerCase().includes(q) ||
      (l.company || '').toLowerCase().includes(q) ||
      (l.intent || '').toLowerCase().includes(q) ||
      (l.phone || '').includes(searchQuery)
    );
  });

  const [callError, setCallError] = useState(null);

  const handleTriggerCall = async (lead) => {
    setCallError(null);
    try {
      await triggerCallToLead(lead.id);
      setCallNotice(`Outbound call started to ${lead.name} (${lead.phone})`);
      setTimeout(() => setCallNotice(null), 3500);
    } catch (e) {
      setCallError(e.message || 'Could not start call');
    }
  };

  return (
    <div className="space-y-6">
      {callError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900">{callError}</div>
      )}
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">
            Autonomous Lead Pipeline ({leads.length})
          </h2>
          <p className="text-xs text-[#524E5E] mt-0.5">
            Leads automatically captured, BANT-qualified, and scored by AI voice employees during phone calls.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
          {phoneNumbers.length > 0 && (
            <select
              value={outboundFromE164 || ''}
              onChange={(e) => setPreferredOutboundFrom(e.target.value)}
              className="text-xs border border-[#E4E2EB] rounded-lg px-2 py-1.5 bg-white"
              aria-label="Outbound caller ID"
            >
              <option value="">Auto-select DID</option>
              {phoneNumbers.map((n) => (
                <option key={n.id} value={n.number}>
                  {n.formatted || n.number}
                </option>
              ))}
            </select>
          )}
          <TactileButton variant="primary" size="sm" onClick={() => setIsAddOpen(true)}>
            Add lead
          </TactileButton>
        </div>

        {/* View Toggle */}
        <div className="flex items-center gap-2">
          <div className="flex items-center p-1 rounded-xl bg-white border border-[#E4E2EB] shadow-2xs">
            <button
              onClick={() => setViewMode('kanban')}
              className={`p-1.5 rounded-lg transition-all ${
                viewMode === 'kanban' ? 'bg-[#0F0E17] text-white shadow-xs' : 'text-[#524E5E] hover:text-[#0F0E17]'
              }`}
              title="Kanban Board View"
            >
              <LayoutGrid className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setViewMode('table')}
              className={`p-1.5 rounded-lg transition-all ${
                viewMode === 'table' ? 'bg-[#0F0E17] text-white shadow-xs' : 'text-[#524E5E] hover:text-[#0F0E17]'
              }`}
              title="Data Table View"
            >
              <List className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Call Trigger Notification Banner */}
      {callNotice && (
        <div className="p-3.5 rounded-xl bg-[#ECFDF5] border border-[#A7F3D0] text-xs font-semibold text-[#047857] flex items-center justify-between animate-in fade-in duration-150">
          <div className="flex items-center gap-2">
            <PhoneCall className="w-4 h-4 animate-pulse text-[#10B981]" />
            <span>{callNotice}</span>
          </div>
          <span className="text-[10px] font-mono">SIP INVITE Dispatched</span>
        </div>
      )}

      {/* KANBAN PIPELINE VIEW */}
      {viewMode === 'kanban' && (
        <div className="flex md:grid md:grid-cols-5 gap-4 overflow-x-auto pb-4 max-w-full">
          {stages.map((stage) => {
            const stageLeads = filteredLeads.filter((l) => l.stage === stage);
            return (
              <div key={stage} className="flex flex-col min-w-[240px] space-y-3">
                {/* Column Header */}
                <div className="flex items-center justify-between p-3 rounded-xl bg-white border border-[#E4E2EB] shadow-2xs">
                  <span className="text-xs font-bold text-[#0F0E17] truncate">{stage}</span>
                  <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-[#F0EEF6] text-[#524E5E]">
                    {stageLeads.length}
                  </span>
                </div>

                {/* Cards in Column */}
                <div className="space-y-3 flex-1">
                  {stageLeads.map((lead) => (
                    <SolidCard
                      key={lead.id}
                      padding="p-3.5"
                      className="space-y-2.5 hover:border-[#D1CFDB] transition-all cursor-pointer group shadow-craft-xs"
                      onClick={() => setSelectedLead(lead)}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="text-xs font-bold text-[#0F0E17] group-hover:text-[#6344E7] transition-colors">
                            {lead.name}
                          </div>
                          <div className="text-[11px] text-[#524E5E] truncate">{lead.company}</div>
                        </div>

                        {/* BANT Score Badge */}
                        <span
                          className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded border ${
                            lead.bantScore >= 80
                              ? 'bg-[#ECFDF5] text-[#047857] border-[#A7F3D0]'
                              : lead.bantScore >= 50
                              ? 'bg-[#FFFBEB] text-[#92400E] border-[#FDE68A]'
                              : 'bg-[#FEF2F2] text-[#991B1B] border-[#FECACA]'
                          }`}
                        >
                          BANT {lead.bantScore}
                        </span>
                      </div>

                      <div className="text-[11px] text-[#524E5E] line-clamp-1">
                        🎯 {lead.intent}
                      </div>

                      {/* Card Bottom: Agent & Quick Call Trigger */}
                      <div className="flex items-center justify-between pt-2 border-t border-[#E4E2EB] text-[10px] text-[#8C879A]">
                        <span>{lead.agentName}</span>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleTriggerCall(lead);
                          }}
                          className="flex items-center gap-1 text-[#6344E7] hover:text-[#5034CE] font-bold"
                        >
                          <PhoneCall className="w-3 h-3" />
                          <span>Call</span>
                        </button>
                      </div>
                    </SolidCard>
                  ))}

                  {stageLeads.length === 0 && (
                    <div className="p-6 rounded-xl border border-dashed border-[#E4E2EB] text-center text-[11px] text-[#8C879A]">
                      No leads in {stage}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* DATA TABLE VIEW */}
      {viewMode === 'table' && (
        <SolidCard padding="p-0" className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-[#E4E2EB] bg-[#FAF9FD] text-[10px] font-bold text-[#8C879A] uppercase tracking-wider">
                  <th className="py-3 px-4">Contact</th>
                  <th className="py-3 px-3">Company</th>
                  <th className="py-3 px-3 font-mono">BANT Score</th>
                  <th className="py-3 px-3">Stage</th>
                  <th className="py-3 px-3">Intent</th>
                  <th className="py-3 px-3">Agent</th>
                  <th className="py-3 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E4E2EB]">
                {filteredLeads.map((lead) => (
                  <tr
                    key={lead.id}
                    onClick={() => setSelectedLead(lead)}
                    className="hover:bg-[#FAF9FD] transition-colors cursor-pointer"
                  >
                    <td className="py-3 px-4">
                      <div className="font-semibold text-[#0F0E17]">{lead.name}</div>
                      <div className="text-[10px] font-mono text-[#524E5E]">{lead.phone}</div>
                    </td>
                    <td className="py-3 px-3 text-[#524E5E] font-medium">{lead.company}</td>
                    <td className="py-3 px-3 font-mono font-bold text-[#047857]">{lead.bantScore}/100</td>
                    <td className="py-3 px-3">
                      <StatusBadge status={lead.stage} size="xs" />
                    </td>
                    <td className="py-3 px-3 text-[#524E5E] truncate max-w-[160px]">{lead.intent}</td>
                    <td className="py-3 px-3 text-[#8C879A]">{lead.agentName}</td>
                    <td className="py-3 px-4 text-right">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleTriggerCall(lead);
                        }}
                        className="text-xs font-semibold text-[#6344E7] hover:underline"
                      >
                        Call Now
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SolidCard>
      )}

      {/* LEAD DETAIL MODAL */}
      {selectedLead && (
        <Modal
          isOpen={!!selectedLead}
          onClose={() => setSelectedLead(null)}
          title={selectedLead.name}
          subtitle={`Captured by ${selectedLead.agentName} • ${selectedLead.source}`}
          maxWidth="max-w-xl"
        >
          <div className="space-y-4 text-xs">
            {/* Stage Selector Ribbon */}
            <div className="p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] flex items-center justify-between">
              <span className="font-bold text-[#0F0E17]">Pipeline Stage:</span>
              <select
                value={selectedLead.stage}
                onChange={(e) => {
                  updateLeadStage(selectedLead.id, e.target.value);
                  setSelectedLead({ ...selectedLead, stage: e.target.value });
                }}
                className="bg-white border border-[#E4E2EB] rounded-lg px-2.5 py-1 text-xs text-[#0F0E17] font-semibold focus:outline-none focus:border-[#6344E7] transition-colors"
              >
                {stages.map((st) => (
                  <option key={st} value={st}>
                    {st}
                  </option>
                ))}
              </select>
            </div>

            {/* Contact Details */}
            <div className="grid grid-cols-2 gap-3 p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
              <div>
                <span className="text-[10px] text-[#8C879A] uppercase block">Phone</span>
                <span className="font-mono text-[#0F0E17] font-semibold">{selectedLead.phone}</span>
              </div>
              <div>
                <span className="text-[10px] text-[#8C879A] uppercase block">Email</span>
                <span className="text-[#0F0E17] truncate block">{selectedLead.email || 'None on file'}</span>
              </div>
              <div>
                <span className="text-[10px] text-[#8C879A] uppercase block">Company</span>
                <span className="text-[#0F0E17] font-semibold">{selectedLead.company}</span>
              </div>
              <div>
                <span className="text-[10px] text-[#8C879A] uppercase block">BANT Score</span>
                <span className="font-mono font-bold text-[#047857]">{selectedLead.bantScore} / 100</span>
              </div>
            </div>

            {/* AI Notes */}
            <div>
              <label className="block text-xs font-bold text-[#0F0E17] mb-1">
                AI Extracted Notes & Summary
              </label>
              <textarea
                rows={3}
                value={selectedLead.notes}
                onChange={(e) => {
                  updateLeadNotes(selectedLead.id, e.target.value);
                  setSelectedLead({ ...selectedLead, notes: e.target.value });
                }}
                className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-3 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
              />
            </div>

            {/* Modal Bottom CTA */}
            <div className="flex items-center justify-between pt-3 border-t border-[#E4E2EB]">
              <span className="text-[11px] text-[#8C879A]">Saved to your tenant CRM</span>
              <TactileButton
                variant="primary"
                size="sm"
                icon={PhoneCall}
                onClick={() => {
                  handleTriggerCall(selectedLead);
                  setSelectedLead(null);
                }}
              >
                Trigger Outbound AI Call
              </TactileButton>
            </div>
          </div>
        </Modal>
      )}

      <Modal isOpen={isAddOpen} onClose={() => setIsAddOpen(false)} title="Add lead" maxWidth="max-w-md">
        <div className="space-y-3">
          {addError && <p className="text-xs text-red-700">{addError}</p>}
          <input
            className="w-full border border-[#E4E2EB] rounded-lg p-2 text-xs"
            placeholder="Name"
            value={addForm.name}
            onChange={(e) => setAddForm({ ...addForm, name: e.target.value })}
          />
          <input
            className="w-full border border-[#E4E2EB] rounded-lg p-2 text-xs"
            placeholder="Phone (E.164)"
            value={addForm.phone}
            onChange={(e) => setAddForm({ ...addForm, phone: e.target.value })}
          />
          <input
            className="w-full border border-[#E4E2EB] rounded-lg p-2 text-xs"
            placeholder="Email"
            value={addForm.email}
            onChange={(e) => setAddForm({ ...addForm, email: e.target.value })}
          />
          <textarea
            className="w-full border border-[#E4E2EB] rounded-lg p-2 text-xs"
            placeholder="Notes"
            rows={3}
            value={addForm.notes}
            onChange={(e) => setAddForm({ ...addForm, notes: e.target.value })}
          />
          <TactileButton
            variant="primary"
            size="sm"
            onClick={async () => {
              setAddError(null);
              try {
                if (!addForm.name.trim()) throw new Error('Name is required');
                await createLead(addForm);
                setIsAddOpen(false);
                setAddForm({ name: '', phone: '', email: '', notes: '' });
              } catch (e) {
                setAddError(e.message || 'Could not create lead');
              }
            }}
          >
            Save lead
          </TactileButton>
        </div>
      </Modal>
    </div>
  );
}
