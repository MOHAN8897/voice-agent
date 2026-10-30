import React from 'react';
import { Bot, Check, Phone, PhoneCall } from 'lucide-react';
import { TactileButton } from '../../ui/TactileButton';

/**
 * First-run home: three steps instead of an empty feed. Each step is marked done
 * from real workspace data, so it disappears on its own once the tenant is live.
 */
export function GuidedStart({ agents, phoneNumbers, calls, onOpenCreateAgent, onOpenBuyNumber, onNavigate }) {
  const firstAgent = agents[0];
  const steps = [
    {
      id: 'agent',
      icon: Bot,
      title: 'Create your first AI employee',
      body: 'Describe the business and the job. You can change the script any time.',
      done: agents.length > 0,
      action: <TactileButton size="sm" variant="primary" onClick={onOpenCreateAgent} data-testid="guided-create-agent">Create agent</TactileButton>,
    },
    {
      id: 'number',
      icon: Phone,
      title: 'Get a phone number',
      body: 'Customers call this number to reach your agent, and it calls out from it.',
      done: phoneNumbers.length > 0,
      action: <TactileButton size="sm" variant={agents.length ? 'primary' : 'secondary'} onClick={onOpenBuyNumber} data-testid="guided-buy-number">Buy number</TactileButton>,
    },
    {
      id: 'test',
      icon: PhoneCall,
      title: 'Place a test call',
      body: 'Talk to your agent in the browser before customers do.',
      done: calls.length > 0,
      action: (
        <TactileButton
          size="sm"
          variant={agents.length ? 'primary' : 'secondary'}
          disabled={!firstAgent}
          onClick={() => onNavigate('employees', { agentId: firstAgent?.id, step: 'test' })}
          data-testid="guided-test-call"
        >
          Test your agent
        </TactileButton>
      ),
    },
  ];
  const remaining = steps.filter((s) => !s.done).length;

  return (
    <div className="rounded-card border border-line bg-surface p-5 sm:p-6 shadow-craft-xs" data-testid="home-guided-start">
      <h2 className="text-title text-ink">Get your first agent working</h2>
      <p className="mt-1 text-ui text-fg-muted">
        {remaining === 0 ? 'All set. Activity will appear here as your agents work.' : `${remaining} step${remaining === 1 ? '' : 's'} left. What your agents do will show up here as it happens.`}
      </p>
      <ol className="mt-5 space-y-3">
        {steps.map((step, index) => {
          const Icon = step.icon;
          return (
            <li key={step.id} className={`flex flex-col gap-3 rounded-control border p-4 sm:flex-row sm:items-center ${step.done ? 'border-success-line bg-success-soft' : 'border-line'}`}>
              <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${step.done ? 'bg-success text-white' : 'bg-surface-subtle text-fg-body'}`} aria-hidden="true">
                {step.done ? <Check className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-copy font-semibold text-ink">
                  <span className="sr-only">Step {index + 1}{step.done ? ', done' : ''}: </span>
                  {step.title}
                </p>
                <p className="text-ui text-fg-body">{step.body}</p>
              </div>
              {!step.done && <div className="shrink-0">{step.action}</div>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
