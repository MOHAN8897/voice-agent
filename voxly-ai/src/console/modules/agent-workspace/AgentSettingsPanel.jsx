import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Phone, Save, CheckCircle2, RotateCcw } from 'lucide-react';
import { SolidCard } from '../../ui/SolidCard';
import { StatusBadge } from '../../ui/StatusBadge';
import { TactileButton } from '../../ui/TactileButton';
import { useWorkspace } from '../../context/WorkspaceContext';
import { showToast } from '../../ui/ToastHost';
import { LANGUAGE_OPTIONS } from '../../../lib/voicePresets';
import { api } from '../../../services/api';
import { TelephonySettingsCard } from '../TelephonySettingsCard';

const DEFAULT_PROFILE = {
  greetingPhrase: '',
  businessHours: {},
  closedDates: [],
  timezone: 'America/New_York',
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
    technicalFallbackPromiseCallback: data?.technicalFallbackPromiseCallback !== false,
    technicalFallbackText: (data?.technicalFallbackText || '').trim(),
    telephonyProfile: {
      greetingPhrase: (data?.telephonyProfile?.greetingPhrase || '').trim(),
      businessHours: data?.telephonyProfile?.businessHours || {},
      closedDates: Array.isArray(data?.telephonyProfile?.closedDates) ? data.telephonyProfile.closedDates : [],
      timezone: data?.telephonyProfile?.timezone || 'America/New_York',
      afterHoursAction: data?.telephonyProfile?.afterHoursAction || 'voicemail',
      transferNumber: (data?.telephonyProfile?.transferNumber || '').trim(),
      inboundEnabled: data?.telephonyProfile?.inboundEnabled !== false,
      outboundEnabled: data?.telephonyProfile?.outboundEnabled !== false,
    },
    compliance: data?.compliance || {},
  };
}

const FALLBACK_VARIANTS = [
  { id: 'callback_promise', label: 'Callback promise' },
  { id: 'call_back', label: 'Call-back request' },
  { id: 'disclosure', label: 'Recording disclosure' },
];

function FallbackAnnouncementClips({ agentId, languages, primaryLanguage, noteText }) {
  const [clips, setClips] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [busyKey, setBusyKey] = useState('');

  const refresh = useCallback(async () => {
    if (!agentId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.agents.listFallbackClips(agentId);
      setClips(data.clips);
    } catch (e) {
      setError(e?.message || 'Could not load recorded announcements.');
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const findClip = (language, variant) =>
    clips.find(
      (clip) =>
        String(clip.language).toLowerCase() === language.toLowerCase() &&
        clip.variant === variant
    );

  const hasCustomTechnical = FALLBACK_VARIANTS.filter((v) => v.id !== 'disclosure').some(
    (v) => findClip(primaryLanguage, v.id)
  );

  const handleUpload = async (language, variant, file) => {
    if (!file) return;
    const key = `${language}:${variant}`;
    setBusyKey(key);
    setError(null);
    try {
      await api.agents.uploadFallbackClip(agentId, language, variant, file);
      await refresh();
      showToast('Recorded announcement saved', 'success');
    } catch (e) {
      setError(e?.message || 'Could not save that recording.');
    } finally {
      setBusyKey('');
    }
  };

  const handleDelete = async (language, variant) => {
    const key = `${language}:${variant}`;
    setBusyKey(key);
    setError(null);
    try {
      await api.agents.deleteFallbackClip(agentId, language, variant);
      await refresh();
      showToast('Custom recording removed — the platform recording is used', 'info');
    } catch (e) {
      setError(e?.message || 'Could not remove that recording.');
    } finally {
      setBusyKey('');
    }
  };

  return (
    <div className="space-y-3 pt-2 border-t border-[#E4E2EB]">
      <div>
        <p className="text-[11px] font-bold text-[#0F0E17]">Recorded announcements per language</p>
        <p className="text-[10px] text-[#8C879A] mt-0.5">
          A platform recording is used by default. Upload your own WAV (16-bit PCM, up to 2 MB or 30 s) to
          replace it — the text above is never spoken during an outage.
        </p>
      </div>
      {noteText.trim() && !hasCustomTechnical && (
        <p
          data-testid="agent-fallback-text-needs-clip"
          className="rounded-xl border border-[#F0C36D] bg-[#FFF8E8] px-3 py-2 text-[11px] text-[#7A5B12]"
        >
          This text needs a recorded audio file to be used during a TTS outage.
        </p>
      )}
      {error && (
        <p role="alert" className="text-[11px] text-[#B42318]">
          {error}
        </p>
      )}
      {loading && <p className="text-[11px] text-[#8C879A]">Loading recordings…</p>}
      {languages.map((language) => (
        <div key={language} className="rounded-xl border border-[#E4E2EB] bg-[#FAF9FD] p-3 space-y-2">
          <p className="text-[11px] font-bold text-[#0F0E17]">{language}</p>
          {FALLBACK_VARIANTS.map((variant) => {
            const key = `${language}:${variant.id}`;
            const clip = findClip(language, variant.id);
            const busy = busyKey === key;
            return (
              <div key={variant.id} className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[11px] text-[#0F0E17]">{variant.label}</p>
                  <p className="text-[10px] text-[#8C879A]">
                    {clip ? `Your recording · ${Math.round((clip.durationMs || 0) / 1000)}s` : 'Platform recording'}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <label
                    data-testid={`agent-fallback-upload-${variant.id}-${language}`}
                    className={`cursor-pointer rounded-lg border border-[#E4E2EB] bg-white px-2.5 py-1.5 text-[10px] font-semibold text-[#524E5E] hover:border-[#6344E7] ${
                      busy ? 'pointer-events-none opacity-60' : ''
                    }`}
                  >
                    {clip ? 'Replace' : 'Upload'}
                    <input
                      type="file"
                      accept="audio/wav,audio/x-wav,.wav"
                      className="hidden"
                      disabled={busy}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        e.target.value = '';
                        handleUpload(language, variant.id, file);
                      }}
                    />
                  </label>
                  {clip && (
                    <button
                      type="button"
                      disabled={busy}
                      data-testid={`agent-fallback-delete-${variant.id}-${language}`}
                      onClick={() => handleDelete(language, variant.id)}
                      className="rounded-lg border border-[#E4E2EB] bg-white px-2.5 py-1.5 text-[10px] font-semibold text-[#B42318] hover:border-[#B42318] disabled:opacity-60"
                    >
                      Remove
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

/**
 * Unified Agent Settings Panel.
 *
 * Holds all configuration sections (Identity, Status, Number, Operating Schedule & Greeting,
 * Call Recording & Disclosure, Compliance) in memory with ZERO database writes until
 * the single primary "Save Agent Settings" button is clicked.
 */
export function AgentSettingsPanel({
  agent,
  agentGreeting,
  onGreetingChange,
  onOpenBuyNumber,
  onDirtyChange,
  registerSaveHandler,
  onSettingsSaved,
}) {
  const { phoneNumbers, agents, assignNumberToAgent, updateAgent } = useWorkspace();
  const agentId = agent?.id;

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
  const [technicalFallbackPromiseCallback, setTechnicalFallbackPromiseCallback] = useState(
    agent?.technicalFallbackPromiseCallback !== false
  );
  const [technicalFallbackText, setTechnicalFallbackText] = useState(
    agent?.technicalFallbackText || ''
  );
  const [telephonyProfile, setTelephonyProfile] = useState(() => ({
    ...DEFAULT_PROFILE,
    greetingPhrase: agentGreeting || '',
  }));
  const [compliance, setCompliance] = useState({});
  const [complianceSummary, setComplianceSummary] = useState(null);
  const [complianceLoading, setComplianceLoading] = useState(false);
  const [complianceError, setComplianceError] = useState(null);

  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  const fallbackLanguages = useMemo(() => {
    const list = Array.isArray(agent?.languages) && agent.languages.length ? agent.languages : [language];
    return Array.from(new Set([language, ...list].filter(Boolean)));
  }, [agent?.languages, language]);

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
    if (!agentId) return;

    setName(agent?.name || '');
    setLanguage((agent?.languages && agent.languages[0]) || agent?.language || 'en-IN');
    setStatus(agent?.status || 'active');
    setNumberId(currentNumberId);
    setRecordingDisclosureEnabled(Boolean(agent?.recordingDisclosureEnabled));
    setRecordingDisclosureText(
      agent?.recordingDisclosureText || 'This call may be recorded for quality and training purposes.'
    );
    setTechnicalFallbackPromiseCallback(agent?.technicalFallbackPromiseCallback !== false);
    setTechnicalFallbackText(agent?.technicalFallbackText || '');

    let cancelled = false;
    setComplianceLoading(true);

    Promise.all([
      api.telephony.getAgentCompliance(agentId).catch((e) => {
        if (!cancelled) setComplianceError(e?.message || 'Could not load compliance obligations');
        return null;
      }),
      api.agents.getTelephonyProfile(agentId).catch(() => ({ profile: {} })),
    ]).then(([compData, profData]) => {
      if (cancelled) return;
      const loadedComp = compData?.acknowledged || {};
      const rawProf = profData?.profile || {};
      const loadedProf = {
        ...DEFAULT_PROFILE,
        ...rawProf,
        greetingPhrase: agentGreeting !== undefined && agentGreeting !== '' ? agentGreeting : (rawProf.greetingPhrase || ''),
      };

      setCompliance(loadedComp);
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
        technicalFallbackPromiseCallback: agent?.technicalFallbackPromiseCallback !== false,
        technicalFallbackText: agent?.technicalFallbackText || '',
        telephonyProfile: loadedProf,
        compliance: loadedComp,
      });
      setInitialSnapshot(JSON.stringify(snap));
    });

    return () => {
      cancelled = true;
    };
  }, [agentId, agent?.name, agent?.status, agent?.language, agent?.recordingDisclosureEnabled, agent?.recordingDisclosureText, agent?.technicalFallbackPromiseCallback, agent?.technicalFallbackText, currentNumberId]);

  // Current state snapshot
  const currentSnapshot = useMemo(() => {
    return cleanSnapshot({
      name,
      language,
      status,
      numberId,
      recordingDisclosureEnabled,
      recordingDisclosureText,
      technicalFallbackPromiseCallback,
      technicalFallbackText,
      telephonyProfile,
      compliance,
    });
  }, [name, language, status, numberId, recordingDisclosureEnabled, recordingDisclosureText, technicalFallbackPromiseCallback, technicalFallbackText, telephonyProfile, compliance]);

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
      setTechnicalFallbackPromiseCallback(restored.technicalFallbackPromiseCallback !== false);
      setTechnicalFallbackText(restored.technicalFallbackText || '');
      setTelephonyProfile(restored.telephonyProfile);
      setCompliance(restored.compliance);
      setError(null);
      showToast('Settings changes discarded', 'info');
    } catch {
      /* ignore */
    }
  }, [initialSnapshot]);

  const handleSaveAll = useCallback(async () => {
    if (!agentId || saving) return false;
    setSaving(true);
    setError(null);

    try {
      const baseSnapshot = initialSnapshot ? JSON.parse(initialSnapshot) : {};

      // 1. Update Agent identity, status, and recording disclosures in a single call
      await updateAgent(agentId, {
        name: name.trim(),
        status,
        languages: [language],
        recordingDisclosureEnabled,
        recordingDisclosureText: recordingDisclosureText.trim(),
        technicalFallbackPromiseCallback,
        technicalFallbackText: technicalFallbackText.trim(),
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
      await api.agents.saveTelephonyProfile(agentId, {
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

      // 5. Keep voice-section language in sync
      try {
        const brain = await api.agents.getBusinessBrain(agentId);
        const voice = brain?.voice || {};
        await api.agents.saveVoice(agentId, {
          voiceId: voice.voiceId || voice.realtimeVoice || 'marin',
          speed: voice.speed ?? 1,
          language,
        });
      } catch {
        /* Language still applies via agent row */
      }

      // Update baseline snapshot
      const updatedSnapshot = JSON.stringify(currentSnapshot);
      setInitialSnapshot(updatedSnapshot);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
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
    <div className="space-y-5 pb-6">
      {error && (
        <div
          role="alert"
          data-testid="agent-settings-error"
          className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900"
        >
          {error}
        </div>
      )}

      {/* Card 1: Identity */}
      <SolidCard>
        <h3 className="text-xs font-bold text-[#0F0E17] mb-4">Identity</h3>
        <div className="grid sm:grid-cols-2 gap-4">
          <label className="block">
            <span className="text-[11px] font-bold text-[#0F0E17]">Agent name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={255}
              data-testid="agent-settings-name"
              className="mt-1 w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-base sm:text-xs min-h-[42px] sm:min-h-[36px] text-[#0F0E17] focus:border-[#6344E7] focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="text-[11px] font-bold text-[#0F0E17]">Spoken language</span>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              data-testid="agent-settings-language"
              className="mt-1 w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-base sm:text-xs min-h-[42px] sm:min-h-[36px] text-[#0F0E17]"
            >
              {LANGUAGE_OPTIONS.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
            <span className="block text-[10px] text-[#8C879A] mt-1">
              Sets the language the agent speaks and its opening line.
            </span>
          </label>
        </div>
      </SolidCard>

      {/* Card 2: Live / Pause Switch */}
      <SolidCard>
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-xs font-bold text-[#0F0E17]">Live / Pause</h3>
            <p className="text-[11px] text-[#524E5E] mt-0.5">
              Off = agent keeps script and number but will not take browser or phone calls.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={isActive}
            data-testid="agent-settings-toggle-status"
            onClick={() => setStatus(isActive ? 'paused' : 'active')}
            className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full border transition-colors ${
              isActive
                ? 'bg-emerald-500 border-emerald-600'
                : 'bg-[#D1CFDB] border-[#C4C0D0]'
            }`}
          >
            <span
              className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${
                isActive ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
            <span className="sr-only">{isActive ? 'Live' : 'Paused'}</span>
          </button>
        </div>
        <p className="mt-2 text-[11px] font-semibold text-[#0F0E17]">
          {isActive ? 'Live — accepting calls' : 'Paused — calls blocked'}
        </p>
      </SolidCard>

      {/* Card 3: Phone number selection */}
      <SolidCard>
        <div className="flex items-center justify-between gap-3 mb-4">
          <div>
            <h3 className="text-xs font-bold text-[#0F0E17]">Phone number</h3>
            <p className="text-[11px] text-[#524E5E] mt-0.5">
              The line callers reach, and the caller ID this agent dials from.
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
          className="w-full bg-white border border-[#E4E2EB] rounded-xl px-3 py-2 text-base sm:text-xs min-h-[42px] sm:min-h-[36px] font-mono text-[#0F0E17]"
        >
          <option value="">No number — browser test calls only</option>
          {phoneNumbers.map((n) => {
            const taken = isTakenByOther(n);
            const owner = ownerOf(n);
            return (
              <option key={n.id} value={n.id} disabled={taken}>
                {n.number}
                {taken ? ' (assigned elsewhere)' : ''}
                {!owner ? ' · available' : ''}
              </option>
            );
          })}
        </select>
      </SolidCard>

      {/* Card 4: Operating Schedule & Inbound Routing (Single Controlled Telephony Card) */}
      {agentId && (
        <div className="space-y-2">
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

      {/* Card 5: Call Recording & Disclosure */}
      <SolidCard className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-xs font-bold text-[#0F0E17]">Call Recording &amp; Disclosure</h3>
            <p className="text-[11px] text-[#524E5E] mt-0.5">
              The agent says this naturally, once, after answering the caller&apos;s first point — never in the opening greeting.
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
                ? 'bg-[#FF5C35] border-[#FF5C35]'
                : 'bg-[#D1CFDB] border-[#C4C0D0]'
            }`}
          >
            <span
              className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${
                recordingDisclosureEnabled ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
            <span className="sr-only">Enable recording disclosure</span>
          </button>
        </div>

        {recordingDisclosureEnabled && (
          <div className="space-y-3 pt-2 border-t border-[#E4E2EB]">
            <label className="block">
              <span className="text-[11px] font-bold text-[#0F0E17]">Disclosure script:</span>
              <textarea
                value={recordingDisclosureText}
                onChange={(e) => setRecordingDisclosureText(e.target.value)}
                rows={2}
                maxLength={255}
                data-testid="agent-recording-disclosure-text"
                placeholder="This call may be recorded for quality and training purposes."
                className="mt-1 w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs text-[#0F0E17] focus:border-[#6344E7] focus:outline-none"
              />
              <span className="mt-1 block text-right text-[10px] text-[#8C879A]">
                {recordingDisclosureText.length}/255
              </span>
            </label>
            <div className="rounded-xl border border-[#E4E2EB] bg-[#FAF9FD] px-3 py-2">
              <p className="text-[10px] font-bold uppercase tracking-wide text-[#8C879A]">Call preview</p>
              <p className="mt-1 text-[11px] text-[#0F0E17]">
                “{recordingDisclosureText.trim() || 'This call may be recorded for quality and training purposes.'}”
              </p>
            </div>
            <p className="text-[10px] text-[#8C879A]">
              Spoken in the call&apos;s language. Zero legal disclaimers play in the sub-500ms prewarm greeting.
            </p>
          </div>
        )}
      </SolidCard>

      {/* Card 5b: TTS Outage Announcement */}
      <SolidCard className="space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-xs font-bold text-[#0F0E17]">TTS Outage Announcement</h3>
            <p className="text-[11px] text-[#524E5E] mt-0.5">
              A pre-recorded message played only when the speech service fails mid-call, so the caller hears
              a professional apology instead of silence.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={technicalFallbackPromiseCallback}
            data-testid="agent-fallback-promise-toggle"
            onClick={() => setTechnicalFallbackPromiseCallback(!technicalFallbackPromiseCallback)}
            className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full border transition-colors ${
              technicalFallbackPromiseCallback
                ? 'bg-[#FF5C35] border-[#FF5C35]'
                : 'bg-[#D1CFDB] border-[#C4C0D0]'
            }`}
          >
            <span
              className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${
                technicalFallbackPromiseCallback ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
            <span className="sr-only">Promise the caller a callback</span>
          </button>
        </div>

        <div className="rounded-xl border border-[#E4E2EB] bg-[#FAF9FD] px-3 py-2">
          <p className="text-[10px] font-bold uppercase tracking-wide text-[#8C879A]">Callback promise</p>
          <p className="mt-1 text-[11px] text-[#0F0E17]">
            {technicalFallbackPromiseCallback
              ? '“We will call you again.” A callback task is saved before this plays; if it cannot be saved, the call-back request recording is used instead.'
              : '“Please call us back.” Used when no callback task will be created.'}
          </p>
        </div>

        <label className="block">
          <span className="text-[11px] font-bold text-[#0F0E17]">Announcement transcript:</span>
          <textarea
            value={technicalFallbackText}
            onChange={(e) => setTechnicalFallbackText(e.target.value)}
            rows={2}
            maxLength={255}
            data-testid="agent-fallback-text"
            placeholder="Stored with the call record when you upload your own recording."
            className="mt-1 w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs text-[#0F0E17] focus:border-[#6344E7] focus:outline-none"
          />
          <span className="mt-1 block text-right text-[10px] text-[#8C879A]">
            {technicalFallbackText.length}/255
          </span>
        </label>
        <p className="text-[10px] text-[#8C879A]">
          Typed text is not synthesized during an outage. The platform recording or your uploaded clip is what
          the caller hears.
        </p>

        {agentId && (
          <FallbackAnnouncementClips
            agentId={agentId}
            languages={fallbackLanguages}
            primaryLanguage={language}
            noteText={technicalFallbackText}
          />
        )}
      </SolidCard>

      {/* Card 6: Compliance Obligations */}
      <SolidCard>
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h3 className="text-xs font-bold text-[#0F0E17]">Compliance</h3>
            <p className="text-[11px] text-[#524E5E] mt-0.5">
              Obligations for the market this agent numbers in. Confirm each one you meet.
            </p>
          </div>
          {complianceSummary && (
            <span
              data-testid="agent-compliance-regulation"
              className="shrink-0 rounded-full bg-[#F0EEF6] border border-[#E4E2EB] px-2.5 py-1 text-[10px] font-semibold text-[#524E5E]"
            >
              {complianceSummary.country} · {complianceSummary.regulation}
            </span>
          )}
        </div>

        {complianceLoading && (
          <p className="text-[11px] text-[#8C879A]">Loading obligations…</p>
        )}
        {complianceError && (
          <p className="text-[11px] text-red-600" data-testid="agent-compliance-error">
            {complianceError}
          </p>
        )}

        {complianceSummary && (
          <>
            <p className="text-[11px] text-[#524E5E] mb-3">{complianceSummary.summary}</p>
            <ul className="space-y-2">
              {Object.keys(complianceSummary.acknowledged || compliance).map((key) => {
                const on = Boolean(compliance[key]);
                return (
                  <li key={key} className="flex items-start justify-between gap-3">
                    <label className="flex items-start gap-2 text-[12px] text-[#0F0E17] capitalize cursor-pointer">
                      <input
                        type="checkbox"
                        checked={on}
                        onChange={(e) =>
                          setCompliance((prev) => ({ ...prev, [key]: e.target.checked }))
                        }
                        data-testid={`agent-compliance-${key}`}
                        className="mt-0.5 h-4 w-4 shrink-0 rounded border-[#E4E2EB]"
                      />
                      <span>{key.replace(/_/g, ' ')}</span>
                    </label>
                  </li>
                );
              })}
            </ul>
            <p className="text-[10px] text-[#8C879A] mt-3">
              Recorded against this agent. These are notes for your compliance review — they do
              not change how calls are placed.
            </p>
          </>
        )}
      </SolidCard>

      {/* SINGLE UNIFIED SAVE BAR FOR ENTIRE SETTINGS PAGE */}
      <div className="sticky bottom-3 z-20 flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-2xl bg-white/95 backdrop-blur-md border border-[#E4E2EB] shadow-lg">
        <div className="flex items-center gap-3">
          <StatusBadge status={isActive ? 'Active' : 'Paused'} size="xs" />
          {isDirty ? (
            <span className="text-xs font-semibold text-[#B45309] flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#B45309] animate-pulse" />
              Unsaved changes in agent settings
            </span>
          ) : (
            <span className="text-xs text-[#8C879A]">All configurations saved</span>
          )}
        </div>

        <div className="flex items-center gap-2.5 ml-auto">
          {isDirty && (
            <TactileButton
              variant="secondary"
              size="sm"
              icon={RotateCcw}
              onClick={handleDiscardAll}
              disabled={saving}
              data-testid="agent-settings-discard"
            >
              Discard changes
            </TactileButton>
          )}

          <TactileButton
            variant="primary"
            size="sm"
            icon={saved ? CheckCircle2 : Save}
            onClick={handleSaveAll}
            loading={saving}
            disabled={saving || !isDirty}
            data-testid="agent-settings-save"
            className="min-h-[38px] px-5"
          >
            {saved ? 'Saved!' : saving ? 'Saving…' : 'Save Agent Settings'}
          </TactileButton>
        </div>
      </div>
    </div>
  );
}