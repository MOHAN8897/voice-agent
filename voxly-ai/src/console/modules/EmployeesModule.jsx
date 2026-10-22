import React, { useState, useEffect } from 'react';
import {
  Plus,
  Play,
  Copy,
  Pause,
  Trash2,
  Search,
  Volume2,
  Sliders,
  FileCode2,
  Phone,
} from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { StatusBadge } from '../ui/StatusBadge';
import { TactileButton } from '../ui/TactileButton';
import { AgentCardsGridSkeleton } from '../ui/Skeleton';
import { useWorkspace } from '../context/WorkspaceContext';
import { AgentStudioModule } from './AgentStudioModule';
import { ErrorBoundary } from '../ui/ErrorBoundary';

export function EmployeesModule({
  onNavigate,
  onOpenCreateAgent,
  onOpenBuyNumber,
  employeeFlowStep,
  onEmployeeFlowStepChange,
  onBackToFleet,
}) {
  const {
    agents,
    selectedAgentId,
    setSelectedAgentId,
    duplicateAgent,
    toggleAgentStatus,
    deleteAgent,
    setBuyNumberPreselectedAgent,
    isLoading,
  } = useWorkspace();

  const [filter, setFilter] = useState('All');
  const [search, setSearch] = useState('');

  // A legacy ?step=telephony / ?step=test link must still open the workspace, not fall
  // back to the fleet list — resolveEmployeeStep maps it to a real tab.
  const inWorkbench = Boolean(employeeFlowStep) && agents.length > 0;

  // Hooks must run before any conditional return — early skeleton used to skip
  // this effect and crash with "Rendered more hooks than during the previous render".
  useEffect(() => {
    if (inWorkbench && selectedAgentId) return;
    if (employeeFlowStep && agents.length && !selectedAgentId) {
      setSelectedAgentId(agents[0].id);
    }
  }, [employeeFlowStep, agents, selectedAgentId, setSelectedAgentId, inWorkbench]);

  const openWorkbench = (agentId, step = 'overview') => {
    setSelectedAgentId(agentId);
    onEmployeeFlowStepChange?.(step, agentId);
  };

  const filteredAgents = agents.filter((agent) => {
    const matchesFilter =
      filter === 'All' ||
      (filter === 'Active' && agent.status === 'active') ||
      (filter === 'Paused' && agent.status === 'paused') ||
      (filter === 'Draft' && agent.status === 'draft');

    const matchesSearch =
      agent.name.toLowerCase().includes(search.toLowerCase()) ||
      agent.role.toLowerCase().includes(search.toLowerCase()) ||
      (agent.department || '').toLowerCase().includes(search.toLowerCase());

    return matchesFilter && matchesSearch;
  });

  if (isLoading && agents.length === 0) {
    return (
      <div className="space-y-6" data-testid="employees-loading" aria-busy="true">
        <div className="space-y-2 animate-pulse">
          <div className="h-6 w-48 bg-[#E4E2EB]/80 rounded-lg" />
          <div className="h-3.5 w-96 max-w-full bg-[#E4E2EB]/80 rounded-lg" />
        </div>
        <AgentCardsGridSkeleton count={3} />
      </div>
    );
  }

  if (inWorkbench) {
    return (
      <ErrorBoundary
        key={selectedAgentId}
        title="Unable to load AI Employee Studio"
        description="An unexpected error occurred while rendering the agent workspace. You can return to your agent fleet or retry."
        onRetry={onBackToFleet}
      >
        <AgentStudioModule
          onNavigate={onNavigate}
          onOpenBuyNumber={onOpenBuyNumber}
          flowStep={employeeFlowStep}
          onFlowStepChange={(step) => onEmployeeFlowStepChange?.(step, selectedAgentId)}
          onBackToFleet={onBackToFleet}
        />
      </ErrorBoundary>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">
            AI Employees ({agents.length})
          </h2>
          <p className="text-xs text-[#524E5E] mt-0.5 max-w-2xl">
            One flow: create an employee, write the script, assign a number, test in the browser, then run
            outgoing calls and campaigns on the live phone AI stack.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <TactileButton onClick={onOpenCreateAgent} variant="primary" icon={Plus} size="md">
            Create AI Employee
          </TactileButton>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-2.5 rounded-2xl bg-white border border-[#E4E2EB] shadow-craft-xs">
        <div className="flex items-center p-1 rounded-xl bg-[#F0EEF6] border border-[#E4E2EB] overflow-x-auto scrollbar-none touch-pan-x">
          {['All', 'Active', 'Paused', 'Draft'].map((tab) => {
            const count =
              tab === 'All'
                ? agents.length
                : agents.filter((a) => a.status.toLowerCase() === tab.toLowerCase()).length;
            return (
              <button
                key={tab}
                onClick={() => setFilter(tab)}
                className={`px-3 py-1.5 min-h-[36px] flex items-center whitespace-nowrap rounded-lg text-xs font-semibold transition-all ${
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

        <div className="relative w-full sm:w-auto sm:min-w-[240px]">
          <Search className="w-3.5 h-3.5 text-[#524E5E] absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search agents..."
            className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl pl-8 pr-3 py-2 sm:py-1.5 min-h-[40px] sm:min-h-[34px] text-base sm:text-xs text-[#0F0E17] placeholder-[#8C879A] focus:outline-none focus:border-[#6344E7] transition-colors"
          />
        </div>
      </div>

      {!isLoading && filteredAgents.length === 0 && (
        <SolidCard className="p-10 text-center space-y-3">
          <p className="text-sm text-[#524E5E]">No agents match your filters.</p>
          <TactileButton onClick={onOpenCreateAgent} variant="primary" icon={Plus}>
            Create your first AI employee
          </TactileButton>
        </SolidCard>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
        {filteredAgents.map((agent) => (
          <SolidCard key={agent.id} data-testid="agent-card" className="flex flex-col justify-between hover:shadow-craft-sm transition-shadow">
            <div className="space-y-4">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-3">
                  <div className="w-11 h-11 rounded-2xl bg-[#F0EEF6] border border-[#E4E2EB] flex items-center justify-center text-[#0F0E17] font-bold text-lg">
                    {agent.name.charAt(0)}
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-[#0F0E17]">{agent.name}</h3>
                    <p className="text-xs text-[#524E5E]">{agent.role}</p>
                  </div>
                </div>
                <StatusBadge status={agent.status} size="xs" />
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <span className="text-[10px] text-[#8C879A] uppercase tracking-wider block font-bold">
                    Live number
                  </span>
                  <div className="flex items-center gap-1 font-mono font-semibold text-[#0F0E17] mt-0.5 truncate">
                    <Phone className="w-3 h-3 text-[#6344E7] shrink-0" />
                    <span className="truncate">{agent.assignedNumber || 'Not assigned'}</span>
                  </div>
                </div>
                <div>
                  <span className="text-[10px] text-[#8C879A] uppercase tracking-wider block font-bold">
                    Voice
                  </span>
                  <div className="flex items-center gap-1 font-semibold text-[#0F0E17] mt-0.5 truncate">
                    <Volume2 className="w-3 h-3 text-[#6344E7] shrink-0" />
                    <span className="truncate">
                      {agent.voice?.provider || 'Default'} — {agent.voice?.voiceName?.split('—')[0] || 'preset'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 py-2.5 border-t border-[#E4E2EB] text-[11px] font-mono mb-4 text-center">
                <div>
                  <span className="text-[#8C879A] block text-[10px]">Calls</span>
                  <span className="font-bold text-[#0F0E17]">
                    {(agent.stats?.totalCalls || 0).toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="text-[#8C879A] block text-[10px]">Success</span>
                  <span className="font-bold text-[#047857]">{agent.stats?.successRate ?? 100}%</span>
                </div>
                <div>
                  <span className="text-[#8C879A] block text-[10px]">Avg</span>
                  <span className="font-bold text-[#0F0E17]">{agent.stats?.avgDuration || '—'}</span>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 pt-3 border-t border-[#E4E2EB]">
              <div className="flex flex-wrap items-center gap-2">
                <TactileButton
                  size="sm"
                  variant="primary"
                  icon={Sliders}
                  onClick={() => openWorkbench(agent.id, 'overview')}
                  data-testid="agent-open-builder"
                >
                  Open builder
                </TactileButton>

                <TactileButton
                  size="sm"
                  variant="secondary"
                  icon={Play}
                  onClick={() => openWorkbench(agent.id, 'script')}
                  data-testid="agent-open-script"
                >
                  Script
                </TactileButton>

                <TactileButton
                  size="sm"
                  variant="ghost"
                  icon={FileCode2}
                  onClick={() => openWorkbench(agent.id, 'calls')}
                  data-testid="agent-open-calls"
                >
                  Calls
                </TactileButton>
              </div>

              <div className="flex items-center gap-1 ml-auto">
                <button
                  type="button"
                  onClick={() => toggleAgentStatus(agent.id)}
                  title={agent.status === 'active' ? 'Pause' : 'Activate'}
                  aria-label={
                    agent.status === 'active'
                      ? `Pause ${agent.name}`
                      : `Activate ${agent.name}`
                  }
                  aria-pressed={agent.status === 'active'}
                  data-testid={`agent-toggle-${agent.id}`}
                  data-status={agent.status}
                  className="p-2 rounded-xl text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD] border border-transparent hover:border-[#E4E2EB] transition-all"
                >
                  {/* Icon follows state: a paused agent offers Play, not Pause. */}
                  {agent.status === 'active' ? (
                    <Pause className="w-3.5 h-3.5" data-testid="agent-toggle-icon-pause" />
                  ) : (
                    <Play className="w-3.5 h-3.5" data-testid="agent-toggle-icon-play" />
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => duplicateAgent(agent.id)}
                  title="Duplicate"
                  className="p-2 rounded-xl text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD] border border-transparent hover:border-[#E4E2EB] transition-all"
                >
                  <Copy className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (confirm(`Delete ${agent.name}?`)) deleteAgent(agent.id);
                  }}
                  title="Delete"
                  className="p-2 rounded-xl text-[#DC2626] hover:bg-[#FEF2F2] border border-transparent hover:border-[#FECACA] transition-all"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </SolidCard>
        ))}
      </div>
    </div>
  );
}
