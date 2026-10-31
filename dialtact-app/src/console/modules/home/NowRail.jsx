import React from 'react';
import { ChevronRight, FileCode2, Phone, Play, Plus, Wallet } from 'lucide-react';
import { Avatar } from '../../ui/Avatar';
import { Section } from '../../ui/SolidCard';
import { StatusBadge } from '../../ui/StatusBadge';
import { TactileButton } from '../../ui/TactileButton';
import { formatClock, walletAmounts } from '../../../lib/money';
import { AnimatedCount } from './AnimatedCount';

function Stat({ label, value, onClick }) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick || undefined}
      className={`rounded-control bg-canvas px-3 py-2.5 text-left ${onClick ? 'hover:bg-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent' : ''}`}
    >
      <div className="text-meta text-fg-muted">{label}</div>
      <div className="mt-0.5 text-title font-mono tabular-nums text-ink">{value}</div>
    </Tag>
  );
}

/** Compact strip for phones: the four numbers that matter, above the feed. */
export function SummaryStrip({ live, wallet, needsActionCount, onShowNeeds, onShowCalls, onTopUp }) {
  const money = walletAmounts(wallet);
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:hidden" data-testid="home-summary-strip">
      <Stat label="On calls now" value={<AnimatedCount value={live.calls.length} />} onClick={onShowCalls} />
      <Stat label="Needs you" value={<AnimatedCount value={needsActionCount} />} onClick={onShowNeeds} />
      <Stat label="Calls today" value={live.today?.calls ?? '—'} />
      <Stat label="Wallet" value={money.primary} onClick={onTopUp} />
    </div>
  );
}

/**
 * The right rail: who is on a call right now (with live timers), today's numbers,
 * the wallet with Add funds, what needs action, the team with Test/Build, and the
 * two setup actions (Create agent, Buy number).
 */
export function NowRail({
  live,
  now,
  agents,
  wallet,
  needsActionCount,
  onShowNeeds,
  onOpenCall,
  onTopUp,
  onNavigate,
  onOpenCreateAgent,
  onOpenBuyNumber,
}) {
  const money = walletAmounts(wallet);
  const today = live.today;
  const lowWallet = money.isEmpty || money.inr < 200;
  const talkMinutes = today ? Math.round((today.talkSeconds || 0) / 60) : null;

  return (
    <div className="space-y-4" data-testid="home-now-rail">
      <Section
        padding="p-4"
        headingLevel={2}
        title="On calls now"
        description={live.ringing ? `${live.ringing} ringing` : null}
        actions={live.calls.length > 0 ? <StatusBadge status="live" label={`${live.calls.length} live`} tone="live" size="xs" /> : null}
      >
        {live.calls.length === 0 ? (
          <p className="text-ui text-fg-muted">{live.error ? 'Live status is unavailable right now.' : 'No one is on a call right now.'}</p>
        ) : (
          <ul className="space-y-2">
            {live.calls.map((call) => {
              const elapsed = call.startedAt ? (now - new Date(call.startedAt).getTime()) / 1000 : 0;
              const name = call.agentName || agents.find((a) => a.id === call.agentId)?.name || 'Agent';
              const who = call.contact?.name || call.contact?.phone || 'a caller';
              return (
                <li key={call.callId}>
                  <button
                    type="button"
                    onClick={() => onOpenCall(call.callId)}
                    className="flex w-full items-center gap-3 rounded-control p-2 text-left hover:bg-canvas focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                    aria-label={`${name} is on a call with ${who}, ${formatClock(elapsed)}. Open live transcript`}
                  >
                    <Avatar name={name} size="sm" live />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-ui font-medium text-ink">{name}</span>
                      <span className="block truncate text-meta text-fg-muted">
                        {call.direction === 'outbound' ? 'Calling' : 'With'} {who}
                      </span>
                    </span>
                    <span className="font-mono text-ui tabular-nums text-success-fg">{formatClock(elapsed)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      <Section padding="p-4" headingLevel={2} title="Today">
        <div className="grid grid-cols-2 gap-2">
          <Stat label="Calls" value={today?.calls ?? '—'} onClick={() => onNavigate('calls')} />
          <Stat label="Answered" value={today?.answered ?? '—'} />
          <Stat label="Talk time" value={talkMinutes == null ? '—' : `${talkMinutes} min`} />
          <Stat label="New leads" value={today?.leads ?? '—'} onClick={() => onNavigate('leads')} />
        </div>
        {today?.bookings > 0 && (
          <p className="mt-2 text-meta text-fg-muted">{today.bookings} site visit{today.bookings === 1 ? '' : 's'} booked</p>
        )}
      </Section>

      <Section padding="p-4" headingLevel={2} title="Wallet">
        <div className="flex items-end justify-between gap-3">
          <div>
            <div className={`text-heading font-mono tabular-nums ${money.isEmpty ? 'text-danger-fg' : 'text-ink'}`} data-testid="home-wallet-inr">
              {money.primary}
            </div>
            <div className="text-meta text-fg-muted">
              {money.secondary} · about {Number(wallet?.remainingMinutes || 0).toLocaleString('en-IN')} min of calls
            </div>
          </div>
          <TactileButton size="sm" variant={lowWallet ? 'primary' : 'secondary'} icon={Wallet} onClick={onTopUp}>
            Add funds
          </TactileButton>
        </div>
        {money.isEmpty && <p className="mt-2 text-meta text-danger-fg">Calls can't be placed until you add funds.</p>}
        {!money.isEmpty && lowWallet && <p className="mt-2 text-meta text-warning-fg">Running low. Add funds to keep agents calling.</p>}
      </Section>

      <button
        type="button"
        onClick={onShowNeeds}
        className={`flex w-full items-center justify-between rounded-card border p-4 text-left shadow-craft-xs transition-[background-color,border-color,transform] duration-200 ease-out active:scale-[0.99] motion-reduce:active:scale-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
          needsActionCount > 0 ? 'border-warning-line bg-warning-soft' : 'border-line bg-surface'
        }`}
        data-testid="home-needs-action"
      >
        <span>
          <span className="block text-title text-ink">
            {needsActionCount > 0 ? (
              <>
                <AnimatedCount value={needsActionCount} /> need{needsActionCount === 1 ? 's' : ''} you
              </>
            ) : (
              'Nothing needs you'
            )}
          </span>
          <span className="block text-ui text-fg-body">Callbacks, approvals and account issues</span>
        </span>
        <ChevronRight className="h-5 w-5 text-fg-body" />
      </button>

      <Section
        padding="p-4"
        headingLevel={2}
        title="Your team"
        actions={
          <button type="button" onClick={() => onNavigate('employees')} className="inline-flex items-center gap-1 text-ui font-medium text-accent-fg hover:underline">
            View all <ChevronRight className="h-4 w-4" />
          </button>
        }
      >
        {agents.length === 0 ? (
          <p className="text-ui text-fg-muted">No agents yet.</p>
        ) : (
          <ul className="divide-y divide-line">
            {agents.slice(0, 5).map((agent) => {
              const onCall = live.calls.some((c) => c.agentId === agent.id);
              return (
                <li key={agent.id} className="py-2.5 first:pt-0 last:pb-0">
                  <div className="flex items-center gap-3">
                    <Avatar name={agent.name} size="sm" live={onCall} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-ui font-medium text-ink">{agent.name}</div>
                      <div className="truncate text-meta text-fg-muted">
                        {onCall ? 'On a call' : agent.role || 'AI employee'} · {agent.assignedNumber || 'No number'}
                      </div>
                    </div>
                    <StatusBadge status={agent.status} size="xs" />
                  </div>
                  <div className="mt-1.5 flex gap-3 pl-11">
                    <button
                      type="button"
                      onClick={() => onNavigate('employees', { agentId: agent.id, step: 'test' })}
                      className="inline-flex items-center gap-1 text-ui font-medium text-accent-fg hover:underline"
                    >
                      <Play className="h-3.5 w-3.5" /> Test
                    </button>
                    <button
                      type="button"
                      onClick={() => onNavigate('employees', { agentId: agent.id, step: 'script' })}
                      className="inline-flex items-center gap-1 text-ui font-medium text-fg-body hover:text-ink hover:underline"
                    >
                      <FileCode2 className="h-3.5 w-3.5" /> Build
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        <div className="mt-4 grid grid-cols-2 gap-2">
          <TactileButton size="sm" variant="secondary" icon={Phone} onClick={onOpenBuyNumber} data-testid="rail-buy-number-btn">
            Buy number
          </TactileButton>
          <TactileButton size="sm" variant="secondary" icon={Plus} onClick={onOpenCreateAgent} data-testid="rail-create-agent-btn">
            New agent
          </TactileButton>
        </div>
      </Section>
    </div>
  );
}

