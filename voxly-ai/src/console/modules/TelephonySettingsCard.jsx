import React, { useCallback, useEffect, useState } from 'react';
import { Phone, RefreshCw, Info } from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
import { StatusBadge } from '../ui/StatusBadge';
import { api } from '../../services/api';
import { showToast } from '../ui/ToastHost';
import {
  AFTER_HOURS_OPTIONS,
  WEEKDAYS,
  businessHoursSummary,
  isBusinessHoursEmpty,
} from './agent-creation';

const DEFAULT_PROFILE = {
  greetingPhrase: '',
  businessHours: {},
  timezone: 'Asia/Kolkata',
  afterHoursAction: 'voicemail',
  transferNumber: '',
  inboundEnabled: true,
  outboundEnabled: true,
};

const DECISION_LABEL = {
  in_hours: 'Inside business hours — the agent answers',
  no_hours_configured: 'No business hours set — the agent always answers',
  after_hours_voicemail: 'Outside business hours — takes a voicemail',
  after_hours_hangup: 'Outside business hours — does not answer',
  after_hours_transfer: 'Outside business hours — transfers the call',
  after_hours_transfer_unconfigured:
    'Outside business hours — no transfer number set, so the agent answers',
  inbound_disabled: 'Incoming calls are switched off for this agent',
  invalid_profile: 'Settings could not be read — falling back to normal behaviour',
  no_profile: 'No phone settings saved yet — normal behaviour applies',
};

function DecisionNote({ decision, hasProfile }) {
  if (!decision) return null;
  return (
    <div className="flex items-start gap-2 p-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
      <Info className="w-3.5 h-3.5 text-[#6344E7] mt-0.5 shrink-0" />
      <div className="text-[11px] text-[#524E5E]">
        <span className="font-semibold text-[#0F0E17]">Right now: </span>
        {DECISION_LABEL[decision.reason] || 'The agent answers normally'}
        {decision.afterHours && <span className="block text-[10px] text-[#8C879A] mt-0.5">It is currently outside business hours.</span>}
        {decision.greetingPhrase && (
          <span className="block text-[10px] text-[#8C879A] mt-0.5">
            Caller hears: “{decision.greetingPhrase}”
          </span>
        )}
        {!hasProfile && (
          <span className="block text-[10px] text-[#8C879A] mt-0.5">
            This agent has no phone settings yet, so it behaves exactly as before.
          </span>
        )}
      </div>
    </div>
  );
}

/**
 * Operational phone settings for one agent.
 *
 * Reads and writes `/api/agents/{id}/telephony-profile`, which is the same data the
 * live inbound path enforces — so what is shown here is what actually happens on
 * the next call. Deliberately not stored in the Business Brain.
 */
export function TelephonySettingsCard({ agentId, disabled = false }) {
  const [profile, setProfile] = useState(DEFAULT_PROFILE);
  const [decision, setDecision] = useState(null);
  const [hasProfile, setHasProfile] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [dirty, setDirty] = useState(false);

  const load = useCallback(async () => {
    if (!agentId) return;
    setLoading(true);
    setError(null);
    try {
      const [data, effective] = await Promise.all([
        api.agents.getTelephonyProfile(agentId),
        api.agents.getEffectiveTelephony(agentId).catch(() => null),
      ]);
      setProfile({ ...DEFAULT_PROFILE, ...(data.profile || {}) });
      setHasProfile(Boolean(data.profile?.hasProfile));
      setDecision(effective?.decision || null);
      setDirty(false);
    } catch (e) {
      setError(e.message || 'Could not load phone settings');
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    load();
  }, [load]);

  const set = (patch) => {
    setProfile((prev) => ({ ...prev, ...patch }));
    setDirty(true);
  };

  const setHours = (day, windows) => {
    const next = { ...(profile.businessHours || {}) };
    if (!windows || windows.length === 0) delete next[day];
    else next[day] = windows;
    set({ businessHours: next });
  };

  const setWindow = (day, index, field, value) => {
    const windows = (profile.businessHours?.[day] || []).map((w, i) =>
      i === index ? { ...w, [field]: value } : w
    );
    setHours(day, windows);
  };

  const save = async () => {
    if (!agentId) return;
    setSaving(true);
    setError(null);
    try {
      await api.agents.saveTelephonyProfile(agentId, {
        greetingPhrase: profile.greetingPhrase || '',
        businessHours: profile.businessHours || {},
        timezone: profile.timezone || 'Asia/Kolkata',
        afterHoursAction: profile.afterHoursAction || 'voicemail',
        transferNumber: profile.transferNumber || '',
        inboundEnabled: profile.inboundEnabled !== false,
        outboundEnabled: profile.outboundEnabled !== false,
      });
      setDirty(false);
      showToast('Phone settings saved', 'success');
      // Re-read so the "right now" note reflects the new configuration.
      await load();
    } catch (e) {
      setError(e.message || 'Could not save phone settings');
      showToast(e.message || 'Could not save phone settings', 'error');
    } finally {
      setSaving(false);
    }
  };

  const hours = profile.businessHours || {};
  const needsTransfer = profile.afterHoursAction === 'transfer';

  return (
    <SolidCard className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold text-[#0F0E17] flex items-center gap-1.5">
            <Phone className="w-3.5 h-3.5 text-[#6344E7]" />
            When this number answers
          </h3>
          <p className="text-[11px] text-[#524E5E] mt-0.5">
            Applies to the next incoming call. Saved on the server, not in the agent's script.
          </p>
        </div>
        {loading ? (
          <RefreshCw className="w-3.5 h-3.5 text-[#8C879A] animate-spin" />
        ) : (
          <StatusBadge status={profile.inboundEnabled === false ? 'Paused' : 'Active'} size="xs" />
        )}
      </div>

      <DecisionNote decision={decision} hasProfile={hasProfile} />

      <div className="space-y-2">
        <label className="flex items-center justify-between p-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
          <span>
            <span className="block font-semibold text-[#0F0E17] text-xs">Accept incoming calls</span>
            <span className="block text-[10px] text-[#8C879A]">
              When off, this number does not ring for inbound calls.
            </span>
          </span>
          <input
            type="checkbox"
            checked={profile.inboundEnabled !== false}
            disabled={disabled}
            onChange={(e) => set({ inboundEnabled: e.target.checked })}
            data-testid="studio-inbound-enabled"
            className="w-4 h-4 accent-[#6344E7]"
          />
        </label>

        <label className="flex items-center justify-between p-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
          <span>
            <span className="block font-semibold text-[#0F0E17] text-xs">Allow outgoing calls</span>
            <span className="block text-[10px] text-[#8C879A]">
              When off, this agent cannot place calls or receive callbacks.
            </span>
          </span>
          <input
            type="checkbox"
            checked={profile.outboundEnabled !== false}
            disabled={disabled}
            onChange={(e) => set({ outboundEnabled: e.target.checked })}
            data-testid="studio-outbound-enabled"
            className="w-4 h-4 accent-[#6344E7]"
          />
        </label>
      </div>

      <div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-bold text-[#0F0E17]">Business hours</span>
          <span className="text-[10px] text-[#8C879A]" data-testid="studio-hours-summary">
            {businessHoursSummary(hours)}
            {!isBusinessHoursEmpty(hours) && ` · ${profile.timezone}`}
          </span>
        </div>
        <div className="mt-2 space-y-1.5">
          {WEEKDAYS.map((day) => {
            const windows = hours[day.id] || [];
            const isOpen = windows.length > 0;
            return (
              <div key={day.id} className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() =>
                    setHours(
                      day.id,
                      isOpen ? [] : [{ open: '09:00', close: '18:00' }]
                    )
                  }
                  disabled={disabled}
                  data-testid={`studio-day-${day.id}`}
                  aria-pressed={isOpen}
                  className={`w-11 shrink-0 px-2 py-1.5 rounded-lg text-[11px] font-bold border transition-colors disabled:opacity-50 ${
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
                          disabled={disabled}
                          data-testid={`studio-hours-${day.id}-open`}
                          className="bg-white border border-[#E4E2EB] rounded-lg px-1.5 py-1 text-[11px] font-mono disabled:opacity-50"
                        />
                        <span className="text-[10px] text-[#8C879A]">to</span>
                        <input
                          type="time"
                          value={w.close}
                          onChange={(e) => setWindow(day.id, i, 'close', e.target.value)}
                          disabled={disabled}
                          data-testid={`studio-hours-${day.id}-close`}
                          className="bg-white border border-[#E4E2EB] rounded-lg px-1.5 py-1 text-[11px] font-mono disabled:opacity-50"
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
          disabled={disabled}
          onClick={() =>
            set({
              businessHours: isBusinessHoursEmpty(hours)
                ? {
                    mon: [{ open: '09:00', close: '18:00' }],
                    tue: [{ open: '09:00', close: '18:00' }],
                    wed: [{ open: '09:00', close: '18:00' }],
                    thu: [{ open: '09:00', close: '18:00' }],
                    fri: [{ open: '09:00', close: '18:00' }],
                    sat: [{ open: '09:00', close: '14:00' }],
                  }
                : {},
            })
          }
          data-testid="studio-hours-toggle-all"
          className="mt-2 text-[11px] font-semibold text-[#5034CE] hover:underline disabled:opacity-50"
        >
          {isBusinessHoursEmpty(hours) ? 'Set standard business hours' : 'Clear hours (always open)'}
        </button>
      </div>

      <div>
        <span className="text-xs font-bold text-[#0F0E17]">Outside business hours</span>
        <div className="mt-2 grid sm:grid-cols-2 gap-2">
          {AFTER_HOURS_OPTIONS.map((opt) => {
            const active = (profile.afterHoursAction || 'voicemail') === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                disabled={disabled}
                onClick={() => set({ afterHoursAction: opt.id })}
                data-testid={`studio-after-hours-${opt.id}`}
                aria-pressed={active}
                className={`px-3 py-2 rounded-xl text-left border transition-all disabled:opacity-50 ${
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

        {needsTransfer && (
          <label className="block mt-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A]">
              Transfer to
            </span>
            <input
              type="text"
              value={profile.transferNumber || ''}
              onChange={(e) => set({ transferNumber: e.target.value })}
              disabled={disabled}
              placeholder="+919999999999"
              data-testid="studio-transfer-number"
              className="mt-1 w-full bg-white border border-[#E4E2EB] rounded-xl px-2.5 py-2 text-xs font-mono disabled:opacity-50"
            />
          </label>
        )}
      </div>

      <label className="block">
        <span className="text-xs font-bold text-[#0F0E17]">Greeting the caller hears</span>
        <span className="block text-[10px] text-[#8C879A] mb-1">
          Leave blank to use the opening line from the agent's script.
        </span>
        <textarea
          value={profile.greetingPhrase || ''}
          onChange={(e) => set({ greetingPhrase: e.target.value })}
          rows={2}
          maxLength={500}
          disabled={disabled}
          placeholder="Thanks for calling, this is Priya speaking."
          data-testid="studio-greeting"
          className="w-full rounded-xl bg-white border border-[#E4E2EB] px-3 py-2 text-xs text-[#0F0E17] placeholder:text-[#8C879A] focus:outline-none focus:border-[#6344E7] resize-none disabled:opacity-50"
        />
      </label>

      {error && (
        <div
          data-testid="studio-telephony-error"
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900"
        >
          {error}
        </div>
      )}

      <div className="flex items-center justify-end gap-2 pt-1 border-t border-[#E4E2EB]">
        {dirty && <span className="text-[10px] text-[#B45309]">Unsaved changes</span>}
        <TactileButton
          variant="secondary"
          size="sm"
          icon={RefreshCw}
          onClick={load}
          loading={loading}
          disabled={disabled}
        >
          Reset
        </TactileButton>
        <TactileButton
          variant="brand"
          size="sm"
          loading={saving}
          disabled={disabled || !dirty}
          data-testid="studio-telephony-save"
          onClick={save}
        >
          Save phone settings
        </TactileButton>
      </div>
    </SolidCard>
  );
}
