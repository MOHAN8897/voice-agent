import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useWorkspace } from '../context/WorkspaceContext';
import { LazyVoxlyScene } from '../../three/LazyVoxlyScene';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
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
          <div>
            <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">Live test</h2>
            <p className="text-xs text-[#524E5E] mt-1 max-w-xl">
              Practice call uses the same live phone AI as a real incoming or outgoing call. Wallet credits
              apply. When the agent hangs up, you will see a short notice — the app stays open.
            </p>
          </div>
        )}
        <div className={`flex flex-wrap items-center gap-2 ${embedded ? 'w-full justify-end' : ''}`}>
          {embedded && activeAgent && (
            <span className="text-xs text-[#524E5E] mr-auto">
              Testing <span className="font-semibold text-[#0F0E17]">{activeAgent.name}</span>
            </span>
          )}
          {!embedded && (
            <select
              value={activeAgent?.id || ''}
              onChange={(e) => setSelectedAgentId(e.target.value)}
              disabled={isLive}
              className="bg-white border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs font-semibold text-[#0F0E17]"
            >
              {!agents.length && <option value="">Create an agent first</option>}
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
              End session
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
              Start live test
            </TactileButton>
          )}
        </div>
      </div>

      <div className="flex items-start gap-2 rounded-xl border border-[#E4E2EB] bg-[#F0EEF6]/60 px-3 py-2.5 text-xs text-[#524E5E]">
        <Info className="w-4 h-4 text-[#6344E7] shrink-0 mt-0.5" />
        <span>
          {statusNote ||
            `Wallet has ${Number(remaining || 0).toLocaleString()} remaining minutes. Publish the agent script before testing.`}
          {callId ? ` · Call ${callId.slice(0, 8)}` : ''}
        </span>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-5 min-h-[520px]">
        <div className="xl:col-span-5 flex flex-col gap-4">
          <SolidCard className="p-0 overflow-hidden flex flex-col flex-1 border-[#E4E2EB]">
            <div className="relative bg-gradient-to-b from-[#F0EEF6] to-white px-5 pt-5 pb-3">
              <div className="flex items-center justify-between gap-2 mb-3">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="w-9 h-9 rounded-xl bg-[#0F0E17] text-white flex items-center justify-center text-sm font-bold shrink-0">
                    {activeAgent?.name?.charAt(0) || 'A'}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-bold text-[#0F0E17] truncate">{activeAgent?.name || 'No agent'}</p>
                    <p className="text-[11px] text-[#524E5E] truncate">{activeAgent?.role || 'Create an agent to test'}</p>
                  </div>
                </div>
                <span
                  className={`text-[11px] font-semibold px-2.5 py-1 rounded-full border ${
                    isLive
                      ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                      : 'bg-white text-[#524E5E] border-[#E4E2EB]'
                  }`}
                >
                  {isLive ? stateLabel : 'Not connected'}
                </span>
              </div>
              <div className="h-[220px] sm:h-[260px] rounded-2xl bg-[#0F0E17]/95 border border-[#262438] overflow-hidden relative">
                <LazyVoxlyScene
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
                      sessionState === 'CONNECTED' ? 'bg-[#6344E7]' : 'bg-[#D1CFDB]'
                    }`}
                    style={{ height: `${Math.min(h, 32)}px` }}
                  />
                ))}
              </div>
            </div>
            <div className="p-4 border-t border-[#E4E2EB] bg-white">
              <button
                type="button"
                onClick={handleToggleMic}
                disabled={!isLive}
                className={`w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold border disabled:opacity-40 ${
                  isMuted
                    ? 'bg-red-50 text-red-700 border-red-200'
                    : 'bg-[#0F0E17] text-white border-[#0F0E17]'
                }`}
              >
                {isMuted ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
                {isMuted ? 'Microphone muted' : 'Microphone live'}
              </button>
            </div>
          </SolidCard>
        </div>

        <SolidCard className="xl:col-span-7 p-0 flex flex-col min-h-[480px] overflow-hidden">
          <div className="px-4 py-3 border-b border-[#E4E2EB] bg-[#FAF9FD] flex items-center gap-2 text-sm font-bold text-[#0F0E17]">
            <MessageSquare className="w-4 h-4 text-[#6344E7]" />
            Session log
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-[#FAF9FD]/30 min-h-[320px]">
            {transcript.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center px-6 py-16">
                <PhoneCall className="w-5 h-5 text-[#8C879A] mb-2" />
                <p className="text-sm font-semibold text-[#0F0E17]">No live session yet</p>
                <p className="text-xs text-[#524E5E] mt-1 max-w-xs">
                  Start a live test, speak, and ask the agent to hang up to confirm the close flow.
                </p>
              </div>
            ) : (
              transcript.map((msg) => (
                <div key={msg.id} className="p-3 rounded-xl bg-white border border-[#E4E2EB] text-xs">
                  <div className="flex justify-between text-[10px] text-[#8C879A] font-mono mb-1">
                    <span className="font-bold text-[#6344E7]">{msg.speaker}</span>
                    <span>{msg.time}</span>
                  </div>
                  <p className="text-[#0F0E17] leading-relaxed">{msg.text}</p>
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
