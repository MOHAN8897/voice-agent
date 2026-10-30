import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useWorkspace } from '../context/WorkspaceContext';
import { LazyDialtactScene } from '../../three/LazyDialtactScene';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
import { Avatar } from '../ui/Avatar';
import { Badge } from '../ui/StatusBadge';
import { PageHeader } from '../ui/PageHeader';
import { createWebAgentSession } from '../../services/webAgentClient';
import { showToast } from '../ui/ToastHost';
import {
  Mic,
  MicOff,
  PhoneCall,
  PhoneOff,
  Info,
  MessageSquare,
} from 'lucide-react';

function formatTime() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function TalkToAiConsole({ embedded = false }) {
  const { agents = [], selectedAgentId, setSelectedAgentId, wallet } = useWorkspace();
  const [sessionState, setSessionState] = useState('DISCONNECTED');
  const [botState, setBotState] = useState('IDLE');
  const [isMuted, setIsMuted] = useState(false);
  const [callId, setCallId] = useState(null);
  const [statusNote, setStatusNote] = useState('');
  const [transcript, setTranscript] = useState([]);
  const [bars, setBars] = useState(() => Array.from({ length: 20 }, () => 8));
  const sessionRef = useRef(null);
  const transcriptEndRef = useRef(null);

  const activeAgent = useMemo(() => {
    if (!agents.length) return null;
    return agents.find((a) => a.id === selectedAgentId) || agents[0];
  }, [agents, selectedAgentId]);

  const isLive = sessionState === 'CONNECTED' || sessionState === 'CONNECTING';

  useEffect(() => {
    if (agents.length && !agents.some((a) => a.id === selectedAgentId)) {
      setSelectedAgentId(agents[0].id);
    }
  }, [agents, selectedAgentId, setSelectedAgentId]);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcript]);

  useEffect(() => {
    let animationFrame;
    const tick = () => {
      if (sessionState === 'CONNECTED') {
        const cap = botState === 'SPEAKING' ? 72 : botState === 'LISTENING' ? 48 : 20;
        setBars((prev) => prev.map(() => Math.floor(Math.random() * cap) + 10));
      } else {
        setBars(Array.from({ length: 20 }, () => 8));
      }
      animationFrame = requestAnimationFrame(tick);
    };
    animationFrame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animationFrame);
  }, [sessionState, botState]);

  useEffect(() => {
    return () => {
      sessionRef.current?.stop();
    };
  }, []);

  const pushNote = (text, role = 'system') => {
    setTranscript((prev) => [
      ...prev,
      {
        id: `t-${Date.now()}`,
        role,
        speaker: role === 'system' ? 'Session' : activeAgent?.name || 'Agent',
        text,
        time: formatTime(),
      },
    ]);
  };

  const handleStartSession = async () => {
    if (!activeAgent) return;
    if (
      Number(wallet?.remainingMinutes || 0) <= 0 &&
      Number(wallet?.balanceInr || 0) <= 0 &&
      Number(wallet?.balanceUsd || 0) <= 0
    ) {
      showToast('Add wallet credits before starting a live test.', 'error');
      return;
    }

    // Mic access requires a secure context (HTTPS or localhost).
    // navigator.mediaDevices is undefined on plain HTTP — the browser never
    // even shows a permission prompt; it just throws a TypeError silently.
    if (!window.isSecureContext) {
      setStatusNote(
        'Microphone access requires HTTPS. Open this page over https:// or use localhost.'
      );
      showToast(
        'Test Studio requires a secure connection (HTTPS). Microphone is unavailable on plain HTTP.',
        'error'
      );
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setStatusNote(
        'Microphone access is blocked. Check browser permissions or use a supported browser.'
      );
      showToast(
        'Your browser can’t use the microphone here. Allow microphone access and make sure the page address starts with https.',
        'error'
      );
      return;
    }
    if (sessionRef.current) {
      try {
        sessionRef.current.stop();
      } catch {
        /* ignore */
      }
      sessionRef.current = null;
    }
    setSessionState('CONNECTING');
    setTranscript([]);
    setIsMuted(false);
    setStatusNote('Connecting to the same realtime voice path used on phone calls…');
    const session = createWebAgentSession();
    sessionRef.current = session;
    session.subscribe((event, data) => {
      if (event === 'ready') {
        setCallId(data.callId);
        setSessionState('CONNECTED');
        setBotState('SPEAKING');
        setStatusNote('Live. Speak naturally — hangup is validated like a phone call.');
        pushNote('Live voice session started. The agent will greet you on this line.');
      }
      if (event === 'audio') {
        setBotState('SPEAKING');
      }
      if (event === 'hangup_initiated') {
        setBotState('SPEAKING');
        setStatusNote('Hangup initiated — waiting for the farewell to finish.');
        pushNote('Hangup initiated. The agent is closing the call without stopping the server.');
      }
      if (event === 'hangup_complete' || event === 'closed') {
        setSessionState('DISCONNECTED');
        setBotState('IDLE');
        setStatusNote('Session ended.');
      }
      if (event === 'error') {
        setSessionState('DISCONNECTED');
        setBotState('IDLE');
        setStatusNote(data?.message || 'Session failed');
        showToast(data?.message || 'Could not start live voice', 'error');
      }
    });
    try {
      await session.start({
        agentId: activeAgent.id,
        language: (activeAgent.languages && activeAgent.languages[0]) || 'en-IN',
      });
    } catch (error) {
      setSessionState('DISCONNECTED');
      setBotState('IDLE');
      setStatusNote(error.message);
      showToast(error.message, 'error');
    }
  };

  const handleEndSession = () => {
    sessionRef.current?.stop();
    sessionRef.current = null;
    setSessionState('DISCONNECTED');
    setBotState('IDLE');
    setIsMuted(false);
    setStatusNote('You ended the test session.');
  };

  const handleToggleMic = async () => {
    if (sessionState !== 'CONNECTED') return;
    setIsMuted((prev) => {
      const next = !prev;
      sessionRef.current?.setMuted?.(next);
      return next;
    });
  };

  const remaining = wallet?.remainingMinutes;
  const stateLabel =
    sessionState === 'CONNECTING'
      ? 'Connecting'
      : botState === 'SPEAKING'
        ? 'Agent speaking'
        : sessionState === 'CONNECTED'
          ? 'Listening'
          : 'Ready';

  return (
    <div className="space-y-5">
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4">
        {!embedded && (
          <PageHeader
            className="min-w-0"
            title="Test call"
            description="A practice call works exactly like a real incoming or outgoing call and is paid from your wallet. When the employee hangs up you’ll see a short notice; the page stays open."
          />
        )}
        <div className={`flex flex-wrap items-center gap-2 ${embedded ? 'w-full justify-end' : ''}`}>
          {embedded && activeAgent && (
            <span className="text-ui text-fg-body mr-auto">
              Testing <span className="font-semibold text-ink">{activeAgent.name}</span>
            </span>
          )}
          {!embedded && (
            <select
              value={activeAgent?.id || ''}
              onChange={(e) => setSelectedAgentId(e.target.value)}
              disabled={isLive}
              aria-label="Choose an employee"
              className="min-w-0 max-w-full bg-surface border border-line rounded-control px-3 py-2 text-base sm:text-ui font-medium text-ink"
            >
              {!agents.length && <option value="">Create an employee first</option>}
              {agents.map((ag) => (
                <option key={ag.id} value={ag.id}>
                  {ag.name}
                </option>
              ))}
            </select>
          )}
          {isLive ? (
            <TactileButton variant="danger" size="sm" onClick={handleEndSession}>
              <PhoneOff className="w-4 h-4" />
              End call
            </TactileButton>
          ) : (
            <TactileButton
              variant="primary"
              size="sm"
              loading={sessionState === 'CONNECTING'}
              onClick={handleStartSession}
              disabled={!activeAgent}
            >
              <PhoneCall className="w-4 h-4" />
              Start test call
            </TactileButton>
          )}
        </div>
      </div>

      <div className="flex items-start gap-2 rounded-card border border-info-line bg-info-soft px-4 py-3 text-ui text-info-fg">
        <Info className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
        <span>
          {statusNote ||
            `Your wallet has ${Number(remaining || 0).toLocaleString()} minutes left. Save the employee’s script before testing.`}
          {callId ? ` · Call ${callId.slice(0, 8)}` : ''}
        </span>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-5 min-h-[520px]">
        <div className="xl:col-span-5 flex flex-col gap-4">
          <SolidCard className="p-0 overflow-hidden flex flex-col flex-1 border-line">
            <div className="relative bg-gradient-to-b from-surface-subtle to-surface px-5 pt-5 pb-3">
              <div className="flex items-center justify-between gap-2 mb-3">
                <div className="flex items-center gap-2 min-w-0">
                  <Avatar name={activeAgent?.name || 'A'} size="md" live={isLive} />
                  <div className="min-w-0">
                    <p className="text-copy font-semibold text-ink truncate" title={activeAgent?.name || undefined}>{activeAgent?.name || 'No employee'}</p>
                    <p className="text-meta text-fg-body truncate">{activeAgent?.role || 'Create an employee to test'}</p>
                  </div>
                </div>
                <Badge tone={isLive ? 'live' : 'neutral'} dot>
                  {isLive ? stateLabel : 'Not connected'}
                </Badge>
              </div>
              <div className="h-[220px] sm:h-[260px] rounded-card bg-ink/95 border border-white/10 overflow-hidden relative">
                <LazyDialtactScene
                  state={botState}
                  audioAmplitude={
                    botState === 'SPEAKING' ? 0.7 : sessionState === 'CONNECTED' ? 0.28 : 0.06
                  }
                  isInView={true}
                />
              </div>
              <div className="flex items-end justify-center gap-1 h-10 mt-4" aria-hidden>
                {bars.map((h, idx) => (
                  <div
                    key={idx}
                    className={`w-1 rounded-full ${
                      sessionState === 'CONNECTED' ? 'bg-accent' : 'bg-line-strong'
                    }`}
                    style={{ height: `${Math.min(h, 32)}px` }}
                  />
                ))}
              </div>
            </div>
            <div className="p-4 border-t border-line bg-surface">
              <button
                type="button"
                onClick={handleToggleMic}
                disabled={!isLive}
                className={`w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-control text-copy font-semibold border disabled:opacity-40 ${
                  isMuted
                    ? 'bg-danger-soft text-danger-fg border-danger-line'
                    : 'bg-ink text-white border-ink'
                }`}
              >
                {isMuted ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
                {isMuted ? 'Microphone muted' : 'Microphone live'}
              </button>
            </div>
          </SolidCard>
        </div>

        <SolidCard className="xl:col-span-7 p-0 flex flex-col min-h-[480px] overflow-hidden">
          <div className="px-4 py-3 border-b border-line bg-canvas flex items-center gap-2 text-title text-ink">
            <MessageSquare className="w-4 h-4 text-accent" />
            Conversation
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-canvas/30 min-h-[320px]">
            {transcript.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center px-6 py-16">
                <PhoneCall className="w-5 h-5 text-fg-muted mb-2" />
                <p className="text-title text-ink">No test call yet</p>
                <p className="text-ui text-fg-body mt-1 max-w-xs">
                  Start a test call and speak. Ask the employee to hang up to check how the call ends.
                </p>
              </div>
            ) : (
              transcript.map((msg) => (
                <div key={msg.id} className="p-3 rounded-control bg-surface border border-line text-ui">
                  <div className="flex justify-between text-meta text-fg-muted mb-1">
                    <span className="font-semibold text-accent-fg">{msg.speaker}</span>
                    <span className="font-mono tabular-nums">{msg.time}</span>
                  </div>
                  <p className="text-ink leading-relaxed">{msg.text}</p>
                </div>
              ))
            )}
            <div ref={transcriptEndRef} />
          </div>
        </SolidCard>
      </div>
    </div>
  );
}
