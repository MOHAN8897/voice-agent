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

/**
 * Frontend default only. The server's DEFAULT_TIMEZONE is unchanged — this just
 * decides what an empty profile starts on in this console.
 */
const DEFAULT_PROFILE = {
  greetingPhrase: '',
  businessHours: {},
  closedDates: [],
  timezone: 'Asia/Kolkata',
  afterHoursAction: 'voicemail',
  transferNumber: '',
  inboundEnabled: true,
  outboundEnabled: true,
};

/** India first; existing international profiles keep their saved timezone. */
const TIMEZONE_FAVOURITES = [
  'Asia/Kolkata',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Dublin',
  'Europe/Berlin',
];

const HOURS_HELP =
  'These hours decide how incoming calls are answered, in the time zone below. For outbound commercial calls in India, ' +
  'separately verify applicable calling times and recipient preferences under TRAI rules. ' +
  'A business-hours setting does not establish permission to call.';

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
    <div className="flex items-start gap-2 p-3 rounded-control bg-info-soft border border-info-line">
      <Info className="w-4 h-4 text-info-fg mt-0.5 shrink-0" aria-hidden="true" />
      <div className="text-ui text-fg-body min-w-0">
        <span className="font-semibold text-ink">Right now: </span>
        {DECISION_LABEL[decision.reason] || 'The agent answers normally'}
        {decision.afterHours && <span className="block text-meta text-fg-muted mt-0.5">It is currently outside business hours.</span>}
        {decision.greetingPhrase && (
          <span className="block text-meta text-fg-muted mt-0.5">
            Caller hears: “{decision.greetingPhrase}”
          </span>
        )}
        {!hasProfile && (
          <span className="block text-meta text-fg-muted mt-0.5">
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
export function TelephonySettingsCard({
  agentId,
  disabled = false,
  profile: controlledProfile,
  onChange: onControlledChange,
  hideSaveButton = false,
}) {
  const [internalProfile, setInternalProfile] = useState(DEFAULT_PROFILE);
  const profile = controlledProfile !== undefined ? controlledProfile : internalProfile;
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
      const loaded = { ...DEFAULT_PROFILE, ...(data.profile || {}) };
      if (onControlledChange) {
        onControlledChange(loaded);
      } else {
        setInternalProfile(loaded);
      }
      setHasProfile(Boolean(data.profile?.hasProfile));
      setDecision(effective?.decision || null);
      setDirty(false);
    } catch (e) {
      setError(e.message || 'Could not load phone settings');
    } finally {
      setLoading(false);
    }
  }, [agentId, onControlledChange]);

  useEffect(() => {
    if (controlledProfile === undefined) {
      load();
    } else if (agentId) {
      api.agents
        .getEffectiveTelephony(agentId)
        .then((eff) => {
          setDecision(eff?.decision || null);
        })
        .catch(() => {});
    }
  }, [load, agentId, controlledProfile === undefined]);

  const set = (patch) => {
    if (onControlledChange) {
      onControlledChange(patch);
    } else {
      setInternalProfile((prev) => ({ ...prev, ...patch }));
      setDirty(true);
    }
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
        closedDates: Array.isArray(profile.closedDates) ? profile.closedDates : [],
        timezone: profile.timezone || DEFAULT_PROFILE.timezone,
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
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-title text-ink flex items-center gap-2">
            <Phone className="w-4 h-4 text-fg-subtle" aria-hidden="true" />
            When this number answers
          </h3>
          <p className="text-ui text-fg-muted mt-0.5">
            Applies from the next incoming call. Saved separately from the agent's script.
          </p>
        </div>
        {loading ? (
          <RefreshCw className="w-3.5 h-3.5 text-fg-muted animate-spin" />
        ) : (
          <StatusBadge status={profile.inboundEnabled === false ? 'Paused' : 'Active'} size="xs" />
        )}
      </div>

      <DecisionNote decision={decision} hasProfile={hasProfile} />

      <div className="space-y-2">
        <label className="flex items-center justify-between gap-3 p-3 rounded-control bg-canvas border border-line cursor-pointer">
          <span className="min-w-0">
            <span className="block font-medium text-ink text-ui">Accept incoming calls</span>
            <span className="block text-meta text-fg-muted">
              When off, this number does not ring for inbound calls.
            </span>
          </span>
          <input
            type="checkbox"
            checked={profile.inboundEnabled !== false}
            disabled={disabled}
            onChange={(e) => set({ inboundEnabled: e.target.checked })}
            data-testid="studio-inbound-enabled"
            className="w-4 h-4 shrink-0 accent-accent"
          />
        </label>

        <label className="flex items-center justify-between gap-3 p-3 rounded-control bg-canvas border border-line cursor-pointer">
          <span className="min-w-0">
            <span className="block font-medium text-ink text-ui">Allow outgoing calls</span>
            <span className="block text-meta text-fg-muted">
              When off, this agent cannot place calls or receive callbacks.
            </span>
          </span>
          <input
            type="checkbox"
            checked={profile.outboundEnabled !== false}
            disabled={disabled}
            onChange={(e) => set({ outboundEnabled: e.target.checked })}
            data-testid="studio-outbound-enabled"
            className="w-4 h-4 shrink-0 accent-accent"
          />
        </label>
      </div>

      <div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-copy font-semibold text-ink">Business hours</span>
          <span className="text-meta text-fg-muted" data-testid="studio-hours-summary">
            {businessHoursSummary(hours)}
            {!isBusinessHoursEmpty(hours) && ` · ${profile.timezone}`}
          </span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <label className="text-ui font-medium text-ink" htmlFor="studio-timezone">
            Time zone
          </label>
          <input
            id="studio-timezone"
            list="studio-timezone-options"
            value={profile.timezone || DEFAULT_PROFILE.timezone}
            onChange={(e) => set({ timezone: e.target.value.trim() })}
            disabled={disabled}
            data-testid="studio-timezone"
            className="min-w-0 max-w-full px-2.5 py-1.5 min-h-[36px] bg-surface border border-line rounded-control text-base sm:text-ui text-ink focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 disabled:opacity-50"
          />
          <datalist id="studio-timezone-options">
            {TIMEZONE_FAVOURITES.map((tz) => (
              <option key={tz} value={tz} />
            ))}
          </datalist>
          <span className="text-meta text-fg-muted">
            Pick from the list or type a zone such as Asia/Kolkata.
          </span>
        </div>
        <p className="mt-2 text-meta text-fg-muted">{HOURS_HELP}</p>
        <div className="mt-2 space-y-1.5">
          {WEEKDAYS.map((day) => {
            const windows = hours[day.id] || [];
            const isOpen = windows.length > 0;
            return (
              <div key={day.id} className="flex flex-wrap items-center gap-2">
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
                  className={`w-12 min-h-[36px] shrink-0 px-2 py-1.5 rounded-control text-meta font-semibold border transition-colors disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                    isOpen
                      ? 'bg-ink text-white border-ink'
                      : 'bg-surface text-fg-muted border-line hover:border-line-strong'
                  }`}
                >
                  {day.label}
                </button>
                {isOpen ? (
                  <div className="flex flex-wrap items-center gap-1.5">
                    {windows.map((w, i) => (
                      <div key={i} className="flex items-center gap-1">
                        <input
                          type="time"
                          value={w.open}
                          onChange={(e) => setWindow(day.id, i, 'open', e.target.value)}
                          disabled={disabled}
                          data-testid={`studio-hours-${day.id}-open`}
                          className="px-2 py-1 min-h-[36px] font-mono tabular-nums bg-surface border border-line rounded-control text-base sm:text-ui text-ink focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 disabled:opacity-50"
                        />
                        <span className="text-meta text-fg-muted">to</span>
                        <input
                          type="time"
                          value={w.close}
                          onChange={(e) => setWindow(day.id, i, 'close', e.target.value)}
                          disabled={disabled}
                          data-testid={`studio-hours-${day.id}-close`}
                          className="px-2 py-1 min-h-[36px] font-mono tabular-nums bg-surface border border-line rounded-control text-base sm:text-ui text-ink focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 disabled:opacity-50"
                        />
                      </div>
                    ))}
                  </div>
                ) : (
                  <span className="text-meta text-fg-muted">Closed</span>
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
          className="mt-2 min-h-[36px] text-ui font-semibold text-accent-fg hover:underline disabled:opacity-50"
        >
          {isBusinessHoursEmpty(hours) ? 'Set standard business hours' : 'Clear hours (always open)'}
        </button>
      </div>

      <div>
        <span className="text-copy font-semibold text-ink">Holidays and closed dates</span>
        <span className="block text-meta text-fg-muted mb-1">
          One date per line, written as YYYY-MM-DD. On these dates the agent follows the after-hours action
          even if the weekday would normally be open.
        </span>
        <textarea
          value={(profile.closedDates || []).join('\n')}
          onChange={(e) =>
            set({
              closedDates: e.target.value
                .split(/[\n,;]+/)
                .map((s) => s.trim())
                .filter(Boolean),
            })
          }
          rows={3}
          disabled={disabled}
          placeholder={'2026-12-25\n2026-01-01'}
          data-testid="studio-closed-dates"
          className="w-full px-3 py-2 font-mono tabular-nums placeholder:text-fg-subtle resize-none bg-surface border border-line rounded-control text-base sm:text-ui text-ink focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 disabled:opacity-50"
        />
      </div>

      <div>
        <span className="text-copy font-semibold text-ink">Outside business hours</span>
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
                className={`px-3 py-2.5 rounded-control text-left border transition-colors disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                  active
                    ? 'bg-ink text-white border-ink'
                    : 'bg-surface text-fg-body border-line hover:border-line-strong'
                }`}
              >
                <span className="block text-ui font-semibold">{opt.label}</span>
                <span
                  className={`block text-meta mt-0.5 ${active ? 'text-white/70' : 'text-fg-muted'}`}
                >
                  {opt.description}
                </span>
              </button>
            );
          })}
        </div>

        {needsTransfer && (
          <label className="block mt-2">
            <span className="text-ui font-medium text-ink">
              Transfer to
            </span>
            <input
              type="text"
              value={profile.transferNumber || ''}
              onChange={(e) => set({ transferNumber: e.target.value })}
              disabled={disabled}
              placeholder="+919999999999"
              data-testid="studio-transfer-number"
              className="mt-1 w-full px-3 py-2 min-h-[40px] font-mono tabular-nums bg-surface border border-line rounded-control text-base sm:text-ui text-ink focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 disabled:opacity-50"
            />
          </label>
        )}
      </div>

      <label className="block">
        <span className="text-copy font-semibold text-ink">Greeting the caller hears</span>
        <span className="block text-meta text-fg-muted mb-1">
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
          className="w-full px-3 py-2 placeholder:text-fg-subtle resize-none bg-surface border border-line rounded-control text-base sm:text-ui text-ink focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 disabled:opacity-50"
        />
      </label>

      {error && (
        <div
          data-testid="studio-telephony-error"
          role="alert"
          className="rounded-control border border-danger-line bg-danger-soft px-3 py-2 text-ui text-danger-fg"
        >
          {error}
        </div>
      )}

      {!hideSaveButton && (
        <div className="flex flex-wrap items-center justify-end gap-2 pt-3 border-t border-line">
          {dirty && <span className="text-ui text-warning-fg">Unsaved changes</span>}
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
      )}
    </SolidCard>
  );
}
