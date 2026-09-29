import React from 'react';
import { Check, PhoneCall, Mic, Settings2, ArrowRight } from 'lucide-react';
import { StepFooter } from './StepBrief';
import { businessHoursSummary } from './index';

const DIRECTION_LABEL = {
  inbound: 'Incoming calls',
  outbound: 'Outgoing calls',
  both: 'Incoming and outgoing calls',
};

/**
 * Step 4 — Ready.
 *
 * Confirms what was built, in plain language, and offers the two things a user
 * actually wants next: test it, or open the full agent editor.
 */
export function StepReady({
  draft,
  onBack,
  onTestCall,
  onOpenStudio,
  onOpenCalls,
  onOpenBuyNumber,
  onFinish,
  busy,
}) {
  const profile = draft.telephony || {};
  const callsHandled = [...new Set([draft.direction].filter(Boolean))];
  const directionLabel =
    callsHandled.length > 1
      ? DIRECTION_LABEL.both
      : DIRECTION_LABEL[callsHandled[0]] || 'Calls';

  return (
    <div className="space-y-5">
      <div className="text-center py-2">
        <div className="inline-flex items-center justify-center w-11 h-11 rounded-full bg-[#ECFDF5] border border-[#A7F3D0]">
          <Check className="w-5 h-5 text-[#047857]" />
        </div>
        <h3 className="text-sm font-bold text-[#0F0E17] mt-2.5">
          {draft.agentName || 'Your agent'} is live
        </h3>
        <p className="text-[11px] text-[#524E5E] mt-0.5 max-w-md mx-auto">
          Its script is published and it is ready to take calls. Test it now, or change anything
          later in the agent editor.
        </p>
      </div>

      {/* Plain-language summary of what was configured. */}
      <dl className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] divide-y divide-[#E4E2EB] text-xs">
        {[
          {
            label: 'Language',
            value: draft.language,
            mono: true,
          },
          {
            label: 'Role',
            value: String(draft.role || '').replace(/_/g, ' '),
          },
          {
            label: 'Takes',
            value: directionLabel,
          },
          {
            label: 'Incoming calls',
            value: profile.inboundEnabled === false ? 'Off' : 'On',
          },
          {
            label: 'Outgoing calls',
            value: profile.outboundEnabled === false ? 'Off' : 'On',
          },
          {
            label: 'Business hours',
            value: businessHoursSummary(profile.businessHours || {}),
          },
          {
            label: 'Outside hours',
            value:
              (profile.afterHoursAction || 'voicemail') === 'always'
                ? 'Still answers'
                : (profile.afterHoursAction || 'voicemail') === 'hangup'
                  ? 'Does not answer'
                  : (profile.afterHoursAction || 'voicemail') === 'transfer'
                    ? 'Transfers the call'
                    : 'Takes a voicemail',
          },
        ].map((row) => (
          <div key={row.label} className="flex items-center justify-between gap-4 py-2">
            <dt className="text-[#8C879A]">{row.label}</dt>
            <dd
              className={`font-semibold text-[#0F0E17] text-right ${row.mono ? 'font-mono' : ''}`}
            >
              {row.value}
            </dd>
          </div>
        ))}
      </dl>

      <div className="grid sm:grid-cols-2 gap-2">
        <button
          type="button"
          onClick={onTestCall}
          data-testid="ready-test-call"
          className="flex items-center gap-2 px-3.5 py-3 rounded-xl bg-[#0F0E17] text-white text-left hover:bg-[#1a1826] transition-colors"
        >
          <Mic className="w-4 h-4 shrink-0" />
          <span>
            <span className="block text-xs font-bold">Test with a call</span>
            <span className="block text-[10px] text-white/70">Talk to it like a real caller</span>
          </span>
        </button>
        <button
          type="button"
          onClick={onOpenCalls}
          data-testid="ready-place-call"
          className="flex items-center gap-2 px-3.5 py-3 rounded-xl bg-white border border-[#E4E2EB] text-left hover:border-[#6344E7]/40 transition-colors"
        >
          <PhoneCall className="w-4 h-4 shrink-0 text-[#6344E7]" />
          <span>
            <span className="block text-xs font-bold text-[#0F0E17]">Place a call</span>
            <span className="block text-[10px] text-[#8C879A]">Call a real number now</span>
          </span>
        </button>
        <button
          type="button"
          onClick={onOpenStudio}
          data-testid="ready-open-studio"
          className="flex items-center gap-2 px-3.5 py-3 rounded-xl bg-white border border-[#E4E2EB] text-left hover:border-[#6344E7]/40 transition-colors"
        >
          <Settings2 className="w-4 h-4 shrink-0 text-[#6344E7]" />
          <span>
            <span className="block text-xs font-bold text-[#0F0E17]">Edit the script</span>
            <span className="block text-[10px] text-[#8C879A]">Fine-tune behaviour and voice</span>
          </span>
        </button>
        {onOpenBuyNumber && (
          <button
            type="button"
            onClick={onOpenBuyNumber}
            data-testid="ready-buy-number"
            className="flex items-center gap-2 px-3.5 py-3 rounded-xl bg-white border border-[#E4E2EB] text-left hover:border-[#6344E7]/40 transition-colors"
          >
            <PhoneCall className="w-4 h-4 shrink-0 text-[#6344E7]" />
            <span>
              <span className="block text-xs font-bold text-[#0F0E17]">Get a phone number</span>
              <span className="block text-[10px] text-[#8C879A]">So customers can call in</span>
            </span>
          </button>
        )}
      </div>

      <StepFooter
        onBack={onBack}
        onNext={onFinish}
        nextLabel="Done"
        backLabel="Back to settings"
        busy={busy}
      />

      <p className="text-[10px] text-center text-[#8C879A] flex items-center justify-center gap-1">
        You are only charged for calls the agent actually makes
        <ArrowRight className="w-3 h-3" />
      </p>
    </div>
  );
}
