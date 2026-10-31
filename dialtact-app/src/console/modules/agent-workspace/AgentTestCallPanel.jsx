import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
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
import { LazyDialtactScene } from '../../../three/LazyDialtactScene';
import { createWebAgentSession } from '../../../services/webAgentClient';
import { showToast } from '../../ui/ToastHost';
import { Avatar } from '../../ui/Avatar';
import { walletAmounts } from '../../../lib/money';
import { OutboundCallForm, useOutboundCall } from '../outbound/OutboundCallForm';

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
    toggleAgentStatus,
  } = useWorkspace();
  // The phone test is the shared outgoing-call form with this agent fixed, so it
  // offers exactly what the Calls tab's Outgoing → Single call offers.
  const phoneCall = useOutboundCall({
    draftName: 'test-call-phone',
    draftSubject: agent?.id,
    lockedAgentId: agent?.id || null,
  });
  const [mode, setMode] = useState('browser');
  const [sessionState, setSessionState] = useState('DISCONNECTED');
  const [botState, setBotState] = useState('IDLE');
  const [isMuted, setIsMuted] = useState(false);
  const [statusNote, setStatusNote] = useState('');
  const [lines, setLines] = useState([]);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [audioAmplitude, setAudioAmplitude] = useState(0.06);
  const [statusBusy, setStatusBusy] = useState(false);
  const sessionRef = useRef(null);
  const endRef = useRef(null);
  const startedAtRef = useRef(null);
  const speakingUntilRef = useRef(0);

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
    showToast('Add funds to your wallet before testing. Test calls are paid from your balance.', 'error');
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
    showToast('This employee is paused. Turn them on before testing.', 'error');
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
    setStatusNote('Connecting…');
    session.subscribe((event, data) => {
      if (event === 'ready') {
        setSessionState('CONNECTED');
        startedAtRef.current = Date.now();
        speakingUntilRef.current = Date.now();
        setStatusNote(data?.microphoneMode === 'listen-only'
          ? 'Connected, but you can only listen. Allow microphone access to speak.'
          : 'Connected. Go ahead and speak.');
        push('Live session started. Agent follows your published script.');
      }
      if (event === 'audio') {
        speakingUntilRef.current = Date.now() + 400;
        setBotState('SPEAKING');
      }
      if (event === 'hangup_initiated') {
        setStatusNote('The employee is ending the call…');
        push('Hangup started.');
      }
      if (event === 'hangup_complete' || event === 'closed') {
        setSessionState('DISCONNECTED');
        setBotState('IDLE');
        startedAtRef.current = null;
        setStatusNote('Call ended. The cost was taken from your wallet.');
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
    setStatusNote('You ended the call.');
    refreshWallet?.();
    setTimeout(() => refreshWallet?.(), 1500);
  };

  const toggleLive = async () => {
    if (!agent?.id || statusBusy) return;
    setStatusBusy(true);
    try {
      await toggleAgentStatus(agent.id, isActive ? 'paused' : 'active');
      showToast(isActive ? 'Employee paused' : 'Employee is live', 'success');
    } catch (e) {
      showToast(e.message || 'The status could not be changed', 'error');
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
        <div className="inline-flex p-0.5 gap-0.5 rounded-control bg-surface-subtle border border-line" role="group" aria-label="How to test">
          {[
            { id: 'browser', label: 'In browser' },
            { id: 'phone', label: 'Phone call' },
          ].map((m) => (
            <button
              key={m.id}
              type="button"
              data-testid={`test-call-mode-${m.id}`}
              onClick={() => setMode(m.id)}
              aria-pressed={mode === m.id}
              className={`px-3 py-1.5 min-h-[32px] rounded-[8px] text-ui font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                mode === m.id ? 'bg-surface text-ink shadow-craft-xs' : 'text-fg-body hover:text-ink'
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
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 min-h-[32px] rounded-pill text-meta font-medium border transition-colors disabled:opacity-50 ${
            isActive
              ? 'bg-success-soft text-success-fg border-success-line'
              : 'bg-warning-soft text-warning-fg border-warning-line'
          }`}
        >
          {isActive ? <Play className="w-3 h-3" /> : <Pause className="w-3 h-3" />}
          {isActive ? 'Live: tap to pause' : 'Paused: tap to turn on'}
        </button>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-ui text-fg-body px-0.5">
        <span className="flex items-center gap-1">
          <Wallet className="w-3.5 h-3.5 text-fg-body" />
          <span>
            Wallet{' '}
            <strong className="text-ink font-semibold font-mono tabular-nums">{walletAmounts(wallet).primary}</strong>
            {!walletAmounts(wallet).isEmpty && (
              <span className="text-fg-muted text-meta ml-1 font-mono tabular-nums">({walletAmounts(wallet).secondary})</span>
            )}{' '}
            {remainingMinutes !== null ? `· ~${remainingMinutes} min` : ''}
          </span>
        </span>
        {walletEmpty && (
          <button
            type="button"
            className="font-medium text-accent-fg hover:underline"
            onClick={() => openAddFunds?.('Add funds to run a test call.')}
          >
            Add funds
          </button>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-control border border-line bg-canvas p-2.5 text-ui" data-testid="test-call-current-rate">
        <span className="flex items-center gap-1.5 font-medium text-fg-body"><Zap className="w-3.5 h-3.5 text-fg-subtle" aria-hidden="true" />{mode === 'browser' ? 'Web call rate' : 'Phone call rate'}</span>
        <span className="font-mono font-semibold tabular-nums text-ink">{rateAvailable ? `₹${activeRateInr.toFixed(2)}/min ($${activeRateUsd.toFixed(3)}/min)` : 'Price not available'}</span>
      </div>

      {mode === 'browser' ? (
        <SolidCard className="p-0 overflow-hidden border-line" data-testid="test-call-browser-chrome">
          <div className="relative bg-gradient-to-b from-surface-subtle to-surface px-4 pt-4 pb-3">
            <div className="flex items-center justify-between gap-2 mb-3">
              <div className="flex items-center gap-2 min-w-0">
                <Avatar name={agent?.name || 'Agent'} size="md" live={isLive} />
                <div className="min-w-0">
                  <p className="text-copy font-semibold text-ink truncate" title={agent?.name || undefined}>{agent?.name || 'Agent'}</p>
                  <p className="text-meta text-fg-body truncate">
                    {sessionState === 'CONNECTING'
                      ? 'Connecting…'
                      : sessionState === 'CONNECTED'
                        ? 'On the call'
                        : 'Not connected'}
                  </p>
                </div>
              </div>
              <div className="text-right shrink-0">
                <p
                  className="font-mono text-copy font-semibold text-ink tabular-nums"
                  data-testid="test-call-timer"
                >
                  {formatElapsed(elapsedMs)}
                </p>
                <p
                  className={`text-meta font-semibold ${
                    isLive ? 'text-success-fg' : 'text-fg-muted'
                  }`}
                >
                  {stateLabel}
                </p>
              </div>
            </div>

            <div className="h-[220px] sm:h-[260px] rounded-card bg-ink/95 border border-white/10 overflow-hidden relative">
              <LazyDialtactScene
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
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-ink/70 backdrop-blur-xs">
                  <div className="relative flex items-center justify-center">
                    <span className="animate-ping absolute inline-flex h-12 w-12 rounded-full bg-accent opacity-60" />
                    <span className="relative inline-flex rounded-full h-10 w-10 bg-accent items-center justify-center text-white shadow-lg">
                      <Mic className="w-5 h-5 animate-pulse" />
                    </span>
                  </div>
                  <p className="text-ui font-semibold text-white">Connecting audio…</p>
                </div>
              )}
            </div>
          </div>

          <div className="p-4 border-t border-line bg-surface space-y-2">
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
                  End call
                </TactileButton>
              </div>
            )}
            <p className="text-meta text-fg-muted" role="status">{statusNote || stateLabel}</p>
          </div>
        </SolidCard>
      ) : (
        <SolidCard className="space-y-3.5" data-testid="test-call-live-number">
          <OutboundCallForm
            call={phoneCall}
            showCost={false}
            compact
            intro={(
              <p className="text-ui text-fg-body leading-relaxed">
                Your phone will ring. Answer it to talk to this employee using their saved script.
              </p>
            )}
            ids={{
              root: 'test-call-phone-form',
              from: 'test-call-phone-from-select',
              fromHidden: 'test-call-phone-from-input',
              to: 'test-call-phone-to',
              submit: 'test-call-start-phone',
              error: 'test-call-phone-error',
              paymentWall: 'test-call-payment-wall',
              paymentWallAdd: 'test-call-payment-wall-add',
              integrationSummary: 'test-call-integration-summary',
            }}
            noLinesHint=", or test with your microphone in the In browser tab"
            submitLabel="Call phone"
            busyLabel="Getting your employee ready…"
            onPlaced={(result) => {
              push(`Dialing ${result.toE164}…`);
              setStatusNote(`Calling ${result.toE164}. The employee will use their saved script`);
            }}
            onFailed={(err) => push(`Call attempt failed: ${err.message}`, 'system')}
          />
        </SolidCard>
      )}

      <div className="max-h-32 overflow-y-auto rounded-control border border-line bg-canvas p-2.5 space-y-1 text-ui" aria-live="polite">
        {lines.length === 0 && (
          <p className="text-fg-muted">What happens on the call will show up here.</p>
        )}
        {lines.map((l) => (
          <p key={l.id} className={l.role === 'system' ? 'text-fg-body' : 'text-ink'}>
            {l.text}
          </p>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}
