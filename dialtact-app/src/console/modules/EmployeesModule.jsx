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
  Users,
} from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { StatusBadge } from '../ui/StatusBadge';
import { TactileButton } from '../ui/TactileButton';
import { Avatar } from '../ui/Avatar';
import { PageHeader } from '../ui/PageHeader';
import { EmptyState } from '../ui/EmptyState';
import { Tabs } from '../ui/Tabs';
import { Toolbar, SearchInput } from '../ui/Toolbar';
import { useLiveRail } from './home/useActivity';
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
  // Same live snapshot the Home rail uses (paused while the tab is hidden, 5s only
  // while someone is on a call), so an employee on a call gets the green ring here
  // and in the workspace header too.
  const live = useLiveRail(true);
  const onCallIds = new Set((live.calls || []).map((call) => call.agentId).filter(Boolean));

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
        <PageHeader title="AI employees" description="Loading your team…" />
        <AgentCardsGridSkeleton count={3} />
      </div>
    );
  }

  if (inWorkbench) {
    return (
      <ErrorBoundary
        key={selectedAgentId}
        title="This employee could not be opened"
        description="Something went wrong while loading this employee. Go back to your team and try again."
        onRetry={onBackToFleet}
      >
        <AgentStudioModule
          onNavigate={onNavigate}
          onOpenBuyNumber={onOpenBuyNumber}
          flowStep={employeeFlowStep}
          onFlowStepChange={(step) => onEmployeeFlowStepChange?.(step, selectedAgentId)}
          onBackToFleet={onBackToFleet}
          liveAgentIds={onCallIds}
        />
      </ErrorBoundary>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={`AI employees (${agents.length})`}
        description="Create an employee, write what they say, give them a number, test them in the browser, then let them take and make calls."
        actions={
          <TactileButton onClick={onOpenCreateAgent} variant="primary" icon={Plus} size="md">
            Create AI employee
          </TactileButton>
        }
      />

      <Toolbar className="rounded-card border border-line bg-surface p-2.5 shadow-craft-xs">
        <Tabs
          variant="pills"
          label="Filter employees by status"
          value={filter}
          onChange={setFilter}
          className="max-w-full"
          items={['All', 'Active', 'Paused', 'Draft'].map((tab) => ({
            id: tab,
            label: tab,
            count:
              tab === 'All'
                ? agents.length
                : agents.filter((a) => a.status.toLowerCase() === tab.toLowerCase()).length,
          }))}
        />
        <Toolbar.Spacer />
        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder="Search employees"
          className="w-full sm:w-64"
        />
      </Toolbar>

      {!isLoading && filteredAgents.length === 0 && (
        <SolidCard padding="p-0">
          <EmptyState
            icon={Users}
            title={agents.length === 0 ? 'No AI employees yet' : 'No employees match these filters'}
            description={
              agents.length === 0
                ? 'Your first employee can answer calls and call leads for you once it has a script and a number.'
                : 'Try another status or clear the search.'
            }
            action={
              <TactileButton onClick={onOpenCreateAgent} variant="primary" icon={Plus}>
                Create your first AI employee
              </TactileButton>
            }
          />
        </SolidCard>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {filteredAgents.map((agent) => (
          <SolidCard key={agent.id} data-testid="agent-card" padding="p-5" className="flex min-w-0 flex-col justify-between transition-shadow hover:shadow-craft-sm">
            <div className="space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                  <Avatar name={agent.name} size="lg" live={onCallIds.has(agent.id)} />
                  <div className="min-w-0">
                    <h3 className="truncate text-title text-ink" title={agent.name}>{agent.name}</h3>
                    <p className="truncate text-ui text-fg-body" title={agent.role}>
                      {onCallIds.has(agent.id) ? 'On a call now' : agent.role}
                    </p>
                  </div>
                </div>
                {onCallIds.has(agent.id) ? (
                  <StatusBadge status="live" label="On a call" tone="live" size="xs" />
                ) : (
                  <StatusBadge status={agent.status} size="xs" />
                )}
              </div>

              <dl className="grid grid-cols-1 gap-3 min-[400px]:grid-cols-2">
                <div className="min-w-0">
                  <dt className="text-meta text-fg-muted">Phone number</dt>
                  <dd className="mt-0.5 flex min-w-0 items-center gap-1.5 text-ui text-ink" title={agent.assignedNumber || 'Not assigned'}>
                    <Phone className="h-3.5 w-3.5 shrink-0 text-fg-subtle" aria-hidden="true" />
                    <span className={`truncate ${agent.assignedNumber ? 'font-mono tabular-nums' : 'text-fg-muted'}`}>
                      {agent.assignedNumber || 'Not assigned'}
                    </span>
                  </dd>
                </div>
                <div className="min-w-0">
                  <dt className="text-meta text-fg-muted">Voice</dt>
                  <dd className="mt-0.5 flex min-w-0 items-center gap-1.5 text-ui text-ink">
                    <Volume2 className="h-3.5 w-3.5 shrink-0 text-fg-subtle" aria-hidden="true" />
                    <span className="truncate">
                      {agent.voice?.voiceId || agent.voice?.voiceName ? 'Custom voice' : 'Default voice'}
                    </span>
                  </dd>
                </div>
              </dl>

              <dl className="mb-4 grid grid-cols-3 gap-2 rounded-control bg-canvas px-3 py-2.5 text-center">
                <div>
                  <dt className="text-meta text-fg-muted">Calls</dt>
                  <dd className="font-mono text-ui font-semibold tabular-nums text-ink">
                    {(agent.stats?.totalCalls || 0).toLocaleString()}
                  </dd>
                </div>
                <div>
                  <dt className="text-meta text-fg-muted">Success</dt>
                  <dd className="font-mono text-ui font-semibold tabular-nums text-ink">{agent.stats?.successRate ?? 100}%</dd>
                </div>
                <div>
                  <dt className="text-meta text-fg-muted">Avg call</dt>
                  <dd className="font-mono text-ui font-semibold tabular-nums text-ink">{agent.stats?.avgDuration || '—'}</dd>
                </div>
              </dl>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 pt-3 border-t border-line">
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
                  className="p-2 rounded-control text-fg-body hover:text-ink hover:bg-canvas border border-transparent hover:border-line transition-all"
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
                  className="p-2 rounded-control text-fg-body hover:text-ink hover:bg-canvas border border-transparent hover:border-line transition-all"
                >
                  <Copy className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (confirm(`Delete ${agent.name}?`)) deleteAgent(agent.id);
                  }}
                  title="Delete"
                  className="p-2 rounded-control text-danger-fg hover:bg-danger-soft border border-transparent hover:border-danger-line transition-all"
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
