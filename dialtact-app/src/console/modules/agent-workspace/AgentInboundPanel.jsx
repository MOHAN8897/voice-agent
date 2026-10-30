import React, { useEffect, useState } from 'react';
import {
  PhoneIncoming,
  PhoneCall,
  Clock,
  Settings,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Phone,
  Volume2
} from 'lucide-react';
import { SolidCard } from '../../ui/SolidCard';
import { StatusBadge } from '../../ui/StatusBadge';
import { TactileButton } from '../../ui/TactileButton';
import { useWorkspace } from '../../context/WorkspaceContext';
import { api } from '../../../services/api';
import { businessHoursSummary } from '../agent-creation';

/**
 * AgentInboundPanel
 * Dedicated inbound channel dashboard for an AI voice employee.
 * Displays assigned line, reception status, live business hours rule, and test call trigger.
 */
export function AgentInboundPanel({ agentId, agentName, onNavigateToSettings }) {
  const { phoneNumbers, openTestCall } = useWorkspace();
  const [profile, setProfile] = useState(null);
  const [decision, setDecision] = useState(null);
  const [loading, setLoading] = useState(true);

  // Find assigned number for this agent
  const assigned = phoneNumbers.find((n) => n.assignedAgentId === agentId);

  useEffect(() => {
    let active = true;
    if (!agentId) return;

    setLoading(true);
    const loadProfile = async () => {
      try {
        let data = null;
        if (typeof api.telephony?.getAgentProfile === 'function') {
          data = await api.telephony.getAgentProfile(agentId);
        } else if (typeof api.agents?.getTelephonyProfile === 'function') {
          const [prof, eff] = await Promise.all([
            api.agents.getTelephonyProfile(agentId).catch(() => ({ profile: {} })),
            typeof api.agents?.getEffectiveTelephony === 'function'
              ? api.agents.getEffectiveTelephony(agentId).catch(() => null)
              : Promise.resolve(null),
          ]);
          data = {
            profile: prof?.profile || {},
            decision: eff?.decision || null,
          };
        }
        if (!active) return;
        setProfile(data?.profile || {});
        setDecision(data?.decision || null);
      } catch (err) {
        console.warn('Could not load agent telephony profile:', err);
        if (active) {
          setProfile({});
          setDecision(null);
        }
      } finally {
        if (active) setLoading(false);
      }
    };

    loadProfile();

    return () => {
      active = false;
    };
  }, [agentId]);

  const isInboundEnabled = profile?.inboundEnabled !== false;
  const hoursText = businessHoursSummary(profile?.businessHours, profile?.timezone || 'America/New_York');

  return (
    <div className="space-y-5" data-testid="agent-inbound-panel">
      {/* Hero Summary Card */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 min-w-0">
        {/* Assigned Line Card */}
        <SolidCard padding="p-5" className="space-y-3 min-w-0">
          <div className="flex items-center justify-between">
            <span className="text-ui font-medium text-fg-body">
              Assigned phone line
            </span>
            <div className="w-8 h-8 rounded-control bg-accent-soft text-accent flex items-center justify-center">
              <PhoneIncoming className="w-4 h-4" />
            </div>
          </div>
          {assigned ? (
            <div>
              <div className="text-heading font-mono tabular-nums text-ink truncate" title={assigned.number}>
                {assigned.number}
              </div>
              <div className="flex items-center gap-2 mt-1">
                <StatusBadge status={isInboundEnabled ? 'active' : 'paused'} size="xs" />
                <span className="text-meta text-fg-body">
                  {isInboundEnabled ? 'Taking incoming calls' : 'Incoming calls paused'}
                </span>
              </div>
            </div>
          ) : (
            <div>
              <div className="text-copy font-semibold text-fg-muted">
                No phone number assigned
              </div>
              <p className="text-meta text-fg-body mt-1">
                Callers can’t reach this employee by phone until you give them a number.
              </p>
              {onNavigateToSettings && (
                <button
                  type="button"
                  onClick={onNavigateToSettings}
                  className="mt-2 text-ui font-semibold text-accent hover:underline inline-flex items-center gap-1"
                >
                  Assign a number in settings <ArrowRight className="w-3 h-3" />
                </button>
              )}
            </div>
          )}
        </SolidCard>

        {/* Live Operating Status */}
        <SolidCard padding="p-5" className="space-y-3 min-w-0">
          <div className="flex items-center justify-between">
            <span className="text-ui font-medium text-fg-body">
              Answering right now
            </span>
            <div className="w-8 h-8 rounded-control bg-accent-soft text-accent flex items-center justify-center">
              <Clock className="w-4 h-4" />
            </div>
          </div>
          <div>
            <div className="text-title text-ink">
              {decision?.afterHours ? 'Outside business hours' : 'Open and taking calls'}
            </div>
            <p className="text-meta text-fg-body mt-1 line-clamp-2">
              {decision?.reason === 'in_hours' && 'The employee answers callers directly.'}
              {decision?.reason === 'after_hours_voicemail' && 'Outside hours, callers can leave a voicemail.'}
              {decision?.reason === 'after_hours_transfer' && `Outside hours, calls go to ${profile?.transferNumber || 'your team'}.`}
              {decision?.reason === 'after_hours_hangup' && 'Outside hours, the line is closed.'}
              {(!decision || decision?.reason === 'no_hours_configured') && 'Open all day, every day: the employee answers every incoming call.'}
            </p>
          </div>
          <div className="text-meta text-fg-muted">
            Timezone: {profile?.timezone || 'America/New_York'}
          </div>
        </SolidCard>

        {/* Quick Inbound Test */}
        <SolidCard padding="p-5" className="space-y-3 min-w-0 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-ui font-medium text-fg-body">
              Try it yourself
            </span>
            <div className="w-8 h-8 rounded-control bg-success-soft text-success-fg flex items-center justify-center">
              <PhoneCall className="w-4 h-4" />
            </div>
          </div>
          <p className="text-meta text-fg-body">
            Call your employee from this browser to hear the greeting and how they answer.
          </p>
          <TactileButton
            variant="primary"
            size="sm"
            icon={PhoneCall}
            onClick={() => openTestCall?.(agentId)}
            className="w-full justify-center !py-2"
          >
            Test incoming call
          </TactileButton>
        </SolidCard>
      </div>

      {/* Inbound Call Configuration & Rules Overview */}
      <SolidCard className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-line pb-3">
          <div>
            <h3 className="text-title text-ink">Incoming call rules</h3>
            <p className="text-ui text-fg-body mt-0.5">
              When this employee answers, and what happens to calls outside those hours.
            </p>
          </div>
          {onNavigateToSettings && (
            <TactileButton
              variant="secondary"
              size="sm"
              icon={Settings}
              onClick={onNavigateToSettings}
            >
              Edit in settings
            </TactileButton>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-ui">
          <div className="p-3.5 rounded-control bg-canvas border border-line space-y-1.5">
            <div className="font-semibold text-ink flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-accent" />
              Business hours
            </div>
            <p className="text-ui text-fg-body">
              {hoursText || 'Always open (24 hours a day, 7 days a week)'}
            </p>
          </div>

          <div className="p-3.5 rounded-control bg-canvas border border-line space-y-1.5">
            <div className="font-semibold text-ink flex items-center gap-1.5">
              <Phone className="w-3.5 h-3.5 text-accent" />
              Outside business hours
            </div>
            <p className="text-ui text-fg-body">
              {profile?.afterHoursAction === 'transfer'
                ? `Transfer to ${profile?.transferNumber || 'a number you haven’t set yet'}`
                : profile?.afterHoursAction === 'voicemail'
                ? 'Take a voicemail'
                : 'Say goodbye and hang up'}
            </p>
          </div>
        </div>

        {decision?.greetingPhrase && (
          <div className="p-3.5 rounded-control bg-warning-soft border border-warning-line text-ui text-fg-body space-y-1">
            <span className="font-semibold text-ink flex items-center gap-1.5">
              <Volume2 className="w-3.5 h-3.5 text-warning" />
              What callers hear outside hours
            </span>
            <p className="italic text-ink text-ui">
              &ldquo;{decision.greetingPhrase}&rdquo;
            </p>
          </div>
        )}
      </SolidCard>
    </div>
  );
}
