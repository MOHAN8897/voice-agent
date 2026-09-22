import React, { useState } from 'react';
import {
  Plus,
  Play,
  FileCode2,
  Copy,
  Pause,
  Trash2,
  Search,
  Volume2,
  Sliders,
  Settings
} from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { StatusBadge } from '../ui/StatusBadge';
import { TactileButton } from '../ui/TactileButton';
import { useWorkspace } from '../context/WorkspaceContext';
import { IndividualEmployeeConsole } from './IndividualEmployeeConsole';

export function EmployeesModule({
  onNavigate,
  onOpenCreateAgent,
  onOpenBuyNumber
}) {
  const {
    agents,
    setSelectedAgentId,
    duplicateAgent,
    toggleAgentStatus,
    deleteAgent,
    setBuyNumberPreselectedAgent
  } = useWorkspace();

  const [filter, setFilter] = useState('All');
  const [search, setSearch] = useState('');
  const [selectedAgentForConsole, setSelectedAgentForConsole] = useState(null);

  const filteredAgents = agents.filter((agent) => {
    const matchesFilter =
      filter === 'All' ||
      (filter === 'Active' && agent.status === 'active') ||
      (filter === 'Paused' && agent.status === 'paused') ||
      (filter === 'Draft' && agent.status === 'draft');

    const matchesSearch =
      agent.name.toLowerCase().includes(search.toLowerCase()) ||
      agent.role.toLowerCase().includes(search.toLowerCase()) ||
      agent.department.toLowerCase().includes(search.toLowerCase());

    return matchesFilter && matchesSearch;
  });

  return (
    <div className="space-y-6">
      {/* Top Header & Fast Filter Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">
            AI Employees Fleet ({agents.length})
          </h2>
          <p className="text-xs text-[#524E5E] mt-0.5">
            Configure autonomous voice agents, customize scripts, and assign dedicated virtual numbers.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <TactileButton
            onClick={onOpenCreateAgent}
            variant="primary"
            icon={Plus}
            size="md"
          >
            Create AI Employee
          </TactileButton>
        </div>
      </div>

      {/* Filter Tabs & Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-2.5 rounded-2xl bg-white border border-[#E4E2EB] shadow-craft-xs">
        {/* Status Pills */}
        <div className="flex items-center p-1 rounded-xl bg-[#F0EEF6] border border-[#E4E2EB]">
          {['All', 'Active', 'Paused', 'Draft'].map((tab) => {
            const count =
              tab === 'All'
                ? agents.length
                : agents.filter((a) => a.status.toLowerCase() === tab.toLowerCase()).length;
            return (
              <button
                key={tab}
                onClick={() => setFilter(tab)}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                  filter === tab
                    ? 'bg-white text-[#0F0E17] shadow-xs'
                    : 'text-[#524E5E] hover:text-[#0F0E17]'
                }`}
              >
                {tab} ({count})
              </button>
            );
          })}
        </div>

        {/* Search Input */}
        <div className="relative min-w-[240px]">
          <Search className="w-3.5 h-3.5 text-[#524E5E] absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, role, department..."
            className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl pl-8 pr-3 py-1.5 text-xs text-[#0F0E17] placeholder-[#8C879A] focus:outline-none focus:border-[#6344E7] transition-colors"
          />
        </div>
      </div>

      {/* Grid of Agent Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {filteredAgents.map((agent) => (
          <SolidCard key={agent.id} className="flex flex-col justify-between group">
            {/* Header: Avatar, Name, Status, Role */}
            <div>
              <div className="flex items-start justify-between gap-3 mb-3">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-2xl bg-[#F0EEF6] border border-[#E4E2EB] flex items-center justify-center text-[#0F0E17] font-bold text-lg shadow-2xs">
                    {agent.name.charAt(0)}
                  </div>
                    <div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedAgentForConsole(agent.id)}
                        className="text-left group/title"
                      >
                        <h3 className="text-sm sm:text-base font-bold text-[#0F0E17] group-hover/title:text-[#6344E7] transition-colors flex items-center gap-1.5">
                          {agent.name}
                        </h3>
                      </button>
                      <StatusBadge status={agent.status} size="xs" />
                    </div>
                    <div className="text-xs text-[#524E5E] font-medium mt-0.5">
                      {agent.role} • <span className="text-[#8C879A]">{agent.department}</span>
                    </div>
                  </div>
                </div>

                {/* Quick Actions: Configure Console & Toggle Status */}
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setSelectedAgentForConsole(agent.id)}
                    title="Employee Settings & Console"
                    className="p-1.5 rounded-lg text-[#524E5E] hover:text-[#6344E7] hover:bg-[#FAF9FD] border border-transparent hover:border-[#E4E2EB] transition-all"
                  >
                    <Sliders className="w-3.5 h-3.5" />
                  </button>

                  <button
                    type="button"
                    onClick={() => toggleAgentStatus(agent.id)}
                    title={agent.status === 'active' ? 'Pause Agent' : 'Activate Agent'}
                    className="p-1.5 rounded-lg text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD] border border-transparent hover:border-[#E4E2EB] transition-all"
                  >
                    <Pause className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {/* Description */}
              <p className="text-xs text-[#524E5E] line-clamp-2 mb-4 leading-relaxed">
                {agent.description}
              </p>

              {/* Specs Ribbon: Phone Number & Voice */}
              <div className="grid grid-cols-2 gap-2 p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] mb-4 text-xs">
                {/* Number */}
                <div>
                  <span className="text-[10px] text-[#8C879A] uppercase tracking-wider block font-bold">
                    Phone Assigned
                  </span>
                  {agent.assignedNumber ? (
                    <span className="font-mono font-semibold text-[#0F0E17] mt-0.5 block truncate">
                      {agent.assignedNumber}
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        setBuyNumberPreselectedAgent(agent.id);
                        onOpenBuyNumber();
                      }}
                      className="text-xs font-semibold text-[#6344E7] hover:underline mt-0.5 flex items-center gap-1"
                    >
                      <Plus className="w-3 h-3" />
                      <span>Assign Number</span>
                    </button>
                  )}
                </div>

                {/* Voice */}
                <div>
                  <span className="text-[10px] text-[#8C879A] uppercase tracking-wider block font-bold">
                    Voice Engine
                  </span>
                  <div className="flex items-center gap-1 font-semibold text-[#0F0E17] mt-0.5 truncate">
                    <Volume2 className="w-3 h-3 text-[#6344E7] shrink-0" />
                    <span className="truncate">{agent.voice.provider} — {agent.voice.voiceName.split('—')[0]}</span>
                  </div>
                </div>
              </div>

              {/* Telemetry Metrics */}
              <div className="grid grid-cols-3 gap-2 py-2.5 border-t border-[#E4E2EB] text-[11px] font-mono mb-4 text-center">
                <div>
                  <span className="text-[#8C879A] block text-[10px]">Calls Handled</span>
                  <span className="font-bold text-[#0F0E17]">{agent.stats.totalCalls.toLocaleString()}</span>
                </div>
                <div>
                  <span className="text-[#8C879A] block text-[10px]">Task Success</span>
                  <span className="font-bold text-[#047857]">{agent.stats.successRate}%</span>
                </div>
                <div>
                  <span className="text-[#8C879A] block text-[10px]">Avg Duration</span>
                  <span className="font-bold text-[#0F0E17]">{agent.stats.avgDuration}</span>
                </div>
              </div>
            </div>

            {/* Bottom Actions Bar */}
            <div className="flex flex-wrap items-center justify-between gap-2 pt-3 border-t border-[#E4E2EB]">
              <div className="flex flex-wrap items-center gap-2">
                <TactileButton
                  size="sm"
                  variant="primary"
                  icon={Sliders}
                  onClick={() => setSelectedAgentForConsole(agent.id)}
                >
                  Configure Settings
                </TactileButton>

                <TactileButton
                  size="sm"
                  variant="secondary"
                  icon={Play}
                  onClick={() => {
                    setSelectedAgentId(agent.id);
                    onNavigate('talk-to-ai');
                  }}
                >
                  Test Voice
                </TactileButton>

                <TactileButton
                  size="sm"
                  variant="ghost"
                  icon={FileCode2}
                  onClick={() => {
                    setSelectedAgentId(agent.id);
                    onNavigate('agent-studio');
                  }}
                >
                  Script Studio
                </TactileButton>
              </div>

              <div className="flex items-center gap-1 ml-auto">
                <button
                  type="button"
                  onClick={() => duplicateAgent(agent.id)}
                  title="Duplicate Agent"
                  className="p-2 rounded-xl text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD] border border-transparent hover:border-[#E4E2EB] transition-all"
                >
                  <Copy className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (confirm(`Are you sure you want to delete ${agent.name}?`)) {
                      deleteAgent(agent.id);
                    }
                  }}
                  title="Delete Agent"
                  className="p-2 rounded-xl text-[#DC2626] hover:bg-[#FEF2F2] border border-transparent hover:border-[#FECACA] transition-all"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </SolidCard>
        ))}
      </div>

      {/* Individual Employee Configuration & Settings Console Modal */}
      <IndividualEmployeeConsole
        agentId={selectedAgentForConsole}
        isOpen={!!selectedAgentForConsole}
        onClose={() => setSelectedAgentForConsole(null)}
        onNavigate={onNavigate}
        onOpenBuyNumber={onOpenBuyNumber}
      />
    </div>
  );
}
