import React from 'react';
import { CalendarClock } from 'lucide-react';
import { SolidCard } from '../../ui/SolidCard';
import { showToast } from '../../ui/ToastHost';

const field = 'mt-1 min-h-10 w-full rounded-control border border-line bg-surface px-3 py-2 text-base text-ink sm:text-copy focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15';
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

/** Server defaults (followup_policy.py) for policies saved before these settings existed. */
export const RECALL_DEFAULTS = {
  recallOutboundMode: 'off',
  recallOutcomes: ['no_answer', 'busy', 'declined'],
  recallMaxAttempts: 3,
  recallSpacingMinutes: 120,
  recallBackoff: true,
  recallMinGapAfterRejectMinutes: 60,
  recallMaxPerNumberPerDay: 2,
  quietHoursEnabled: false,
  quietStart: '13:00',
  quietEnd: '14:00',
  skipHolidays: true,
  holidays: [],
  dayParts: {
    morning: { start: '10:00', end: '12:00' },
    after_lunch: { start: '14:00', end: '15:00' },
    afternoon: { start: '14:00', end: '16:00' },
    end_of_day: { start: '17:30', end: '18:30' },
    evening: { start: '17:00', end: '19:30' },
    night: { start: '19:30', end: '20:30' },
  },
};

const RECALL_OUTCOMES = [
  ['no_answer', 'No answer'],
  ['busy', 'Busy'],
  ['declined', 'Declined'],
  ['failed', 'Failed to connect'],
];
const SPACING = [[30, '30 minutes'], [60, '1 hour'], [120, '2 hours'], [240, '4 hours'], [1440, 'Next day']];
const REJECT_GAP = [[15, '15 minutes'], [30, '30 minutes'], [60, '1 hour'], [120, '2 hours']];
const DAY_PARTS = [
  ['morning', 'Morning', '“morning”, “subah”, “ఉదయం”, “காலை”'],
  ['after_lunch', 'After lunch', '“after lunch”, “lunch ke baad”'],
  ['afternoon', 'Afternoon', '“afternoon”, “dopahar”, “మధ్యాహ్నం”'],
  ['end_of_day', 'End of day', '“end of day”, “before closing”'],
  ['evening', 'Evening', '“evening”, “शाम”, “ఈవెనింగ్”, “மாலை”'],
  ['night', 'Night', '“night”, “raat”, “రాత్రి” (never after 9 pm)'],
];
const INDIA_ZONES = ['Asia/Kolkata', 'Asia/Calcutta'];

export function FollowUpSettingsCard({ config, onChange, acknowledged, onAcknowledge, needsConsent, error }) {
  const set = (key, value) => onChange({ ...config, [key]: value });
  // Read-through defaults so a policy saved before these settings existed still renders.
  const c = config ? { ...RECALL_DEFAULTS, ...config, dayParts: { ...RECALL_DEFAULTS.dayParts, ...(config.dayParts || {}) } } : null;
  const setDayPart = (key, edge, value) => set('dayParts', { ...c.dayParts, [key]: { ...c.dayParts[key], [edge]: value } });
  return <SolidCard className="space-y-5" data-testid="followup-settings">
    <div className="flex gap-3"><CalendarClock className="h-5 w-5 shrink-0 text-accent" aria-hidden="true" /><div><h3 className="text-title text-ink">Callbacks & missed calls</h3><p className="mt-1 text-ui leading-relaxed text-fg-muted">Let this employee schedule follow-up calls. They are paid from your wallet, skip numbers on the Do Not Disturb list, and only happen inside the calling window below and the employee’s working hours.</p></div></div>
    {error ? <p role="alert" className="rounded-control bg-warning-soft p-3 text-copy text-warning-fg">{error}</p> : !config ? <p role="status" className="text-copy">Loading follow-up settings…</p> : <>
      <label className="flex items-start gap-3 text-copy font-medium"><input type="checkbox" aria-label="Allow scheduled follow-up calls" checked={config.enabled} onChange={(e) => { set('enabled', e.target.checked); onAcknowledge(false); showToast(e.target.checked ? 'Permission is not active until you confirm and save. Follow-up calls use your wallet.' : 'Save to cancel pending follow-ups. Calls that have already started may finish.', 'info'); }} className="mt-1 h-4 w-4 accent-accent" /><span>Allow scheduled follow-up calls<span className="mt-1 block text-ui font-normal text-fg-muted">Off by default. Enabling applies to new caller requests and new missed calls.</span></span></label>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="text-ui font-medium">Caller-requested callbacks<select aria-label="Caller-requested callbacks" className={field} value={config.callbackMode} onChange={(e) => set('callbackMode', e.target.value)}><option value="review">Review before calling</option><option value="automatic">Automatically schedule explicit requests</option></select></label>
        <label className="text-ui font-medium">Missed inbound calls<select aria-label="Missed inbound calls" className={field} value={config.missedMode} onChange={(e) => set('missedMode', e.target.value)}><option value="off">Do not follow up automatically</option><option value="review">Add to review queue</option><option value="automatic">Automatically call back</option></select></label>
        <label className="text-ui font-medium">Missed-call delay (minutes)<input aria-label="Missed-call delay (minutes)" className={field} type="number" min="5" max="10080" value={config.missedDelayMinutes} onChange={(e) => set('missedDelayMinutes', Number(e.target.value))} /></label>
        <label className="text-ui font-medium">Recipient timezone fallback<input aria-label="Follow-up timezone" className={field} value={config.timezone} onChange={(e) => set('timezone', e.target.value)} placeholder="Asia/Kolkata" /><span className="mt-1 block font-normal text-fg-muted">Use a timezone name such as Asia/Kolkata. If the caller’s timezone is different or unclear, the call waits for your review.</span></label>
        <label className="text-ui font-medium">Call window starts<input aria-label="Call window starts" className={field} type="time" value={config.startTime} onChange={(e) => set('startTime', e.target.value)} /></label>
        <label className="text-ui font-medium">Call window ends<input aria-label="Call window ends" className={field} type="time" value={config.endTime} onChange={(e) => set('endTime', e.target.value)} /></label>
      </div>
      <fieldset><legend className="mb-2 text-ui font-medium">Calling days</legend><div className="flex flex-wrap gap-2">{DAYS.map((day, index) => <button type="button" key={day} aria-pressed={config.weekdays.includes(index)} onClick={() => set('weekdays', config.weekdays.includes(index) ? config.weekdays.filter((d) => d !== index) : [...config.weekdays, index].sort())} className={`min-h-10 rounded-control border px-3 text-ui ${config.weekdays.includes(index) ? 'border-accent bg-accent-soft text-accent-fg' : 'border-line bg-surface text-fg-body hover:border-line-strong'}`}>{day}</button>)}</div></fieldset>
      <section className="space-y-4 rounded-control border border-line p-4" data-testid="recall-settings" aria-labelledby="recall-settings-title">
        <div><h4 id="recall-settings-title" className="text-copy font-semibold text-ink">Call back calls that didn’t connect</h4><p className="mt-1 text-ui text-fg-muted">Outgoing calls nobody answered, that were busy, declined or failed, and incoming calls you missed (set above). Recalls appear in Follow-ups and on Home.</p></div>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-ui font-medium">Outgoing calls not answered<select aria-label="Outgoing calls not answered" data-testid="recall-outbound-mode" className={field} value={c.recallOutboundMode} onChange={(e) => set('recallOutboundMode', e.target.value)}><option value="off">Don’t call back automatically</option><option value="review">Add to review queue</option><option value="automatic">Automatically call back</option></select></label>
          <label className="text-ui font-medium">Recall attempts per call<select aria-label="Recall attempts per call" className={field} value={c.recallMaxAttempts} onChange={(e) => set('recallMaxAttempts', Number(e.target.value))}>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n} {n === 1 ? 'attempt' : 'attempts'}</option>)}</select></label>
          <label className="text-ui font-medium">Time between attempts<select aria-label="Time between attempts" className={field} value={c.recallSpacingMinutes} onChange={(e) => set('recallSpacingMinutes', Number(e.target.value))}>{SPACING.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="text-ui font-medium">Wait after a declined call<select aria-label="Wait after a declined call" className={field} value={c.recallMinGapAfterRejectMinutes} onChange={(e) => set('recallMinGapAfterRejectMinutes', Number(e.target.value))}>{REJECT_GAP.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="text-ui font-medium">Calls to one number per day<select aria-label="Calls to one number per day" className={field} value={c.recallMaxPerNumberPerDay} onChange={(e) => set('recallMaxPerNumberPerDay', Number(e.target.value))}>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
          <label className="flex items-start gap-2 self-end text-copy"><input type="checkbox" aria-label="Wait longer after each unanswered try" checked={c.recallBackoff} onChange={(e) => set('recallBackoff', e.target.checked)} className="mt-1 h-4 w-4 accent-accent" /><span>Wait longer after each unanswered try<span className="block text-ui text-fg-muted">2 h, then 4 h, then 8 h.</span></span></label>
        </div>
        <fieldset><legend className="mb-2 text-ui font-medium">Call back when the outgoing call was</legend><div className="flex flex-wrap gap-2">{RECALL_OUTCOMES.map(([key, label]) => { const on = c.recallOutcomes.includes(key); return <button type="button" key={key} aria-pressed={on} data-testid={`recall-outcome-${key}`} onClick={() => set('recallOutcomes', on ? c.recallOutcomes.filter((v) => v !== key) : [...c.recallOutcomes, key])} className={`min-h-10 rounded-control border px-3 text-ui ${on ? 'border-accent bg-accent-soft text-accent-fg' : 'border-line bg-surface text-fg-body hover:border-line-strong'}`}>{label}</button>; })}</div></fieldset>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex items-start gap-2 text-copy"><input type="checkbox" aria-label="Quiet hours" checked={c.quietHoursEnabled} onChange={(e) => set('quietHoursEnabled', e.target.checked)} className="mt-1 h-4 w-4 accent-accent" /><span>Quiet hours<span className="block text-ui text-fg-muted">No follow-up calls in this break, for example lunch.</span></span></label>
          <div className="grid grid-cols-2 gap-3"><label className="text-ui font-medium">Quiet from<input aria-label="Quiet hours start" className={field} type="time" disabled={!c.quietHoursEnabled} value={c.quietStart} onChange={(e) => set('quietStart', e.target.value)} /></label><label className="text-ui font-medium">Quiet until<input aria-label="Quiet hours end" className={field} type="time" disabled={!c.quietHoursEnabled} value={c.quietEnd} onChange={(e) => set('quietEnd', e.target.value)} /></label></div>
          <label className="flex items-start gap-2 text-copy"><input type="checkbox" aria-label="Skip holidays" checked={c.skipHolidays} onChange={(e) => set('skipHolidays', e.target.checked)} className="mt-1 h-4 w-4 accent-accent" /><span>Skip holidays<span className="block text-ui text-fg-muted">The employee’s closed days always count. Add public holidays here.</span></span></label>
          <label className="text-ui font-medium">Holiday dates<input aria-label="Holiday dates" className={field} disabled={!c.skipHolidays} placeholder="2026-11-14, 2026-12-25" value={c.holidays.join(', ')} onChange={(e) => set('holidays', e.target.value.split(',').map((v) => v.trim()).filter(Boolean))} /></label>
        </div>
        <div className="rounded-control bg-surface-subtle p-3 text-ui text-fg-body" data-testid="recall-stop-conditions"><p className="font-medium text-ink">Recalls always stop when</p><ul className="mt-1 list-disc space-y-0.5 pl-5"><li>the call connects, or the person calls you and is answered</li><li>the number is on your Do Not Disturb list or the person opted out</li><li>the attempt limit is reached or the request expires</li><li>the number is invalid or not in service</li></ul>{INDIA_ZONES.includes(c.timezone) && <p className="mt-2">Indian numbers are only called between 9:00 am and 9:00 pm (TRAI), even if your window is wider.</p>}</div>
      </section>
      <details className="rounded-control border border-line p-4" data-testid="day-part-settings"><summary className="cursor-pointer text-copy font-medium">When callers say “evening”, “tomorrow morning”…</summary><p className="mt-3 text-ui text-fg-muted">A vague time is booked at the start of its window in {c.timezone || 'your timezone'}. If today’s window has passed, the next calling day is used. Clock times like “5 pm” are kept exactly.</p><div className="mt-3 grid gap-3">{DAY_PARTS.map(([key, label, examples]) => <div key={key} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_8rem_8rem] sm:items-end" data-testid={`day-part-${key}`}><div className="min-w-0"><p className="text-ui font-medium text-ink">{label}</p><p className="text-meta text-fg-muted break-words">{examples}</p></div><label className="text-meta text-fg-muted">From<input aria-label={`${label} starts`} className={field} type="time" value={c.dayParts[key].start} onChange={(e) => setDayPart(key, 'start', e.target.value)} /></label><label className="text-meta text-fg-muted">To<input aria-label={`${label} ends`} className={field} type="time" value={c.dayParts[key].end} onChange={(e) => setDayPart(key, 'end', e.target.value)} /></label></div>)}</div></details>
      {needsConsent && <label className="flex items-start gap-3 rounded-control border border-warning-line bg-warning-soft p-4 text-copy text-warning-fg"><input type="checkbox" aria-label="Authorize follow-up calls and charges" checked={acknowledged} onChange={(e) => onAcknowledge(e.target.checked)} className="mt-1 h-4 w-4 shrink-0" /><span>I allow this employee to make the follow-up calls set up here and charge my wallet. I have permission to contact these people. The Do Not Disturb list always comes first.</span></label>}
      <p className="text-ui leading-relaxed text-fg-muted">“After six hours” sets the earliest requested time. Quiet hours, holidays, capacity and cooldowns can move it later. Vague requests go to review. Turning permission off cancels pending follow-ups; it does not stop a call that has already started.</p>
      <details className="rounded-control border border-line p-4"><summary className="cursor-pointer text-copy font-medium">Limits, expiry & lead scoring</summary><div className="mt-4 grid gap-4 sm:grid-cols-2">{[['maxAttempts', 'Maximum attempts per request', 1, 3], ['retryDelayMinutes', 'Retry delay (minutes)', 30, 10080], ['dailyLimit', 'Daily follow-up call limit', 1, 500], ['cooldownMinutes', 'Same-number cooldown (minutes)', 30, 43200], ['expiryDays', 'Request expires after (days)', 1, 90], ['warmThreshold', 'Warm score threshold', 1, 99], ['hotThreshold', 'Hot score threshold', 1, 100]].map(([key, label, min, max]) => <label key={key} className="text-ui font-medium">{label}<input className={field} type="number" min={min} max={max} value={config[key]} onChange={(e) => set(key, Number(e.target.value))} /></label>)}
        <label className="flex items-center gap-2 text-copy"><input type="checkbox" checked={config.scoringEnabled} onChange={(e) => set('scoringEnabled', e.target.checked)} />Score future call outcomes</label>
        <div className="sm:col-span-2"><p className="text-ui text-fg-muted">Priority weights must total 100. Scores explain recorded interest, requirements, timing and contact details. They do not confirm a conversion or permit a call.</p><div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">{Object.entries(config.scoreWeights).map(([key, value]) => <label key={key} className="text-ui capitalize">{key}<input className={field} aria-label={`${key} score weight`} type="number" min="0" max="100" value={value} onChange={(e) => set('scoreWeights', { ...config.scoreWeights, [key]: Number(e.target.value) })} /></label>)}</div></div>
      </div></details>
      {config.scoringEnabled && <details className="rounded-control border border-line p-4"><summary className="cursor-pointer text-copy font-medium">Choose which collected details count towards the score</summary><p className="mt-3 text-ui text-fg-muted">List the names of details your employee collects on calls, separated by commas. Changes apply to future calls; past scores stay as they were.</p><div className="mt-3 grid gap-3">{Object.entries(config.scoreFactKeys || {}).map(([key, values]) => <label key={key} className="text-ui capitalize">{key} details<input className={field} value={values.join(', ')} onChange={(e) => set('scoreFactKeys', { ...config.scoreFactKeys, [key]: e.target.value.split(',').map((v) => v.trim()) })} /></label>)}</div></details>}
    </>}
  </SolidCard>;
}
