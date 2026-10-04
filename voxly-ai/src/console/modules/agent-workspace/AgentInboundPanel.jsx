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
    api.telephony
      .getAgentProfile(agentId)
      .then((data) => {
        if (!active) return;
        setProfile(data.profile || {});
        setDecision(data.decision || null);
      })
      .catch(() => {
        if (!active) return;
        setProfile({});
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [agentId]);

  const isInboundEnabled = profile?.inboundEnabled !== false;
  const hoursText = businessHoursSummary(profile?.businessHours, profile?.timezone || 'America/New_York');

  return (
    <div className="space-y-5" data-testid="agent-inbound-panel">
      {/* Hero Summary Card */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Assigned Line Card */}
        <SolidCard className="space-y-3 p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-[#524E5E] uppercase tracking-wider">
              Assigned Phone Line
            </span>
            <div className="w-8 h-8 rounded-lg bg-[#FF5C35]/10 text-[#FF5C35] flex items-center justify-center">
              <PhoneIncoming className="w-4 h-4" />
            </div>
          </div>
          {assigned ? (
            <div>
              <div className="text-lg font-bold font-mono text-[#0F0E17]">
                {assigned.number}
              </div>
              <div className="flex items-center gap-2 mt-1">
                <StatusBadge status={isInboundEnabled ? 'active' : 'paused'} size="xs" />
                <span className="text-[11px] text-[#524E5E]">
                  {isInboundEnabled ? 'Live for inbound calls' : 'Inbound calls paused'}
                </span>
              </div>
            </div>
          ) : (
            <div>
              <div className="text-sm font-semibold text-[#8C879A]">
                No phone number assigned
              </div>
              <p className="text-[11px] text-[#524E5E] mt-1">
                Callers cannot reach this agent via phone until a number is linked.
              </p>
              {onNavigateToSettings && (
                <button
                  type="button"
                  onClick={onNavigateToSettings}
                  className="mt-2 text-xs font-semibold text-[#FF5C35] hover:underline inline-flex items-center gap-1"
                >
                  Assign number in Settings <ArrowRight className="w-3 h-3" />
                </button>
              )}
            </div>
          )}
        </SolidCard>

        {/* Live Operating Status */}
        <SolidCard className="space-y-3 p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-[#524E5E] uppercase tracking-wider">
              Reception Status
            </span>
            <div className="w-8 h-8 rounded-lg bg-[#6344E7]/10 text-[#6344E7] flex items-center justify-center">
              <Clock className="w-4 h-4" />
            </div>
          </div>
          <div>
            <div className="text-sm font-bold text-[#0F0E17]">
              {decision?.afterHours ? 'Outside Business Hours' : 'Open / Accepting Calls'}
            </div>
            <p className="text-[11px] text-[#524E5E] mt-1 line-clamp-2">
              {decision?.reason === 'in_hours' && 'Agent will answer caller inquiries directly.'}
              {decision?.reason === 'after_hours_voicemail' && 'Outside hours: routed to agent voicemail.'}
              {decision?.reason === 'after_hours_transfer' && `Outside hours: transfers to ${profile?.transferNumber || 'team'}.`}
              {decision?.reason === 'after_hours_hangup' && 'Outside hours: line is closed.'}
              {(!decision || decision?.reason === 'no_hours_configured') && '24/7 reception: agent answers all incoming calls.'}
            </p>
          </div>
          <div className="text-[10px] text-[#8C879A] font-mono">
            {profile?.timezone || 'America/New_York'}
          </div>
        </SolidCard>

        {/* Quick Inbound Test */}
        <SolidCard className="space-y-3 p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-[#524E5E] uppercase tracking-wider">
              Verify Voice Line
            </span>
            <div className="w-8 h-8 rounded-lg bg-[#16A34A]/10 text-[#16A34A] flex items-center justify-center">
              <PhoneCall className="w-4 h-4" />
            </div>
          </div>
          <p className="text-[11px] text-[#524E5E]">
            Simulate a real incoming caller in your browser to hear the opening greeting and response rules.
          </p>
          <TactileButton
            variant="primary"
            size="sm"
            icon={PhoneCall}
            onClick={() => openTestCall?.(agentId)}
            className="w-full justify-center !py-2"
          >
            Test Inbound Call
          </TactileButton>
        </SolidCard>
      </div>

      {/* Inbound Call Configuration & Rules Overview */}
      <SolidCard className="space-y-4">
        <div className="flex items-center justify-between border-b border-[#E4E2EB] pb-3">
          <div>
            <h3 className="text-sm font-bold text-[#0F0E17]">Inbound Call Rules</h3>
            <p className="text-xs text-[#524E5E] mt-0.5">
              Operating schedule and automated routing enforced when customers dial this agent.
            </p>
          </div>
          {onNavigateToSettings && (
            <TactileButton
              variant="secondary"
              size="sm"
              icon={Settings}
              onClick={onNavigateToSettings}
            >
              Edit in Settings
            </TactileButton>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-1.5">
            <div className="font-semibold text-[#0F0E17] flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-[#FF5C35]" />
              Operating Hours Schedule
            </div>
            <p className="text-[11px] text-[#524E5E]">
              {hoursText || 'Always Available (24 hours a day, 7 days a week)'}
            </p>
          </div>

          <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-1.5">
            <div className="font-semibold text-[#0F0E17] flex items-center gap-1.5">
              <Phone className="w-3.5 h-3.5 text-[#6344E7]" />
              Outside-Hours Fallback
            </div>
            <p className="text-[11px] text-[#524E5E] capitalize">
              {profile?.afterHoursAction === 'transfer'
                ? `Transfer to ${profile?.transferNumber || 'Unconfigured'}`
                : profile?.afterHoursAction === 'voicemail'
                ? 'Record Voicemail Message'
                : 'Polite Hangup'}
            </p>
          </div>
        </div>

        {decision?.greetingPhrase && (
          <div className="p-3.5 rounded-xl bg-amber-500/5 border border-amber-500/20 text-xs text-[#524E5E] space-y-1">
            <span className="font-semibold text-[#0F0E17] flex items-center gap-1.5">
              <Volume2 className="w-3.5 h-3.5 text-amber-600" />
              After-Hours Spoken Notice
            </span>
            <p className="italic text-[#0F0E17] text-[11px]">
              &ldquo;{decision.greetingPhrase}&rdquo;
            </p>
          </div>
        )}
      </SolidCard>
    </div>
  );
}
