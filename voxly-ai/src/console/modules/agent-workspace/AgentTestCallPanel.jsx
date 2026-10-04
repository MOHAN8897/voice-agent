import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Mic,
  MicOff,
  Pause,
  PhoneCall,
  PhoneOff,
  Play,
  Wallet,
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
export function AgentTestCallPanel({ agent }) {
  const {
    wallet,
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

  const isLive = sessionState === 'CONNECTED' || sessionState === 'CONNECTING';
  const balanceUsd = Number(wallet?.balanceUsd) || 0;
  const balanceInr = Number(wallet?.balanceInr) || 0;
  const fx = Number(wallet?.fxRateInr) || 95.64;
  const displayUsd =
    balanceUsd > 0 ? balanceUsd : balanceInr > 0 ? balanceInr / fx : 0;
  const walletEmpty = displayUsd <= 0 && balanceInr <= 0 && balanceUsd <= 0;
  const isActive = agent?.status === 'active';
  const fromLine =
    outboundFromE164 ||
    phoneNumbers.find((n) => n.outboundEnabled !== false)?.e164 ||
    phoneNumbers.find((n) => n.outboundEnabled !== false)?.number ||
    '';

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

  const requireLive = () => {
    if (isActive) return true;
    showToast('Agent is paused. Switch to Live before testing.', 'error');
    return false;
  };

  const startBrowser = async () => {
    if (!agent?.id) return;
    if (!requireLive() || !requireWallet()) return;
    setSessionState('CONNECTING');
    setBotState('THINKING');
    setLines([]);
    setIsMuted(false);
    setElapsedMs(0);
    // The clock starts on `ready` (server accepted the session and the voice loop is
    // live), not here — time spent handshaking is not billed time.
    startedAtRef.current = null;
    setStatusNote('Connecting to agent…');
    const session = createWebAgentSession();
    sessionRef.current = session;
    session.subscribe((event, data) => {
      if (event === 'ready') {
        setSessionState('CONNECTED');
        setBotState('SPEAKING');
        startedAtRef.current = Date.now();
        speakingUntilRef.current = Date.now() + 2500;
        setStatusNote('Connected — agent is live');
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
        language: (agent.languages && agent.languages[0]) || agent.language || 'en-US',
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
  };

  const dialPhone = async () => {
    if (!agent?.id) return;
    if (!requireLive() || !requireWallet()) return;
    if (!toE164.trim()) {
      showToast('Enter a destination number in E.164 (+1…).', 'error');
      return;
    }
    setDialBusy(true);
    try {
      await placeOutboundCall({
        agentId: agent.id,
        toE164: toE164.trim(),
        fromE164: fromLine || null,
      });
      showToast('Live number call started', 'success');
      push(`Dialing ${toE164.trim()}…`);
      setStatusNote(`Dialing ${toE164.trim()} — same agent script as browser test`);
    } catch (e) {
      const msg = e.message || 'Could not place call';
      showToast(msg, 'error');
      if (/wallet|balance|funds|402/i.test(msg)) openAddFunds?.(msg);
    } finally {
      setDialBusy(false);
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
            { id: 'browser', label: 'Browser mic' },
            { id: 'phone', label: 'Live number' },
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
          {isActive ? 'Live' : 'Paused'}
        </button>
      </div>

      <div className="flex items-center justify-between text-[11px] text-[#524E5E] px-0.5">
        <span className="flex items-center gap-1">
          <Wallet className="w-3.5 h-3.5" />
          Wallet ${displayUsd.toFixed(2)} · ~{Number(wallet?.remainingMinutes || 0)} min
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
                disabled={!isActive}
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
        <SolidCard className="space-y-3" data-testid="test-call-live-number">
          <p className="text-[11px] text-[#524E5E]">
            Places a real outbound call to a live number using this agent&apos;s published script —
            same path as production phone calls. Billed from your wallet.
          </p>
          <label className="block text-xs font-bold text-[#0F0E17]">
            Destination (E.164)
            <input
              type="tel"
              value={toE164}
              onChange={(e) => setToE164(e.target.value)}
              placeholder="+1555…"
              data-testid="test-call-phone-to"
              className="mt-1 w-full rounded-xl border border-[#E4E2EB] bg-white px-3 py-2 font-mono text-sm"
            />
          </label>
          {fromLine && (
            <p className="text-[10px] text-[#8C879A]">Caller ID: {fromLine}</p>
          )}
          <TactileButton
            variant="brand"
            size="md"
            icon={PhoneCall}
            loading={dialBusy}
            onClick={dialPhone}
            data-testid="test-call-start-phone"
            className="w-full justify-center"
            disabled={!isActive}
          >
            Call live number
          </TactileButton>
        </SolidCard>
      )}

      <div className="max-h-32 overflow-y-auto rounded-xl border border-[#E4E2EB] bg-[#FAF9FD] p-2 space-y-1 text-[11px]">
        {lines.length === 0 && (
          <p className="text-[#8C879A]">Session notes appear here. Failure details stay on the API.</p>
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
