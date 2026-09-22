import React, { useState, useEffect, useRef } from 'react';
import { useWorkspace } from '../context/WorkspaceContext';
import { VoxlyScene } from '../../three/VoxlyScene';
import { voiceAgent } from '../../services/voiceAgent';
import { SolidCard } from '../ui/SolidCard';
import { TactileButton } from '../ui/TactileButton';
import { StatusBadge } from '../ui/StatusBadge';
import {
  Mic,
  MicOff,
  PhoneCall,
  PhoneOff,
  Zap,
  Volume2,
  VolumeX,
  Sparkles,
  RefreshCw,
  Sliders,
  Send,
  Radio,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  ArrowRight,
  Play,
  ShieldCheck,
  Cpu
} from 'lucide-react';

const SAMPLE_PROMPTS = [
  "How much does a dental implant procedure cost?",
  "Can I schedule an appointment for Friday at 3:00 PM?",
  "Are you an AI or a real human receptionist?",
  "Can I speak directly to the clinic doctor right away?",
  "Do you accept Delta Dental PPO insurance plans?"
];

export function TalkToAiConsole() {
  const { agents = [] } = useWorkspace();
  const [selectedAgentId, setSelectedAgentId] = useState(agents[0]?.id || 'agent-maya');
  const [sessionState, setSessionState] = useState('DISCONNECTED'); // DISCONNECTED | CONNECTING | CONNECTED
  const [botState, setBotState] = useState('IDLE'); // IDLE | LISTENING | THINKING | SPEAKING | INTERRUPTED
  const [isMuted, setIsMuted] = useState(false);
  const [bargeInSensitivity, setBargeInSensitivity] = useState('normal'); // low | normal | high
  const [noiseSuppression, setNoiseSuppression] = useState(true);
  const [textInput, setTextInput] = useState('');
  
  // Real-time telemetry metrics
  const [telemetry, setTelemetry] = useState({
    sttLatency: 92,
    ttft: 174,
    ttsLatency: 76,
    rtt: 342,
    jitter: 1.8,
    packetLoss: '0.00%'
  });

  // Transcript log
  const [transcript, setTranscript] = useState([
    {
      id: 't-1',
      role: 'agent',
      speaker: 'Sophia',
      text: "Hello, thank you for calling Apex Dental! My name is Sophia, your AI patient coordinator. How can I assist you with your appointment or dental care today?",
      time: '12:30:02',
      intent: 'greeting',
      sentiment: 'positive',
      latencyMs: 310
    }
  ]);

  const [bars, setBars] = useState(Array.from({ length: 24 }, () => 15));
  const transcriptEndRef = useRef(null);
  const activeAgent = (agents && agents.find(a => a.id === selectedAgentId)) || (agents && agents[0]) || { name: 'Maya', role: 'Inbound Receptionist' };

  // Auto-scroll transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcript]);

  // Audio equalizer simulation / animation
  useEffect(() => {
    let animationFrame;
    const updateEqualizer = () => {
      if (sessionState === 'CONNECTED') {
        const multiplier = botState === 'SPEAKING' ? 80 : botState === 'LISTENING' ? 40 : 10;
        setBars(prev => prev.map(() => Math.floor(Math.random() * multiplier) + 12));
      } else {
        setBars(Array.from({ length: 24 }, () => 6));
      }
      animationFrame = requestAnimationFrame(updateEqualizer);
    };

    animationFrame = requestAnimationFrame(updateEqualizer);
    return () => cancelAnimationFrame(animationFrame);
  }, [sessionState, botState]);

  // Jitter and RTT telemetry flutter
  useEffect(() => {
    if (sessionState !== 'CONNECTED') return;
    const interval = setInterval(() => {
      setTelemetry(prev => ({
        ...prev,
        sttLatency: Math.floor(88 + Math.random() * 14),
        ttft: Math.floor(165 + Math.random() * 22),
        ttsLatency: Math.floor(70 + Math.random() * 12),
        rtt: Math.floor(325 + Math.random() * 35),
        jitter: Number((1.2 + Math.random() * 0.9).toFixed(1))
      }));
    }, 2500);
    return () => clearInterval(interval);
  }, [sessionState]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      voiceAgent.stopConversation();
    };
  }, []);

  // Start Session
  const handleStartSession = () => {
    setSessionState('CONNECTING');
    setTimeout(() => {
      setSessionState('CONNECTED');
      setBotState('SPEAKING');
      voiceAgent.ensureAudioContext();
      
      const welcomeText = `Connected! I'm ${activeAgent?.name || 'your agent'}, running live on WebRTC. How can I assist you with your appointment or inquiry today?`;
      const welcomeMsg = {
        id: `t-${Date.now()}`,
        role: 'agent',
        speaker: activeAgent?.name || 'Voice AI',
        text: welcomeText,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        intent: 'session_init',
        sentiment: 'positive',
        latencyMs: 295
      };
      setTranscript(prev => [...prev, welcomeMsg]);

      // Speak welcome message through speech synthesis
      voiceAgent.playTTS(
        welcomeText,
        () => {
          setBotState('LISTENING');
          if (!isMuted) {
            voiceAgent.startListening({
              onSpeechResult: (spokenText) => {
                handleSendMessage(spokenText);
              }
            });
          }
        },
        () => {
          setBotState('SPEAKING');
        },
        {
          speed: activeAgent?.voice?.speed || 1.0,
          pitch: activeAgent?.voice?.pitch || 0.0,
          voiceName: activeAgent?.voice?.voiceName || activeAgent?.name
        }
      );
    }, 1000);
  };

  // End Session
  const handleEndSession = () => {
    voiceAgent.stopConversation();
    setSessionState('DISCONNECTED');
    setBotState('IDLE');
    setIsMuted(false);
  };

  // Force Interrupt
  const handleForceInterrupt = () => {
    if (sessionState !== 'CONNECTED') return;
    voiceAgent.stopTTS();
    setBotState('INTERRUPTED');
    setTimeout(() => {
      setBotState('LISTENING');
      if (!isMuted) {
        voiceAgent.startListening({
          onSpeechResult: (spokenText) => {
            handleSendMessage(spokenText);
          }
        });
      }
    }, 350);
  };

  // Toggle Microphone
  const handleToggleMic = async () => {
    if (sessionState !== 'CONNECTED') return;
    if (!isMuted) {
      voiceAgent.stopListening();
      setIsMuted(true);
    } else {
      setIsMuted(false);
      setBotState('LISTENING');
      await voiceAgent.startListening({
        onSpeechResult: (spokenText) => {
          handleSendMessage(spokenText);
        },
        onError: () => {
          setIsMuted(true);
        }
      });
    }
  };

  // Send User Message / Inject Prompt
  const handleSendMessage = (textToSend) => {
    const query = textToSend || textInput;
    if (!query.trim() || sessionState !== 'CONNECTED') return;

    voiceAgent.stopListening();

    const userEntry = {
      id: `t-user-${Date.now()}`,
      role: 'caller',
      speaker: 'You (Caller)',
      text: query,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      intent: 'user_utterance',
      sentiment: 'neutral'
    };

    setTranscript(prev => [...prev, userEntry]);
    setTextInput('');
    setBotState('THINKING');

    // Simulate sub-400ms neural pipeline response
    setTimeout(() => {
      setBotState('SPEAKING');

      let replyText = "I understand completely. Let me verify that in our database.";
      let intentTag = "general_inquiry";

      if (query.toLowerCase().includes("cost") || query.toLowerCase().includes("implant") || query.toLowerCase().includes("pricing")) {
        replyText = "Single tooth dental implants typically start from $1,850 including the abutment and crown. We also provide zero-interest financing through CareCredit.";
        intentTag = "pricing_inquiry";
      } else if (query.toLowerCase().includes("friday") || query.toLowerCase().includes("appointment") || query.toLowerCase().includes("schedule")) {
        replyText = "I have an opening this Friday at 3:00 PM with Dr. Chen. Shall I reserve that slot under your name?";
        intentTag = "booking_request";
      } else if (query.toLowerCase().includes("human") || query.toLowerCase().includes("ai") || query.toLowerCase().includes("real")) {
        replyText = "I am an autonomous voice assistant engineered by Voxly, but I have direct access to clinic schedules and can transfer you to our front desk anytime.";
        intentTag = "identity_verification";
      } else if (query.toLowerCase().includes("insurance") || query.toLowerCase().includes("dental") || query.toLowerCase().includes("ppo")) {
        replyText = "Yes! We are an in-network provider for Delta Dental Premier and PPO plans. We can perform real-time benefits verification before your visit.";
        intentTag = "insurance_check";
      } else if (query.toLowerCase().includes("doctor") || query.toLowerCase().includes("urgent") || query.toLowerCase().includes("pain")) {
        replyText = "Dr. Miller is currently in a restorative procedure, but I can flag an urgent priority callback or warm transfer you to head nurse Sarah right away.";
        intentTag = "escalation_transfer";
      }

      const agentReply = {
        id: `t-agent-${Date.now()}`,
        role: 'agent',
        speaker: activeAgent?.name || 'Sophia',
        text: replyText,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        intent: intentTag,
        sentiment: 'positive',
        latencyMs: Math.floor(310 + Math.random() * 45)
      };

      setTranscript(prev => [...prev, agentReply]);

      // Speak response through voiceAgent
      voiceAgent.playTTS(
        replyText,
        () => {
          setBotState('LISTENING');
          if (!isMuted) {
            voiceAgent.startListening({
              onSpeechResult: (spokenText) => {
                handleSendMessage(spokenText);
              }
            });
          }
        },
        () => {
          setBotState('SPEAKING');
        },
        {
          speed: activeAgent?.voice?.speed || 1.0,
          pitch: activeAgent?.voice?.pitch || 0.0,
          voiceName: activeAgent?.voice?.voiceName || activeAgent?.name
        }
      );
    }, 450);
  };

  return (
    <div className="space-y-6">
      {/* Top Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[#0F0E17]">Talk-To-AI Testing Lab</h1>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-[#6344E7]/10 text-[#6344E7] border border-[#6344E7]/20">
              <Radio className="w-3 h-3 animate-pulse text-[#6344E7]" />
              Real-time WebRTC
            </span>
          </div>
          <p className="text-xs sm:text-sm text-[#524E5E] mt-1">
            Test conversational turns, barge-in behavior, latency metrics, and emotional sync directly in your browser.
          </p>
        </div>

        {/* Agent Selector Dropdown */}
        <div className="flex items-center gap-3">
          <label className="text-xs font-semibold text-[#524E5E]">Active Agent:</label>
          <select
            value={selectedAgentId}
            onChange={(e) => setSelectedAgentId(e.target.value)}
            disabled={sessionState === 'CONNECTED'}
            className="h-9 px-3 text-xs font-semibold bg-white text-[#0F0E17] border border-[#E4E2EB] rounded-xl focus:border-[#6344E7] focus:outline-none transition-colors shadow-craft-xs"
          >
            {agents.map(ag => (
              <option key={ag.id} value={ag.id}>
                {ag.name} ({ag.role})
              </option>
            ))}
          </select>

          {sessionState === 'CONNECTED' ? (
            <TactileButton variant="danger" size="sm" onClick={handleEndSession}>
              <PhoneOff className="w-4 h-4 mr-1.5 text-rose-100" />
              End Call
            </TactileButton>
          ) : (
            <TactileButton
              variant="primary"
              size="sm"
              loading={sessionState === 'CONNECTING'}
              onClick={handleStartSession}
            >
              <PhoneCall className="w-4 h-4 mr-1.5" />
              Connect Live Call
            </TactileButton>
          )}
        </div>
      </div>

      {/* Telemetry Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <SolidCard className="p-3">
          <div className="text-[11px] font-semibold text-[#524E5E] uppercase tracking-wider">STT Latency</div>
          <div className="text-base font-bold text-[#0F0E17] font-mono mt-1 flex items-baseline gap-1">
            <span>{sessionState === 'CONNECTED' ? telemetry.sttLatency : '--'}</span>
            <span className="text-[10px] text-[#524E5E] font-normal">ms</span>
          </div>
          <div className="text-[10px] text-[#15803D] font-medium mt-0.5">Whisper V3 Turbo</div>
        </SolidCard>

        <SolidCard className="p-3">
          <div className="text-[11px] font-semibold text-[#524E5E] uppercase tracking-wider">TTFT (1st Token)</div>
          <div className="text-base font-bold text-[#0F0E17] font-mono mt-1 flex items-baseline gap-1">
            <span>{sessionState === 'CONNECTED' ? telemetry.ttft : '--'}</span>
            <span className="text-[10px] text-[#524E5E] font-normal">ms</span>
          </div>
          <div className="text-[10px] text-[#6344E7] font-medium mt-0.5">Gemini 2.5 Flash</div>
        </SolidCard>

        <SolidCard className="p-3">
          <div className="text-[11px] font-semibold text-[#524E5E] uppercase tracking-wider">TTS Latency</div>
          <div className="text-base font-bold text-[#0F0E17] font-mono mt-1 flex items-baseline gap-1">
            <span>{sessionState === 'CONNECTED' ? telemetry.ttsLatency : '--'}</span>
            <span className="text-[10px] text-[#524E5E] font-normal">ms</span>
          </div>
          <div className="text-[10px] text-[#15803D] font-medium mt-0.5">Cartesia Sonic</div>
        </SolidCard>

        <SolidCard className="p-3">
          <div className="text-[11px] font-semibold text-[#524E5E] uppercase tracking-wider">Full RTT</div>
          <div className="text-base font-bold font-mono mt-1 flex items-baseline gap-1">
            <span className={sessionState === 'CONNECTED' && telemetry.rtt < 400 ? 'text-[#15803D]' : 'text-amber-600'}>
              {sessionState === 'CONNECTED' ? telemetry.rtt : '--'}
            </span>
            <span className="text-[10px] text-[#524E5E] font-normal">ms</span>
          </div>
          <div className="text-[10px] text-[#524E5E] mt-0.5">&lt; 450ms target</div>
        </SolidCard>

        <SolidCard className="p-3">
          <div className="text-[11px] font-semibold text-[#524E5E] uppercase tracking-wider">Jitter / Loss</div>
          <div className="text-base font-bold text-[#0F0E17] font-mono mt-1 flex items-baseline gap-1">
            <span>{sessionState === 'CONNECTED' ? `${telemetry.jitter}ms` : '--'}</span>
            <span className="text-[10px] text-[#15803D] font-medium ml-1">0.0%</span>
          </div>
          <div className="text-[10px] text-[#15803D] font-medium mt-0.5">Opus / WebRTC</div>
        </SolidCard>

        <SolidCard className="p-3">
          <div className="text-[11px] font-semibold text-[#524E5E] uppercase tracking-wider">Pipeline State</div>
          <div className="text-base font-bold mt-1">
            {sessionState === 'CONNECTED' ? (
              <span className={`inline-block text-xs font-semibold px-2 py-0.5 rounded-md ${
                botState === 'SPEAKING' ? 'bg-[#22C55E]/15 text-[#15803D]' :
                botState === 'THINKING' ? 'bg-[#6344E7]/15 text-[#6344E7] animate-pulse' :
                botState === 'LISTENING' ? 'bg-sky-500/15 text-sky-700' :
                botState === 'INTERRUPTED' ? 'bg-amber-500/15 text-amber-700' :
                'bg-[#F0EEF6] text-[#524E5E]'
              }`}>
                {botState}
              </span>
            ) : (
              <span className="text-xs font-semibold text-[#524E5E]">STANDBY</span>
            )}
          </div>
          <div className="text-[10px] text-[#524E5E] mt-0.5">Barge-in: {bargeInSensitivity}</div>
        </SolidCard>
      </div>

      {/* Main Console Split View: 3D Mascot & Audio Engine vs Live Transcript Stream */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left / Mascot & Controls Column */}
        <div className="lg:col-span-5 space-y-4">
          <SolidCard className="relative overflow-hidden bg-[#0F0E17] border-[#262438] p-0 flex flex-col items-center">
            
            {/* Top State Badge overlay */}
            <div className="absolute top-4 left-4 z-20 flex items-center gap-2">
              <span className={`w-2.5 h-2.5 rounded-full ${
                sessionState === 'CONNECTED' ? 'bg-emerald-400 animate-ping' : 'bg-zinc-600'
              }`} />
              <span className="text-xs font-semibold text-white/90 uppercase tracking-wide">
                {sessionState === 'CONNECTED' ? `${activeAgent?.name} is ${botState}` : 'Session Idle'}
              </span>
            </div>

            <div className="absolute top-4 right-4 z-20">
              <span className="px-2.5 py-1 text-[11px] font-medium bg-[#111019]/80 border border-[#262438] rounded-lg text-[#8E8B9E]">
                Voice: {activeAgent?.voiceModel || 'Cartesia - Katie (Calm)'}
              </span>
            </div>

            {/* 3D Canvas Area */}
            <div className="w-full h-[320px] relative flex items-center justify-center pt-6">
              <div className="w-full h-full">
                <VoxlyScene
                  state={botState}
                  audioAmplitude={botState === 'SPEAKING' ? 0.75 : botState === 'LISTENING' ? 0.25 : 0.05}
                  isInView={true}
                />
              </div>

              {/* Glowing Aura Ring based on State */}
              <div
                aria-hidden="true"
                className={`absolute inset-0 pointer-events-none transition-opacity duration-500 ${
                  botState === 'SPEAKING' ? 'bg-indigo-500/10 opacity-100' :
                  botState === 'THINKING' ? 'bg-purple-500/10 opacity-100' :
                  botState === 'LISTENING' ? 'bg-cyan-500/10 opacity-100' :
                  botState === 'INTERRUPTED' ? 'bg-amber-500/15 opacity-100' :
                  'opacity-0'
                }`}
              />
            </div>

            {/* Live Audio Equalizer Bars */}
            <div className="w-full px-6 py-3 bg-[#111019]/90 border-t border-[#262438] flex items-center justify-center gap-1.5 h-14">
              {bars.map((height, idx) => (
                <div
                  key={idx}
                  className={`w-1.5 rounded-full transition-all duration-75 ${
                    botState === 'SPEAKING' ? 'bg-gradient-to-t from-[#6344E7] to-[#A390FD]' :
                    botState === 'LISTENING' ? 'bg-cyan-400' :
                    botState === 'INTERRUPTED' ? 'bg-amber-400' :
                    'bg-[#262438]'
                  }`}
                  style={{ height: `${Math.min(height, 36)}px` }}
                />
              ))}
            </div>

            {/* Action Bar / Control Deck */}
            <div className="w-full p-4 bg-[#0B0A10] border-t border-[#262438] space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <TactileButton
                    variant={isMuted ? 'danger' : 'secondary'}
                    size="sm"
                    onClick={handleToggleMic}
                    disabled={sessionState !== 'CONNECTED'}
                  >
                    {isMuted ? <MicOff className="w-4 h-4 mr-1 text-rose-400" /> : <Mic className="w-4 h-4 mr-1 text-emerald-400" />}
                    {isMuted ? 'Muted' : 'Mic Live'}
                  </TactileButton>

                  <TactileButton
                    variant="outline"
                    size="sm"
                    onClick={handleForceInterrupt}
                    disabled={sessionState !== 'CONNECTED'}
                    title="Simulate human barge-in interruption"
                  >
                    <Zap className="w-4 h-4 mr-1 text-amber-400" />
                    Force Interrupt
                  </TactileButton>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-[#8E8B9E] font-medium hidden sm:inline">Sensitivity:</span>
                  <div className="inline-flex rounded-lg border border-[#262438] bg-[#111019] p-0.5">
                    {['low', 'normal', 'high'].map(level => (
                      <button
                        key={level}
                        onClick={() => setBargeInSensitivity(level)}
                        className={`px-2 py-0.5 text-[10px] font-semibold uppercase rounded-md transition-colors ${
                          bargeInSensitivity === level
                            ? 'bg-[#6344E7] text-white shadow-xs'
                            : 'text-[#8E8B9E] hover:text-white'
                        }`}
                      >
                        {level}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Hardware / Engine Toggles */}
              <div className="pt-2 border-t border-[#1C1A27] flex items-center justify-between text-xs text-[#8E8B9E]">
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="noise-suppress"
                    checked={noiseSuppression}
                    onChange={(e) => setNoiseSuppression(e.target.checked)}
                    className="rounded border-[#262438] bg-[#111019] text-[#6344E7] focus:ring-0"
                  />
                  <label htmlFor="noise-suppress" className="cursor-pointer select-none text-[11px]">
                    Echo Cancellation & DeepFilterNet V3
                  </label>
                </div>
                <div className="flex items-center gap-1 text-[11px] text-emerald-400">
                  <ShieldCheck className="w-3.5 h-3.5" />
                  <span>Sub-400ms SLA</span>
                </div>
              </div>
            </div>
          </SolidCard>

          {/* Quick Synthetic Test Prompts */}
          <SolidCard className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-xs font-bold text-[#0F0E17] uppercase tracking-wider">
                <Sparkles className="w-3.5 h-3.5 text-[#6344E7]" />
                Synthetic Test Injection
              </div>
              <span className="text-[10px] text-[#524E5E]">Click pill to simulate caller voice</span>
            </div>

            <div className="flex flex-wrap gap-2">
              {SAMPLE_PROMPTS.map((prompt, i) => (
                <button
                  key={i}
                  disabled={sessionState !== 'CONNECTED'}
                  onClick={() => handleSendMessage(prompt)}
                  className="text-left text-xs px-3 py-1.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-[#0F0E17] hover:border-[#6344E7] hover:text-[#6344E7] transition-all disabled:opacity-40 disabled:hover:border-[#E4E2EB] active:scale-[0.98] shadow-craft-xs"
                >
                  &ldquo;{prompt}&rdquo;
                </button>
              ))}
            </div>
          </SolidCard>
        </div>

        {/* Right / Live Transcript & Intent Stream */}
        <div className="lg:col-span-7 flex flex-col h-[580px] bg-white border border-[#E4E2EB] rounded-2xl overflow-hidden shadow-craft-xs">
          
          {/* Header */}
          <div className="px-5 py-3.5 bg-[#FAF9FD] border-b border-[#E4E2EB] flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-2 h-2 rounded-full bg-[#22C55E] animate-pulse" />
              <span className="text-xs font-bold text-[#0F0E17] tracking-wide">Live Conversation Stream</span>
              <span className="text-[11px] text-[#524E5E]">({transcript.length} turns)</span>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => setTranscript([])}
                className="text-xs text-[#524E5E] hover:text-[#0F0E17] px-2 py-1 rounded-md hover:bg-[#F0EEF6] transition-colors font-medium"
                title="Clear transcript log"
              >
                Clear Log
              </button>
            </div>
          </div>

          {/* Transcript Scroll Area */}
          <div className="flex-1 p-5 overflow-y-auto space-y-4 font-sans text-sm bg-[#FAF9FD]/40">
            {transcript.map((msg) => (
              <div
                key={msg.id}
                className={`flex flex-col ${msg.role === 'agent' ? 'items-start' : 'items-end'}`}
              >
                <div className="flex items-center gap-2 mb-1 text-[11px] text-[#524E5E]">
                  <span className="font-semibold text-[#0F0E17]">{msg.speaker}</span>
                  <span>•</span>
                  <span>{msg.time}</span>
                  {msg.latencyMs && (
                    <span className="px-1.5 py-0.2 rounded bg-[#22C55E]/10 text-[#15803D] font-mono text-[10px] font-medium">
                      ⚡ {msg.latencyMs}ms RTT
                    </span>
                  )}
                  {msg.intent && (
                    <span className="px-1.5 py-0.2 rounded bg-[#6344E7]/10 text-[#6344E7] font-mono text-[10px] font-medium">
                      #{msg.intent}
                    </span>
                  )}
                </div>

                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed border ${
                    msg.role === 'agent'
                      ? 'bg-white text-[#0F0E17] border-[#E4E2EB] rounded-tl-sm shadow-craft-xs'
                      : 'bg-[#0F0E17] text-white border-[#0F0E17] rounded-tr-sm shadow-craft-xs'
                  }`}
                >
                  {msg.text}
                </div>
              </div>
            ))}
            <div ref={transcriptEndRef} />
          </div>

          {/* Prompt / Input Bar */}
          <div className="p-3.5 bg-white border-t border-[#E4E2EB]">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendMessage();
              }}
              className="flex items-center gap-2"
            >
              <input
                type="text"
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                placeholder={
                  sessionState === 'CONNECTED'
                    ? "Type a caller message or question to test response..."
                    : "Connect call above to start testing..."
                }
                disabled={sessionState !== 'CONNECTED'}
                className="flex-1 h-10 px-4 bg-[#FAF9FD] text-[#0F0E17] placeholder-[#8E8B9E] text-xs font-medium rounded-xl border border-[#E4E2EB] focus:border-[#6344E7] focus:outline-none transition-colors disabled:opacity-50 shadow-craft-xs"
              />
              <TactileButton
                type="submit"
                variant="primary"
                size="sm"
                disabled={sessionState !== 'CONNECTED' || !textInput.trim()}
              >
                <Send className="w-4 h-4" />
              </TactileButton>
            </form>
          </div>
        </div>

      </div>
    </div>
  );
}
