import React from 'react';
import { Phone, Volume2, Check } from 'lucide-react';
import { StepFooter } from './StepBrief';
import {
  AFTER_HOURS_OPTIONS,
  DEFAULT_BUSINESS_HOURS,
  WEEKDAYS,
  businessHoursSummary,
  countOpenDays,
  isBusinessHoursEmpty,
} from './index';

const VOICE_TONE = {
  warm: 'Warm & clear',
  bright: 'Bright & upbeat',
  calm: 'Calm & reassuring',
  formal: 'Formal & precise',
};

/**
 * Step 3 — Phone & voice.
 *
 * Voice is a brain-level setting (it changes how the agent speaks). Everything else
 * here is telephony: whether the line rings, when, and what the caller hears. These
 * are stored server-side and enforced by the live inbound path.
 */
export function StepConfigure({
  draft,
  onChange,
  onNext,
  onBack,
  onOpenBuyNumber,
  busy,
  error,
  voices = [],
  phoneNumbers = [],
  agents = [],
  walletBalanceInr = 0,
  selectedAgentId,
}) {
  const set = (patch) => onChange({ ...draft, ...patch });
  const profile = draft.telephony || {};
  const hours = profile.businessHours || {};
  const agentNumber = phoneNumbers.find(
    (n) => n.assignedAgentId === (draft.agentId || selectedAgentId)
  );

  const setHours = (day, windows) => {
    const next = { ...hours };
    if (!windows || windows.length === 0) delete next[day];
    else next[day] = windows;
    set({ telephony: { ...profile, businessHours: next }, telephonyDirty: true });
  };

  const setAllHours = (next) => {
    set({ telephony: { ...profile, businessHours: next }, telephonyDirty: true });
  };

  const toggleDay = (day) => {
    if (hours[day]?.length) {
      setHours(day, []);
    } else {
      setHours(day, DEFAULT_BUSINESS_HOURS[day] || [{ open: '09:00', close: '18:00' }]);
    }
  };

  const setWindow = (day, index, field, value) => {
    const windows = (hours[day] || []).map((w, i) =>
      i === index ? { ...w, [field]: value } : w
    );
    setHours(day, windows);
  };

  const needsTransferNumber = profile.afterHoursAction === 'transfer';

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-bold text-[#0F0E17]">How callers reach this agent</h3>
        <p className="text-[11px] text-[#524E5E] mt-0.5">
          These settings take effect on the next inbound call. The agent is already published, so
          you can test it now and change any of this later.
        </p>
      </div>

      {/* Voice */}
      <section className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-3">
        <div className="flex items-center gap-1.5 text-xs font-bold text-[#0F0E17]">
          <Volume2 className="w-3.5 h-3.5 text-[#6344E7]" />
          <span>Voice</span>
        </div>
        <div className="grid sm:grid-cols-2 gap-3">
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A]">
              Voice
            </span>
            <select
              value={profile.voiceId || ''}
              onChange={(e) => set({ voiceId: e.target.value, voiceDirty: true })}
              data-testid="config-voice"
              className="mt-1 w-full bg-white border border-[#E4E2EB] rounded-xl px-2.5 py-2 text-xs"
            >
              {voices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.label}
                </option>
              ))}
            </select>
            {voices.find((v) => v.id === profile.voiceId)?.tone && (
              <span className="text-[10px] text-[#8C879A] mt-1 block">
                {VOICE_TONE[voices.find((v) => v.id === profile.voiceId).tone] ||
                  voices.find((v) => v.id === profile.voiceId).tone}
              </span>
            )}
          </label>
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A]">
              Speaking speed
            </span>
            <input
              type="range"
              min="0.5"
              max="1.5"
              step="0.05"
              value={profile.speed ?? 1}
              onChange={(e) => set({ speed: Number(e.target.value), voiceDirty: true })}
              data-testid="config-voice-speed"
              className="mt-2 w-full accent-[#6344E7]"
            />
            <span className="text-[10px] font-mono text-[#524E5E]">
              {Number(profile.speed ?? 1).toFixed(2)}×
            </span>
          </label>
        </div>
      </section>

      {/* Phone line */}
      <section className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 text-xs font-bold text-[#0F0E17]">
            <Phone className="w-3.5 h-3.5 text-[#6344E7]" />
            <span>Phone line</span>
          </div>
          {onOpenBuyNumber && (
            <button
              type="button"
              onClick={onOpenBuyNumber}
              data-testid="config-buy-number"
              className="text-[11px] font-semibold text-[#5034CE] hover:underline"
            >
              Buy a number
            </button>
          )}
        </div>

        {agentNumber ? (
          <div className="flex items-center gap-2 text-xs">
            <Check className="w-3.5 h-3.5 text-[#047857]" />
            <span className="font-mono font-semibold text-[#0F0E17]">{agentNumber.number}</span>
            <span className="text-[#524E5E]">assigned to this agent</span>
          </div>
        ) : (
          <p className="text-[11px] text-[#524E5E]">
            No number yet. The agent works for browser test calls, and you can also place outgoing
            calls by entering a number. Buy a number when you want inbound callers.
          </p>
        )}

        {walletBalanceInr <= 0 && (
          <p className="text-[10px] text-[#B45309]">
            Your wallet is empty. Outgoing calls and buying numbers need credits.
          </p>
        )}
      </section>

      {/* Inbound availability */}
      <section className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-xs font-bold text-[#0F0E17]">Accept incoming calls</div>
            <div className="text-[10px] text-[#8C879A] mt-0.5">
              When off, this number does not ring for inbound calls.
            </div>
          </div>
          <input
            type="checkbox"
            checked={profile.inboundEnabled !== false}
            onChange={(e) => set({ telephony: { ...profile, inboundEnabled: e.target.checked }, telephonyDirty: true })}
            data-testid="config-inbound-enabled"
            className="w-4 h-4 accent-[#6344E7]"
          />
        </div>

        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-xs font-bold text-[#0F0E17]">Allow outgoing calls</div>
            <div className="text-[10px] text-[#8C879A] mt-0.5">
              When off, this agent cannot place or receive callback calls.
            </div>
          </div>
          <input
            type="checkbox"
            checked={profile.outboundEnabled !== false}
            onChange={(e) => set({ telephony: { ...profile, outboundEnabled: e.target.checked }, telephonyDirty: true })}
            data-testid="config-outbound-enabled"
            className="w-4 h-4 accent-[#6344E7]"
          />
        </div>
      </section>

      {/* Business hours */}
      <section className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-3">
        <div>
          <div className="text-xs font-bold text-[#0F0E17]">Business hours</div>
          <div className="text-[10px] text-[#8C879A] mt-0.5" data-testid="config-hours-summary">
            {businessHoursSummary(hours)}
            {countOpenDays(hours) > 0 && ' · times are in Asia/Kolkata'}
          </div>
        </div>

        <div className="space-y-1.5">
          {WEEKDAYS.map((day) => {
            const windows = hours[day.id] || [];
            const isOpen = windows.length > 0;
            return (
              <div key={day.id} className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => toggleDay(day.id)}
                  data-testid={`config-day-${day.id}`}
                  aria-pressed={isOpen}
                  className={`w-11 shrink-0 px-2 py-1.5 rounded-lg text-[11px] font-bold border transition-colors ${
                    isOpen
                      ? 'bg-[#0F0E17] text-white border-[#0F0E17]'
                      : 'bg-white text-[#8C879A] border-[#E4E2EB]'
                  }`}
                >
                  {day.label}
                </button>
                {isOpen ? (
                  <div className="flex items-center gap-1.5">
                    {windows.map((w, i) => (
                      <div key={i} className="flex items-center gap-1">
                        <input
                          type="time"
                          value={w.open}
                          onChange={(e) => setWindow(day.id, i, 'open', e.target.value)}
                          data-testid={`config-hours-${day.id}-open`}
                          className="bg-white border border-[#E4E2EB] rounded-lg px-1.5 py-1 text-[11px] font-mono"
                        />
                        <span className="text-[10px] text-[#8C879A]">to</span>
                        <input
                          type="time"
                          value={w.close}
                          onChange={(e) => setWindow(day.id, i, 'close', e.target.value)}
                          data-testid={`config-hours-${day.id}-close`}
                          className="bg-white border border-[#E4E2EB] rounded-lg px-1.5 py-1 text-[11px] font-mono"
                        />
                      </div>
                    ))}
                  </div>
                ) : (
                  <span className="text-[10px] text-[#A9A5B4]">Closed</span>
                )}
              </div>
            );
          })}
        </div>

        <button
          type="button"
          onClick={() => setAllHours(isBusinessHoursEmpty(hours) ? DEFAULT_BUSINESS_HOURS : {})}
          data-testid="config-hours-toggle-all"
          className="text-[11px] font-semibold text-[#5034CE] hover:underline"
        >
          {isBusinessHoursEmpty(hours)
            ? 'Set standard business hours'
            : 'Clear hours (always open)'}
        </button>
      </section>

      {/* After hours */}
      <section className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-3">
        <div>
          <div className="text-xs font-bold text-[#0F0E17]">Outside business hours</div>
          <div className="text-[10px] text-[#8C879A] mt-0.5">
            What happens when a caller rings outside the hours above.
          </div>
        </div>
        <div className="grid sm:grid-cols-2 gap-2">
          {AFTER_HOURS_OPTIONS.map((opt) => {
            const active = (profile.afterHoursAction || 'voicemail') === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                data-testid={`config-after-hours-${opt.id}`}
                aria-pressed={active}
                onClick={() => set({ telephony: { ...profile, afterHoursAction: opt.id }, telephonyDirty: true })}
                className={`px-3 py-2 rounded-xl text-left border transition-all ${
                  active
                    ? 'bg-[#0F0E17] text-white border-[#0F0E17]'
                    : 'bg-white text-[#524E5E] border-[#E4E2EB] hover:border-[#6344E7]/40'
                }`}
              >
                <span className="block text-xs font-bold">{opt.label}</span>
                <span
                  className={`block text-[10px] mt-0.5 ${active ? 'text-white/70' : 'text-[#8C879A]'}`}
                >
                  {opt.description}
                </span>
              </button>
            );
          })}
        </div>

        {needsTransferNumber && (
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A]">
              Transfer to
            </span>
            <input
              type="text"
              value={profile.transferNumber || ''}
              onChange={(e) => set({ telephony: { ...profile, transferNumber: e.target.value }, telephonyDirty: true })}
              placeholder="+919999999999"
              data-testid="config-transfer-number"
              className="mt-1 w-full bg-white border border-[#E4E2EB] rounded-xl px-2.5 py-2 text-xs font-mono"
            />
          </label>
        )}
      </section>

      {/* Greeting */}
      <section className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-2">
        <label htmlFor="config-greeting" className="block text-xs font-bold text-[#0F0E17]">
          Greeting the caller hears
        </label>
        <p className="text-[10px] text-[#8C879A]">
          Leave blank to use the opening line from the agent's script.
        </p>
        <textarea
          id="config-greeting"
          value={profile.greetingPhrase || ''}
          onChange={(e) => set({ telephony: { ...profile, greetingPhrase: e.target.value }, telephonyDirty: true })}
          rows={2}
          maxLength={500}
          placeholder="Thanks for calling Sai Constructions, this is Priya speaking."
          data-testid="config-greeting"
          className="w-full rounded-xl bg-white border border-[#E4E2EB] px-3 py-2 text-xs text-[#0F0E17] placeholder:text-[#8C879A] focus:outline-none focus:border-[#6344E7] resize-none"
        />
      </section>

      {error && (
        <div
          data-testid="employee-create-error"
          className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900"
          role="alert"
        >
          {error}
        </div>
      )}

      <StepFooter
        onBack={onBack}
        onNext={onNext}
        nextLabel="Save and test"
        busy={busy}
        busyLabel="Saving…"
      />
    </div>
  );
}
