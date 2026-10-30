import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Phone, LayoutGrid, Users, PhoneCall, ShieldCheck } from 'lucide-react';
import { SolidCard } from '../../ui/SolidCard';
import { TactileButton } from '../../ui/TactileButton';
import { Badge } from '../../ui/StatusBadge';
import { humanizeToken } from '../../../lib/internalLabels';
import { useWorkspace } from '../../context/WorkspaceContext';
import { showToast } from '../../ui/ToastHost';
import { LANGUAGE_OPTIONS } from '../../../lib/voicePresets';
import { api } from '../../../services/api';
import { TelephonySettingsCard } from '../TelephonySettingsCard';
import { SectionNav } from './SectionNav';
import { FollowUpSettingsCard } from './FollowUpSettingsCard';
import { useAuth } from '../../../context/AuthContext';

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

function cleanSnapshot(data) {
  return {
    name: (data?.name || '').trim(),
    language: data?.language || 'en-IN',
    status: data?.status || 'active',
    numberId: data?.numberId || '',
    recordingDisclosureEnabled: Boolean(data?.recordingDisclosureEnabled),
    recordingDisclosureText: (data?.recordingDisclosureText || '').trim(),
    telephonyProfile: {
      greetingPhrase: (data?.telephonyProfile?.greetingPhrase || '').trim(),
      businessHours: data?.telephonyProfile?.businessHours || {},
      closedDates: Array.isArray(data?.telephonyProfile?.closedDates) ? data.telephonyProfile.closedDates : [],
      timezone: data?.telephonyProfile?.timezone || 'Asia/Kolkata',
      afterHoursAction: data?.telephonyProfile?.afterHoursAction || 'voicemail',
      transferNumber: (data?.telephonyProfile?.transferNumber || '').trim(),
      inboundEnabled: data?.telephonyProfile?.inboundEnabled !== false,
      outboundEnabled: data?.telephonyProfile?.outboundEnabled !== false,
    },
    compliance: data?.compliance || {},
    followup: data?.followup || null,
  };
}

/**
 * Unified Agent Settings Panel.
 *
 * Holds all configuration sections (Identity, Status, Number, Operating Schedule & Greeting,
 * Call Recording & Disclosure, Compliance) in memory with ZERO database writes until
 * the workspace save dock is used.
 */
export function AgentSettingsPanel({
  savingChanges = false,
  agent,
  agentGreeting,
  onGreetingChange,
  onOpenBuyNumber,
  onDirtyChange,
  registerSaveHandler,
  onSettingsSaved,
}) {
  const { user } = useAuth();
  const readOnly = user?.role === 'customer_viewer' || user?.role === 'viewer';
  const { phoneNumbers, agents, assignNumberToAgent, updateAgent } = useWorkspace();
  const agentId = agent?.id;
  const [category, setCategory] = useState('all');

  const assigned = useMemo(
    () => phoneNumbers.find((n) => n.assignedAgentId === agentId),
    [phoneNumbers, agentId]
  );
  const currentNumberId = assigned?.id || agent?.numberId || '';

  // In-memory state for the entire agent settings stack
  const [name, setName] = useState(agent?.name || '');
  const [language, setLanguage] = useState(
    (agent?.languages && agent.languages[0]) || agent?.language || 'en-IN'
  );
  const [status, setStatus] = useState(agent?.status || 'active');
  const [numberId, setNumberId] = useState(currentNumberId);
  const [recordingDisclosureEnabled, setRecordingDisclosureEnabled] = useState(
    Boolean(agent?.recordingDisclosureEnabled)
  );
  const [recordingDisclosureText, setRecordingDisclosureText] = useState(
    agent?.recordingDisclosureText || 'This call may be recorded for quality and training purposes.'
  );
  const [telephonyProfile, setTelephonyProfile] = useState(() => ({
    ...DEFAULT_PROFILE,
    greetingPhrase: agentGreeting || '',
  }));
  const [followup, setFollowup] = useState(null);
  const [followupRevision, setFollowupRevision] = useState(0);
  const [followupError, setFollowupError] = useState('');
  const [profileError, setProfileError] = useState('');
  const [profileLoaded, setProfileLoaded] = useState(false);
  const [followupAcknowledged, setFollowupAcknowledged] = useState(false);
  const [compliance, setCompliance] = useState({});
  const [complianceSummary, setComplianceSummary] = useState(null);
  const [complianceLoading, setComplianceLoading] = useState(false);
  const [complianceError, setComplianceError] = useState(null);

  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [error, setError] = useState(null);

  // Keep telephonyProfile.greetingPhrase in sync with universal agentGreeting
  useEffect(() => {
    if (agentGreeting !== undefined) {
      setTelephonyProfile((prev) => {
        if (prev.greetingPhrase === agentGreeting) return prev;
        return { ...prev, greetingPhrase: agentGreeting };
      });
    }
  }, [agentGreeting]);

  // Snapshot for dirty comparison
  const [initialSnapshot, setInitialSnapshot] = useState(null);

  // Seed on agent selection or change
  useEffect(() => {
    if (!agentId || savingRef.current) return;

    setName(agent?.name || '');
    setLanguage((agent?.languages && agent.languages[0]) || agent?.language || 'en-IN');
    setStatus(agent?.status || 'active');
    setNumberId(currentNumberId);
    setRecordingDisclosureEnabled(Boolean(agent?.recordingDisclosureEnabled));
    setRecordingDisclosureText(
      agent?.recordingDisclosureText || 'This call may be recorded for quality and training purposes.'
    );
    let cancelled = false;
    setComplianceLoading(true);
    setComplianceError(null); setProfileError(''); setProfileLoaded(false);
    setFollowup(null); setFollowupError(''); setFollowupAcknowledged(false);

    Promise.all([
      api.telephony.getAgentCompliance(agentId).catch((e) => {
        if (!cancelled) setComplianceError(e?.message || 'Could not load compliance obligations');
        return null;
      }),
      api.agents.getTelephonyProfile(agentId).catch((e) => {
        if (!cancelled) setProfileError(e.message || 'Operating settings could not be loaded. Reload before saving.');
        return null;
      }),
      api.followups.policy(agentId).catch((e) => { if (!cancelled) setFollowupError(e.message || 'Follow-up scheduling could not be loaded. Reload to retry.'); return null; }),
    ]).then(([compData, profData, followupData]) => {
      if (cancelled) return;
      const loadedComp = compData?.acknowledged || {};
      const rawProf = profData?.profile || {};
      const loadedProf = {
        ...DEFAULT_PROFILE,
        ...rawProf,
        greetingPhrase: agentGreeting !== undefined && agentGreeting !== '' ? agentGreeting : (rawProf.greetingPhrase || ''),
      };

      setFollowup(followupData?.config || null);
      setFollowupRevision(followupData?.revision || 0);
      setCompliance(loadedComp);
      setProfileLoaded(Boolean(profData));
      setComplianceSummary(compData || null);
      setTelephonyProfile(loadedProf);
      setComplianceLoading(false);

      const snap = cleanSnapshot({
        name: agent?.name || '',
        language: (agent?.languages && agent.languages[0]) || agent?.language || 'en-IN',
        status: agent?.status || 'active',
        numberId: currentNumberId,
        recordingDisclosureEnabled: Boolean(agent?.recordingDisclosureEnabled),
        recordingDisclosureText:
          agent?.recordingDisclosureText || 'This call may be recorded for quality and training purposes.',
        telephonyProfile: loadedProf,
        compliance: loadedComp,
        followup: followupData?.config || null,
      });
      setInitialSnapshot(JSON.stringify(snap));
    });

    return () => {
      cancelled = true;
    };
  }, [agentId, agent?.name, agent?.status, agent?.language, agent?.recordingDisclosureEnabled, agent?.recordingDisclosureText, currentNumberId]);

  // Current state snapshot
  const currentSnapshot = useMemo(() => {
    return cleanSnapshot({
      name,
      language,
      status,
      numberId,
      recordingDisclosureEnabled,
      recordingDisclosureText,
      telephonyProfile,
      compliance,
      followup,
    });
  }, [name, language, status, numberId, recordingDisclosureEnabled, recordingDisclosureText, telephonyProfile, compliance, followup]);

  const isDirty = useMemo(() => {
    if (!initialSnapshot) return false;
    return JSON.stringify(currentSnapshot) !== initialSnapshot;
  }, [currentSnapshot, initialSnapshot]);

  // Propagate dirty state to parent for tab/page leave guards
  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  const handleDiscardAll = useCallback(() => {
    if (!initialSnapshot) return;
    try {
      const restored = JSON.parse(initialSnapshot);
      setName(restored.name);
      setLanguage(restored.language);
      setStatus(restored.status);
      setNumberId(restored.numberId);
      setRecordingDisclosureEnabled(restored.recordingDisclosureEnabled);
      setRecordingDisclosureText(restored.recordingDisclosureText);
      setTelephonyProfile(restored.telephonyProfile);
      setCompliance(restored.compliance);
      setFollowup(restored.followup); setFollowupAcknowledged(false);
      setError(null);
      showToast('Settings changes discarded', 'info');
    } catch {
      /* ignore */
    }
  }, [initialSnapshot]);

  const handleSaveAll = useCallback(async () => {
    if (!agentId || savingRef.current) return false;
    savingRef.current = true;
    setSaving(true);
    setError(null);

    try {
      if (!profileLoaded) throw new Error(profileError || 'Wait for operating settings to load before saving.');
      if (complianceError) throw new Error('Compliance settings could not be loaded. Reload before saving changes.');
      const baseSnapshot = initialSnapshot ? JSON.parse(initialSnapshot) : {};
      const needsConsent = followup?.enabled && (!baseSnapshot.followup?.enabled ||
        (followup.callbackMode === 'automatic' && baseSnapshot.followup?.callbackMode !== 'automatic') ||
        (followup.missedMode === 'automatic' && baseSnapshot.followup?.missedMode !== 'automatic'));
      if (needsConsent && !followupAcknowledged) throw new Error('Confirm follow-up call permission and wallet charges before saving.');

      // 1. Update Agent identity, status, and recording disclosures in a single call
      const identityChanged = ['name', 'status', 'language', 'recordingDisclosureEnabled', 'recordingDisclosureText']
        .some((key) => currentSnapshot[key] !== baseSnapshot[key]);
      if (identityChanged) await updateAgent(agentId, {
        name: name.trim(),
        status,
        languages: [language],
        recordingDisclosureEnabled,
        recordingDisclosureText: recordingDisclosureText.trim(),
      });

      // 2. Assign or unassign phone number if changed
      if (numberId !== baseSnapshot.numberId) {
        if (assigned && assigned.id !== numberId) {
          await assignNumberToAgent(assigned.id, '');
        }
        if (numberId) {
          await assignNumberToAgent(numberId, agentId, name.trim());
        }
      }

      // 3. Save telephony profile (operating hours, transfer, greeting)
      if (JSON.stringify(currentSnapshot.telephonyProfile) !== JSON.stringify(baseSnapshot.telephonyProfile)) await api.agents.saveTelephonyProfile(agentId, {
        greetingPhrase: telephonyProfile.greetingPhrase || '',
        businessHours: telephonyProfile.businessHours || {},
        closedDates: Array.isArray(telephonyProfile.closedDates) ? telephonyProfile.closedDates : [],
        timezone: telephonyProfile.timezone || DEFAULT_PROFILE.timezone,
        afterHoursAction: telephonyProfile.afterHoursAction || 'voicemail',
        transferNumber: telephonyProfile.transferNumber || '',
        inboundEnabled: telephonyProfile.inboundEnabled !== false,
        outboundEnabled: telephonyProfile.outboundEnabled !== false,
      });

      // 4. Save compliance obligations if changed
      if (JSON.stringify(compliance) !== JSON.stringify(baseSnapshot.compliance || {})) {
        await api.telephony.saveAgentCompliance(agentId, {
          acknowledged: compliance,
        });
      }

      // Agent.languages is the canonical session language. Voice selection is
      // saved by the voice panel with its revision; unrelated settings must not
      // overwrite it through the legacy voice endpoint.

      if (followup && JSON.stringify(followup) !== JSON.stringify(baseSnapshot.followup)) {
        const saved = await api.followups.savePolicy(agentId, { config: followup, revision: followupRevision, acknowledgeCharges: followupAcknowledged });
        setFollowupRevision(saved.revision); setFollowupAcknowledged(false);
      }

      // Update baseline snapshot
      const updatedSnapshot = JSON.stringify(currentSnapshot);
      setInitialSnapshot(updatedSnapshot);
      showToast('All agent configurations saved successfully', 'success');

      onSettingsSaved?.({
        id: agentId,
        name: name.trim(),
        status,
        language,
        languages: [language],
        recordingDisclosureEnabled,
        recordingDisclosureText: recordingDisclosureText.trim(),
        greeting: telephonyProfile.greetingPhrase || '',
      });

      return true;
    } catch (e) {
      setError(e.message || 'Could not save agent configurations');
      showToast(e.message || 'Could not save agent configurations', 'error');
      return false;
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }, [
    agentId,
    saving,
    initialSnapshot,
    name,
    status,
    language,
    recordingDisclosureEnabled,
    recordingDisclosureText,
    numberId,
    assigned,
    telephonyProfile,
    compliance,
    currentSnapshot,
    followup, followupRevision, followupAcknowledged,
    profileLoaded, profileError, complianceError,
    updateAgent,
    assignNumberToAgent,
    onSettingsSaved,
  ]);

  // Register handlers so parent modal or navigation can trigger atomic save or discard
  useEffect(() => {
    registerSaveHandler?.(handleSaveAll, handleDiscardAll);
  }, [registerSaveHandler, handleSaveAll, handleDiscardAll]);

  // Prevent accidental browser reload/close with unsaved changes
  useEffect(() => {
    const onBeforeUnload = (e) => {
      if (!isDirty) return;
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [isDirty]);

  const knownAgentIds = useMemo(() => new Set((agents || []).map((a) => a.id)), [agents]);
  const ownerOf = (n) =>
    n.assignedAgentId && knownAgentIds.has(n.assignedAgentId) ? n.assignedAgentId : null;
  const isTakenByOther = (n) => {
    const owner = ownerOf(n);
    return Boolean(owner && owner !== agentId);
  };

  const isActive = status === 'active';

  return (
    <div className="flex flex-col gap-4 pb-6">
      <SectionNav label="Settings sections" value={category} onChange={setCategory} variant="tiles"
        items={[
          ['all', 'All settings', LayoutGrid, 'Everything on one page'],
          ['identity', 'Agent & phone', Users, 'Name, language, on or off, and number'],
          ['routing', 'Call handling', PhoneCall, 'Business hours and where calls go'],
          ['followups', 'Follow-ups & scoring', PhoneCall, 'Callbacks, schedules and lead priority'],
          ['compliance', 'Recording & compliance', ShieldCheck, 'Recording notice and calling rules'],
        ]} />
      {profileError && <p role="alert" className="rounded-control border border-warning-line bg-warning-soft p-3 text-copy text-warning-fg">{profileError} Reload the page before saving so your current call settings are kept.</p>}
      {error && (
        <div
          role="alert"
          data-testid="agent-settings-error"
          className="rounded-control border border-danger-line bg-danger-soft px-3 py-2 text-ui text-danger-fg"
        >
          {error}
        </div>
      )}

      <fieldset disabled={readOnly || savingChanges || saving} className="console-categories settings-categories grid min-w-0 gap-4 items-start" data-category={category}>
      <div className="settings-primary flex min-w-0 flex-col gap-4">
      <div data-section="identity"><SolidCard>
        <h3 className="text-title text-ink mb-4">Name and language</h3>
        <div className="grid sm:grid-cols-2 gap-4">
          <label className="block">
            <span className="text-ui font-medium text-ink">Employee name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={255}
              data-testid="agent-settings-name"
              className="mt-1 w-full bg-canvas border border-line rounded-control px-3 py-2 text-base sm:text-ui min-h-[42px] sm:min-h-[36px] text-ink focus:border-accent focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="text-ui font-medium text-ink">Spoken language</span>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              data-testid="agent-settings-language"
              className="mt-1 w-full bg-canvas border border-line rounded-control px-3 py-2 text-base sm:text-ui min-h-[42px] sm:min-h-[36px] text-ink"
            >
              {LANGUAGE_OPTIONS.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
            <span className="block text-meta text-fg-muted mt-1">
              The language the employee speaks, including the greeting.
            </span>
          </label>
        </div>
      </SolidCard></div>

      <div data-section="identity"><SolidCard>
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-title text-ink">Taking calls</h3>
            <p className="text-ui text-fg-muted mt-0.5">
              When off, the employee keeps their script and number but won’t take browser or phone calls.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={isActive}
            aria-label="Taking calls"
            data-testid="agent-settings-toggle-status"
            onClick={() => setStatus(isActive ? 'paused' : 'active')}
            className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full border transition-colors ${
              isActive
                ? 'bg-success border-success'
                : 'bg-line-strong border-line-strong'
            }`}
          >
            <span
              className={`inline-block h-5 w-5 rounded-full bg-surface shadow transition-transform ${
                isActive ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
            <span className="sr-only">{isActive ? 'Live' : 'Paused'}</span>
          </button>
        </div>
        <div className="mt-3">
          <Badge tone={isActive ? 'success' : 'neutral'} dot>
            {isActive ? 'Live: taking calls' : 'Paused: not taking calls'}
          </Badge>
        </div>
      </SolidCard></div>

      <div data-section="identity"><SolidCard>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-4">
          <div>
            <h3 className="text-title text-ink">Phone number</h3>
            <p className="text-ui text-fg-muted mt-0.5">
              The number callers ring, and the number this employee calls from.
            </p>
          </div>
          <TactileButton
            variant="secondary"
            size="sm"
            icon={Phone}
            onClick={onOpenBuyNumber}
            data-testid="agent-settings-buy-number"
          >
            Buy a number
          </TactileButton>
        </div>
        <select
          value={numberId}
          onChange={(e) => setNumberId(e.target.value)}
          data-testid="agent-settings-number"
          aria-label="Assigned phone number"
          className="w-full bg-surface border border-line rounded-control px-3 py-2 text-base sm:text-ui min-h-[42px] sm:min-h-[36px] font-mono tabular-nums text-ink focus:border-accent focus:outline-none"
        >
          <option value="">No number (browser test calls only)</option>
          {phoneNumbers.map((n) => {
            const taken = isTakenByOther(n);
            const owner = ownerOf(n);
            return (
              <option key={n.id} value={n.id} disabled={taken}>
                {n.number}
                {taken ? ' (used by another employee)' : ''}
                {!owner ? ' · available' : ''}
              </option>
            );
          })}
        </select>
      </SolidCard></div>

      {/* Card 4: Operating Schedule & Inbound Routing (Single Controlled Telephony Card) */}
      {agentId && (
        <div data-section="routing" className="space-y-2">
          <TelephonySettingsCard
            agentId={agentId}
            profile={telephonyProfile}
            onChange={(patch) => {
              setTelephonyProfile((prev) => ({ ...prev, ...patch }));
              if (patch.greetingPhrase !== undefined) {
                onGreetingChange?.(patch.greetingPhrase);
              }
            }}
            hideSaveButton={true}
          />
        </div>
      )}

      </div>
      <div className="settings-secondary flex min-w-0 flex-col gap-4">
      <div data-section="compliance"><SolidCard className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-title text-ink">Call recording notice</h3>
            <p className="text-ui text-fg-muted mt-0.5">
              The employee says this once, after answering the caller’s first question, never in the greeting.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={recordingDisclosureEnabled}
            data-testid="agent-recording-disclosure-toggle"
            onClick={() => setRecordingDisclosureEnabled(!recordingDisclosureEnabled)}
            className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full border transition-colors ${
              recordingDisclosureEnabled
                ? 'bg-accent border-accent'
                : 'bg-line-strong border-line-strong'
            }`}
          >
            <span
              className={`inline-block h-5 w-5 rounded-full bg-surface shadow transition-transform ${
                recordingDisclosureEnabled ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
            <span className="sr-only">Enable recording disclosure</span>
          </button>
        </div>

        {recordingDisclosureEnabled && (
          <div className="space-y-3 pt-2 border-t border-line">
            <label className="block">
              <span className="text-ui font-medium text-ink">What the employee says</span>
              <textarea
                value={recordingDisclosureText}
                onChange={(e) => setRecordingDisclosureText(e.target.value)}
                rows={2}
                maxLength={255}
                data-testid="agent-recording-disclosure-text"
                placeholder="This call may be recorded for quality and training purposes."
                className="mt-1 w-full bg-canvas border border-line rounded-control px-3 py-2 text-ui text-ink focus:border-accent focus:outline-none"
              />
              <span className="mt-1 block text-right text-meta text-fg-muted">
                {recordingDisclosureText.length}/255
              </span>
            </label>
            <div className="rounded-control border border-line bg-canvas px-3 py-2">
              <p className="text-meta font-medium text-fg-muted">Preview</p>
              <p className="mt-1 text-ui text-ink">
                “{recordingDisclosureText.trim() || 'This call may be recorded for quality and training purposes.'}”
              </p>
            </div>
            <p className="text-meta text-fg-muted">
              Spoken in the call’s language. It is never added to the greeting, so callers hear a quick hello first.
            </p>
          </div>
        )}
      </SolidCard></div>

      <div data-section="compliance"><SolidCard>
        <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
          <div>
            <h3 className="text-title text-ink">India calling compliance</h3>
            <p className="text-ui text-fg-muted mt-0.5">
              A checklist for business calls made from India. Your ticks are saved with this employee;
              they are not a legal certificate.
            </p>
          </div>
          {complianceSummary && (
            <span
              data-testid="agent-compliance-regulation"
              className="max-w-full rounded-pill bg-surface-subtle border border-line px-2.5 py-1 text-meta font-medium text-fg-body"
            >
              {complianceSummary.countryName || complianceSummary.country} · {complianceSummary.regulation}
            </span>
          )}
        </div>

        {complianceLoading && (
          <p role="status" className="text-meta text-fg-muted">Loading calling requirements…</p>
        )}
        {complianceError && (
          <p role="alert" className="text-meta text-danger-fg" data-testid="agent-compliance-error">
            {complianceError}
          </p>
        )}

        {complianceSummary && (
          <>
            <p className="text-ui text-fg-body mb-3">{complianceSummary.summary}</p>
            <ul className="flex flex-col gap-3">
              {(complianceSummary.obligations || Object.keys(complianceSummary.acknowledged || compliance).map((key) => ({ key, label: humanizeToken(key) }))).map(({ key, label }) => {
                const on = Boolean(compliance[key]);
                return (
                  <li key={key} className="flex items-start justify-between gap-3">
                    <label className="flex items-start gap-2 text-ui leading-relaxed text-ink cursor-pointer">
                      <input
                        type="checkbox"
                        checked={on}
                        disabled={saving || complianceLoading}
                        onChange={(e) =>
                          setCompliance((prev) => ({ ...prev, [key]: e.target.checked }))
                        }
                        data-testid={`agent-compliance-${key}`}
                        className="mt-0.5 h-4 w-4 shrink-0 border-line accent-accent"
                      />
                      <span>{label}</span>
                    </label>
                  </li>
                );
              })}
            </ul>
            <p className="text-meta text-fg-muted mt-3">
              Saved with this employee. Calling rules are still checked on every call; ticking a box does
              not confirm consent or turn on the national Do Not Disturb check.
            </p>
            {complianceSummary.notes?.length > 0 && (
              <details className="mt-4 border-t border-line pt-3" data-testid="agent-compliance-guidance">
                <summary className="cursor-pointer text-ui font-medium text-fg-body focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4">
                  Indian rules and official sources
                </summary>
                <div className="mt-3 flex flex-col gap-2 text-meta leading-relaxed text-fg-body">
                  {complianceSummary.notes.map((note) => <p key={note}>{note}</p>)}
                  <ul className="flex flex-wrap gap-x-4 gap-y-2">
                    {(complianceSummary.sources || []).map((source) => (
                      <li key={source.url}><a href={source.url} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">{source.label}</a></li>
                    ))}
                  </ul>
                </div>
              </details>
            )}
          </>
        )}
      </SolidCard></div>
      </div>
      </fieldset>
      {['all', 'followups'].includes(category) && <fieldset disabled={readOnly || savingChanges || saving}><FollowUpSettingsCard config={followup} onChange={setFollowup} acknowledged={followupAcknowledged} onAcknowledge={setFollowupAcknowledged} needsConsent={Boolean(followup?.enabled && (!JSON.parse(initialSnapshot || '{}').followup?.enabled || (followup.callbackMode === 'automatic' && JSON.parse(initialSnapshot || '{}').followup?.callbackMode !== 'automatic') || (followup.missedMode === 'automatic' && JSON.parse(initialSnapshot || '{}').followup?.missedMode !== 'automatic')))} error={followupError} /></fieldset>}
    </div>
  );
}
