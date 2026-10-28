import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  Mic,
  MicOff,
  Pause,
  PhoneCall,
  PhoneOff,
  Play,
  Radio,
  Wallet,
  Zap,
} from 'lucide-react';
import { useWorkspace } from '../../context/WorkspaceContext';
import { TactileButton } from '../../ui/TactileButton';
import { SolidCard } from '../../ui/SolidCard';
import { LazyVoxlyScene } from '../../../three/LazyVoxlyScene';
import { createWebAgentSession } from '../../../services/webAgentClient';
import { showToast } from '../../ui/ToastHost';

function formatElapsed(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

/**
 * Live test call: browser mic or live-number dial.
 * Same AI path as production phone. Call chrome + 3D speaking avatar + timer.
 */
export function AgentTestCallPanel({ agent, language, pricingProfile }) {
  const {
    wallet,
    refreshWallet,
    openAddFunds,
    placeOutboundCall,
    phoneNumbers,
    outboundFromE164,
    toggleAgentStatus,
  } = useWorkspace();
  const [mode, setMode] = useState('browser');
  const [sessionState, setSessionState] = useState('DISCONNECTED');
  const [botState, setBotState] = useState('IDLE');
  const [isMuted, setIsMuted] = useState(false);
  const [statusNote, setStatusNote] = useState('');
  const [lines, setLines] = useState([]);
  const [toE164, setToE164] = useState('');
  const [dialBusy, setDialBusy] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [audioAmplitude, setAudioAmplitude] = useState(0.06);
  const [statusBusy, setStatusBusy] = useState(false);
  const sessionRef = useRef(null);
  const endRef = useRef(null);
  const startedAtRef = useRef(null);
  const speakingUntilRef = useRef(0);
  const dialRef = useRef(false);

  const isLive = sessionState === 'CONNECTED' || sessionState === 'CONNECTING';
  const balanceUsd = Number(wallet?.balanceUsd) || 0;
  const balanceInr = Number(wallet?.balanceInr) || 0;
  const fx = Number(wallet?.fxRateInr) || 95.64;
  const displayUsd =
    balanceUsd > 0 ? balanceUsd : balanceInr > 0 ? balanceInr / fx : 0;
  const walletEmpty = displayUsd <= 0 && balanceInr <= 0 && balanceUsd <= 0;
  const isActive = agent?.status === 'active';

  const agentTier = useMemo(() => {
    return String(agent?.default_tier || agent?.defaultTier || agent?.tier || 'medium').toLowerCase();
  }, [agent]);

  const activeRateInr = useMemo(() => {
    if (mode === 'browser') {
      return pricingProfile?.webRetailRate?.inrPaisePerMin != null ? Number(pricingProfile.webRetailRate.inrPaisePerMin) / 100 : Number(wallet?.webTierRates?.[agentTier]?.inrPerMin ?? wallet?.webRateInrPerMin ?? 0);
    }
    const directRate = wallet?.tierRates?.[agentTier]?.inrPerMin;
    if (directRate != null && Number(directRate) > 0) return Number(directRate);
    const parentTier = (agentTier.startsWith('low') || agentTier.includes('economical') || agentTier.includes('budget'))
      ? 'low'
      : (agentTier.startsWith('prem') || agentTier.includes('flagship') || agentTier.includes('high'))
      ? 'premium'
      : 'medium';
    const parentRate = wallet?.tierRates?.[parentTier]?.inrPerMin;
    if (parentRate != null && Number(parentRate) > 0) return Number(parentRate);
    if (parentTier === 'low' && wallet?.pstnLowRateInrPerMin) return Number(wallet.pstnLowRateInrPerMin);
    if (parentTier === 'medium' && wallet?.pstnMediumRateInrPerMin) return Number(wallet.pstnMediumRateInrPerMin);
    if (parentTier === 'premium' && wallet?.pstnPremiumRateInrPerMin) return Number(wallet.pstnPremiumRateInrPerMin);
    return Number(wallet?.rateInrPerMin ?? 0);
  }, [mode, agentTier, wallet, pricingProfile]);

  const activeRateUsd = useMemo(() => {
    if (mode === 'browser') {
      return pricingProfile?.webRetailRate?.usdMicrosPerMin != null ? Number(pricingProfile.webRetailRate.usdMicrosPerMin) / 1000000 : Number(wallet?.webTierRates?.[agentTier]?.usdPerMin ?? wallet?.webRateUsdPerMin ?? 0);
    }
    const directRate = wallet?.tierRates?.[agentTier]?.usdPerMin;
    if (directRate != null && Number(directRate) > 0) return Number(directRate);
    const parentTier = (agentTier.startsWith('low') || agentTier.includes('economical') || agentTier.includes('budget'))
      ? 'low'
      : (agentTier.startsWith('prem') || agentTier.includes('flagship') || agentTier.includes('high'))
      ? 'premium'
      : 'medium';
    const parentRate = wallet?.tierRates?.[parentTier]?.usdPerMin;
    if (parentRate != null && Number(parentRate) > 0) return Number(parentRate);
    return Number(wallet?.rateUsdPerMin ?? 0);
  }, [mode, agentTier, wallet, pricingProfile]);
  const rateAvailable = Number.isFinite(activeRateInr) && activeRateInr > 0 && Number.isFinite(activeRateUsd) && activeRateUsd > 0;
  const remainingMinutes = rateAvailable ? Math.floor(balanceInr > 0 ? balanceInr / activeRateInr : displayUsd / activeRateUsd) : null;

  // Find the agent's assigned phone line
  const assignedLine = useMemo(() => {
    const fromList = phoneNumbers.find(
      (n) => (agent?.id && n.assignedAgentId === agent.id) || (agent?.numberId && n.id === agent.numberId)
    );
    if (fromList) return fromList;
    return null;
  }, [phoneNumbers, agent]);

  // All valid outbound numbers available to this agent/workspace
  const availableOutboundNumbers = useMemo(() => {
    // 1. Gather all tenant numbers that are not released or failed
    const valid = phoneNumbers.filter(
      (n) => ['active', 'provisioned'].includes(n.status || 'active') && n.outboundEnabled !== false && (n.e164 || n.number)
    );

    // 2. Ensure assignedLine is included even if phoneNumbers list hasn't finished syncing
    const list = [...valid];
    if (assignedLine && valid.includes(assignedLine)) {
      const assignedVal = assignedLine.e164 || assignedLine.number;
      if (!list.some((n) => (n.e164 || n.number) === assignedVal)) {
        list.unshift(assignedLine);
      }
    }

    // 3. Sort assigned line directly to the top (index 0)
    if (assignedLine) {
      const assignedVal = assignedLine.e164 || assignedLine.number;
      list.sort((a, b) => {
        const aVal = a.e164 || a.number;
        const bVal = b.e164 || b.number;
        if (aVal === assignedVal) return -1;
        if (bVal === assignedVal) return 1;
        return 0;
      });
    }

    return list;
  }, [phoneNumbers, assignedLine]);

  // Default to the agent's dedicated assigned line first, then workspace outboundFromE164, then first available
  const defaultFromLine = useMemo(() => {
    if (assignedLine && availableOutboundNumbers.includes(assignedLine)) return assignedLine.e164 || assignedLine.number || '';
    if (availableOutboundNumbers.some((n) => (n.e164 || n.number) === outboundFromE164)) return outboundFromE164;
    return availableOutboundNumbers[0]?.e164 || availableOutboundNumbers[0]?.number || '';
  }, [assignedLine, outboundFromE164, availableOutboundNumbers]);

  const [selectedFromLine, setSelectedFromLine] = useState('');
  const activeFromLine = availableOutboundNumbers.some((n) => (n.e164 || n.number) === selectedFromLine) ? selectedFromLine : defaultFromLine;

  useEffect(() => () => {
    sessionRef.current?.stop();
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [lines]);

  useEffect(() => {
    // CONNECTING has no start stamp, so the clock stays at 00:00 until `ready` lands.
  if (!isLive || !startedAtRef.current) {
      setElapsedMs(0);
      return undefined;
    }
    const tick = () => setElapsedMs(Date.now() - startedAtRef.current);
    tick();
    const id = setInterval(tick, 250);
    return () => clearInterval(id);
  }, [isLive, sessionState]);

  useEffect(() => {
    let frame;
    const loop = () => {
      const speaking = Date.now() < speakingUntilRef.current || botState === 'SPEAKING';
      if (sessionState === 'CONNECTED' && speaking) {
        setBotState('SPEAKING');
        setAudioAmplitude(0.55 + Math.random() * 0.35);
      } else if (sessionState === 'CONNECTED') {
        setBotState('LISTENING');
        setAudioAmplitude(0.22 + Math.random() * 0.08);
      } else if (sessionState === 'CONNECTING') {
        setAudioAmplitude(0.18 + Math.random() * 0.1);
      } else {
        setAudioAmplitude(0.06);
      }
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [sessionState, botState]);

  const push = (text, role = 'system') => {
    setLines((prev) => [...prev, { id: `${Date.now()}-${prev.length}`, role, text }]);
  };

  const requireWallet = () => {
    if (!walletEmpty) return true;
    showToast('Add wallet funds before testing. Sessions are billed from your balance.', 'error');
    openAddFunds?.('Your wallet is empty — add funds to start a test call.');
    return false;
  };

  const requireLive = async () => {
    if (isActive) return true;
    if (mode === 'browser' && toggleAgentStatus && agent?.id) {
      try {
        await toggleAgentStatus(agent.id, 'active');
        return true;
      } catch {
        /* fallback */
      }
    }
    showToast('Agent is paused. Switch to Live before testing.', 'error');
    return false;
  };

  const startBrowser = async () => {
    if (!agent?.id) return;
    const liveOk = await requireLive();
    if (!liveOk || !requireWallet()) return;
    if (sessionRef.current) {
      try {
        sessionRef.current.stop();
      } catch {
        /* ignore */
      }
      sessionRef.current = null;
    }
    const session = createWebAgentSession();
    try {
      // Unlock speaker output during the original click, before agent activation
      // or microphone permission checks can await and expire browser activation.
      session.prepareAudio();
    } catch (error) {
      setStatusNote(error.message || 'Browser audio is unavailable.');
      showToast(error.message || 'Browser audio is unavailable.', 'error');
      session.stop();
      return;
    }
    sessionRef.current = session;
    setSessionState('CONNECTING');
    setBotState('THINKING');
    setLines([]);
    setIsMuted(false);
    setElapsedMs(0);
    // The clock starts on `ready` (server accepted the session and the voice loop is
    // live), not here — time spent handshaking is not billed time.
    startedAtRef.current = null;
    setStatusNote('Connecting to agent…');
    session.subscribe((event, data) => {
      if (event === 'ready') {
        setSessionState('CONNECTED');
        startedAtRef.current = Date.now();
        speakingUntilRef.current = Date.now();
        setStatusNote(data?.microphoneMode === 'listen-only'
          ? 'Connected in listen-only mode — allow microphone access to speak.'
          : 'Connected — microphone and agent are live');
        push('Live session started. Agent follows your published script.');
      }
      if (event === 'audio') {
        speakingUntilRef.current = Date.now() + 400;
        setBotState('SPEAKING');
      }
      if (event === 'hangup_initiated') {
        setStatusNote('Agent is ending the call…');
        push('Hangup started.');
      }
      if (event === 'hangup_complete' || event === 'closed') {
        setSessionState('DISCONNECTED');
        setBotState('IDLE');
        startedAtRef.current = null;
        setStatusNote('Call ended — usage deducted from wallet');
        refreshWallet?.();
        setTimeout(() => refreshWallet?.(), 1500);
      }
      if (event === 'error') {
        setSessionState('DISCONNECTED');
        setBotState('IDLE');
        startedAtRef.current = null;
        const msg = data?.message || 'Could not start live voice';
        setStatusNote(msg);
        showToast(msg, 'error');
        if (/wallet|balance|funds|credit/i.test(msg)) openAddFunds?.(msg);
      }
    });
    try {
      await session.start({
        agentId: agent.id,
        language: language || (agent.languages && agent.languages[0]) || agent.language || 'en-IN',
      });
    } catch (error) {
      setSessionState('DISCONNECTED');
      setBotState('IDLE');
      startedAtRef.current = null;
      setStatusNote(error.message || 'Failed');
      showToast(error.message || 'Could not start', 'error');
      if (/wallet|balance|funds|credit/i.test(error.message || '')) {
        openAddFunds?.(error.message);
      }
    }
  };

  const endBrowser = () => {
    sessionRef.current?.stop();
    sessionRef.current = null;
    setSessionState('DISCONNECTED');
    setBotState('IDLE');
    setIsMuted(false);
    startedAtRef.current = null;
    setStatusNote('You ended the session.');
    refreshWallet?.();
    setTimeout(() => refreshWallet?.(), 1500);
  };

  const dialPhone = async () => {
    if (!agent?.id || dialRef.current) return;
    const liveOk = await requireLive();
    if (!liveOk || !requireWallet()) return;
    if (!activeFromLine) {
      showToast('Enable outgoing calls on a phone line in Phone lines before calling.', 'error');
      return;
    }
    const rawDest = toE164.trim();
    if (!rawDest) {
      showToast('Enter a phone number with country code (e.g. +91 98765 43210).', 'error');
      return;
    }
    // Clean spaces, hyphens, and parentheses
    let cleanDest = rawDest.replace(/[\s()-]/g, '');
    if (!/^(?:\+|00)?\d+$/.test(cleanDest)) {
      showToast('Use digits and a country code, such as +91.', 'error');
      return;
    }
    if (cleanDest.startsWith('00')) cleanDest = '+' + cleanDest.slice(2);
    if (!cleanDest.startsWith('+')) {
      const digits = cleanDest.replace(/\D/g, '');
      if (digits.length === 10) {
        cleanDest = `+91${digits}`; // Default to +91 for standard 10-digit Indian input
      } else {
        cleanDest = `+${digits}`;
      }
    }
    if (!/^\+[1-9]\d{7,14}$/.test(cleanDest)) {
      showToast('Please enter a valid phone number with country code (e.g. +91 98765 43210).', 'error');
      return;
    }
    dialRef.current = true;
    setDialBusy(true);
    try {
      await placeOutboundCall({
        agentId: agent.id,
        toE164: cleanDest,
        fromE164: activeFromLine || null,
      });
      showToast('Live call initiated', 'success');
      push(`Dialing ${cleanDest}…`);
      setStatusNote(`Calling ${cleanDest} — agent is speaking from its published script`);
    } catch (e) {
      const msg = e.message || 'Could not place call';
      showToast(msg, 'error');
      push(`Call attempt failed: ${msg}`, 'system');
      if (/wallet|balance|funds|402/i.test(msg)) openAddFunds?.(msg);
    } finally {
      setDialBusy(false);
      dialRef.current = false;
    }
  };

  const toggleLive = async () => {
    if (!agent?.id || statusBusy) return;
    setStatusBusy(true);
    try {
      await toggleAgentStatus(agent.id, isActive ? 'paused' : 'active');
      showToast(isActive ? 'Agent paused' : 'Agent is live', 'success');
    } catch (e) {
      showToast(e.message || 'Could not change status', 'error');
    } finally {
      setStatusBusy(false);
    }
  };

  const stateLabel = useMemo(() => {
    if (sessionState === 'CONNECTING') return 'Connecting…';
    if (botState === 'SPEAKING') return 'Agent speaking';
    if (sessionState === 'CONNECTED') return 'Listening';
    return 'Ready';
  }, [sessionState, botState]);

  return (
    <div className="space-y-4" data-testid="agent-test-call-panel-inner">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex p-1 rounded-xl bg-[#F0EEF6] border border-[#E4E2EB]">
          {[
            { id: 'browser', label: 'In browser' },
            { id: 'phone', label: 'Phone call' },
          ].map((m) => (
            <button
              key={m.id}
              type="button"
              data-testid={`test-call-mode-${m.id}`}
              onClick={() => setMode(m.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                mode === m.id ? 'bg-white text-[#0F0E17] shadow-xs' : 'text-[#524E5E]'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          data-testid="test-call-live-toggle"
          onClick={toggleLive}
          disabled={statusBusy || isLive}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-bold border transition-all disabled:opacity-50 ${
            isActive
              ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
              : 'bg-amber-50 text-amber-900 border-amber-200'
          }`}
        >
          {isActive ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
          {isActive ? 'Agent active' : 'Agent paused'}
        </button>
      </div>

      <div className="flex items-center justify-between text-[11px] text-[#524E5E] px-0.5">
        <span className="flex items-center gap-1">
          <Wallet className="w-3.5 h-3.5 text-[#524E5E]" />
          <span>
            Wallet{' '}
            {Number(wallet?.balanceInr || 0) > 0 ? (
              <>
                <strong className="text-[#0F0E17] font-semibold font-mono">₹{Number(wallet.balanceInr).toFixed(2)}</strong>
                <span className="text-[#8C879A] text-[10px] ml-1 font-mono">(${displayUsd.toFixed(2)})</span>
              </>
            ) : (
              <strong className="text-[#0F0E17] font-semibold font-mono">${displayUsd.toFixed(2)}</strong>
            )}{' '}
            {remainingMinutes !== null ? `· ~${remainingMinutes} min` : ''}
          </span>
        </span>
        {walletEmpty && (
          <button
            type="button"
            className="font-semibold text-[#6344E7]"
            onClick={() => openAddFunds?.('Add funds to run a test call.')}
          >
            Recharge
          </button>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[#E4E2EB] bg-[#FAF9FD] p-2.5 text-xs" data-testid="test-call-current-rate">
        <span className="flex items-center gap-1.5 font-medium text-[#524E5E]"><Zap className="w-3.5 h-3.5 text-amber-500" />{mode === 'browser' ? 'Web call rate' : 'Phone call rate'}</span>
        <span className="font-mono font-semibold text-[#0F0E17]">{rateAvailable ? `₹${activeRateInr.toFixed(2)}/min ($${activeRateUsd.toFixed(3)}/min)` : 'Rate unavailable'}</span>
      </div>

      {mode === 'browser' ? (
        <SolidCard className="p-0 overflow-hidden border-[#E4E2EB]" data-testid="test-call-browser-chrome">
          <div className="relative bg-gradient-to-b from-[#F0EEF6] to-white px-4 pt-4 pb-3">
            <div className="flex items-center justify-between gap-2 mb-3">
              <div className="flex items-center gap-2 min-w-0">
                <div className="w-9 h-9 rounded-xl bg-[#0F0E17] text-white flex items-center justify-center text-sm font-bold shrink-0">
                  {agent?.name?.charAt(0) || 'A'}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-bold text-[#0F0E17] truncate">{agent?.name || 'Agent'}</p>
                  <p className="text-[11px] text-[#524E5E] truncate">
                    {sessionState === 'CONNECTING'
                      ? 'Connecting with agent…'
                      : sessionState === 'CONNECTED'
                        ? 'Connected with agent'
                        : 'Not connected'}
                  </p>
                </div>
              </div>
              <div className="text-right shrink-0">
                <p
                  className="font-mono text-sm font-bold text-[#0F0E17] tabular-nums"
                  data-testid="test-call-timer"
                >
                  {formatElapsed(elapsedMs)}
                </p>
                <p
                  className={`text-[10px] font-semibold ${
                    isLive ? 'text-emerald-700' : 'text-[#8C879A]'
                  }`}
                >
                  {stateLabel}
                </p>
              </div>
            </div>

            <div className="h-[220px] sm:h-[260px] rounded-2xl bg-[#0F0E17]/95 border border-[#262438] overflow-hidden relative">
              <LazyVoxlyScene
                state={
                  sessionState === 'CONNECTING'
                    ? 'THINKING'
                    : botState === 'SPEAKING'
                      ? 'SPEAKING'
                      : sessionState === 'CONNECTED'
                        ? 'LISTENING'
                        : 'IDLE'
                }
                audioAmplitude={audioAmplitude}
                isInView={true}
              />
              {/* chisel: pulse animation with radial ripples (animate-ping) on microphone circle during connection handshake */}
              {sessionState === 'CONNECTING' && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-[#0F0E17]/70 backdrop-blur-xs">
                  <div className="relative flex items-center justify-center">
                    <span className="animate-ping absolute inline-flex h-12 w-12 rounded-full bg-[#6344E7] opacity-60" />
                    <span className="relative inline-flex rounded-full h-10 w-10 bg-[#6344E7] items-center justify-center text-white shadow-lg">
                      <Mic className="w-5 h-5 animate-pulse" />
                    </span>
                  </div>
                  <p className="text-xs font-semibold text-white tracking-wide">Connecting WebRTC audio…</p>
                </div>
              )}
            </div>
          </div>

          <div className="p-4 border-t border-[#E4E2EB] bg-white space-y-2">
            {!isLive ? (
              <TactileButton
                variant="brand"
                size="md"
                icon={PhoneCall}
                onClick={startBrowser}
                data-testid="test-call-start-browser"
                className="w-full justify-center"
                disabled={!isActive || statusBusy}
              >
                Start call
              </TactileButton>
            ) : (
              <div className="flex gap-2">
                <TactileButton
                  variant="secondary"
                  size="md"
                  icon={isMuted ? MicOff : Mic}
                  onClick={() => {
                    const next = !isMuted;
                    setIsMuted(next);
                    sessionRef.current?.setMuted?.(next);
                  }}
                  className="flex-1 justify-center"
                >
                  {isMuted ? 'Unmute' : 'Mute'}
                </TactileButton>
                <TactileButton
                  variant="danger"
                  size="md"
                  icon={PhoneOff}
                  onClick={endBrowser}
                  data-testid="test-call-end-browser"
                  className="flex-1 justify-center"
                >
                  End
                </TactileButton>
              </div>
            )}
            <p className="text-[11px] font-mono text-[#8C879A]">{statusNote || stateLabel}</p>
          </div>
        </SolidCard>
      ) : (
        <SolidCard className="space-y-3.5" data-testid="test-call-live-number">
          <p className="text-xs text-[#524E5E] leading-relaxed">
            Your phone will ring. Answer to speak with this agent using its published script.
          </p>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-xs font-bold text-[#0F0E17]">
                Phone Number to Call
              </label>
              <span className="text-[10px] text-[#8C879A]">e.g. +91 98765 43210</span>
            </div>
            <input
              type="tel"
              aria-label="Phone number to call"
              value={toE164}
              onChange={(e) => setToE164(e.target.value)}
              placeholder="+91 98765 43210"
              data-testid="test-call-phone-to"
              className="w-full rounded-xl border border-[#E4E2EB] bg-white px-3 py-2 font-mono text-sm min-h-[42px] sm:min-h-[38px] text-[#0F0E17] focus:outline-none focus:border-[#6344E7] focus:ring-1 focus:ring-[#6344E7]"
            />
            <p className="text-[10px] text-[#8C879A] mt-1">
              Enter your mobile or test phone number including the country code (+91 for India, +1 for US).
            </p>
          </div>

          <div>
            <label className="block text-xs font-bold text-[#0F0E17] mb-1">
              Call from
            </label>
            {availableOutboundNumbers.length > 0 ? (
              <>
                <select
                  aria-label="Call from"
                  value={activeFromLine}
                  onChange={(e) => setSelectedFromLine(e.target.value)}
                  data-testid="test-call-phone-from-select"
                  className="w-full rounded-xl border border-[#E4E2EB] bg-white px-3 py-2 font-mono text-sm min-h-[42px] sm:min-h-[38px] text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                >
                  {availableOutboundNumbers.map((num) => {
                    const val = num.e164 || num.number;
                    const isAgentAssigned =
                      num.assignedAgentId === agent?.id ||
                      (assignedLine && val === (assignedLine.e164 || assignedLine.number));
                    const assigned = isAgentAssigned ? ' (Assigned to this agent)' : '';
                    return (
                      <option key={num.id || val} value={val}>
                        {val} • {assigned || (num.locality ? num.locality : 'Direct Line')}
                      </option>
                    );
                  })}
                </select>
                <p className="text-[10px] text-[#8C879A] mt-1">
                  The caller ID that will display on the recipient&apos;s phone screen.
                </p>
              </>
            ) : (
              <div className="space-y-1.5">
                <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-3 text-xs text-amber-900 space-y-1">
                  <div className="flex items-center gap-1.5 font-semibold text-amber-900">
                    <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
                    <span>No phone line is ready for outgoing calls</span>
                  </div>
                  <p className="text-[11px] text-amber-800 leading-normal">
                    Enable outgoing calls on an active line in <strong>Phone lines</strong>, or test with your microphone in the <strong>In browser</strong> tab.
                  </p>
                </div>
                <input
                  type="hidden"
                  value={activeFromLine}
                  data-testid="test-call-phone-from-input"
                />
              </div>
            )}
          </div>

          {!isActive && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-2.5 text-xs text-amber-800 flex items-center justify-between">
              <span>Agent is currently paused. Activate it to place live calls.</span>
              <button
                type="button"
                onClick={toggleLive}
                disabled={statusBusy}
                className="font-bold text-[#6344E7] hover:underline ml-2 shrink-0"
              >
                Make Live
              </button>
            </div>
          )}

          <TactileButton
            variant="brand"
            size="md"
            icon={PhoneCall}
            loading={dialBusy}
            onClick={dialPhone}
            data-testid="test-call-start-phone"
            className="w-full justify-center min-h-[44px]"
            disabled={!isActive || !activeFromLine || statusBusy}
          >
            {dialBusy ? 'Preparing your agent…' : 'Call phone'}
          </TactileButton>
        </SolidCard>
      )}

      <div className="max-h-32 overflow-y-auto rounded-xl border border-[#E4E2EB] bg-[#FAF9FD] p-2.5 space-y-1 text-[11px]">
        {lines.length === 0 && (
          <p className="text-[#8C879A]">Live call events and status updates will appear here.</p>
        )}
        {lines.map((l) => (
          <p key={l.id} className={l.role === 'system' ? 'text-[#524E5E]' : 'text-[#0F0E17]'}>
            {l.text}
          </p>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}
