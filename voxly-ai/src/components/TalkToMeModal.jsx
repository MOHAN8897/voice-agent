import React, { useState, useEffect } from 'react';
import { X, Mic, MicOff, Volume2, AlertCircle, Shield } from 'lucide-react';
import { voiceAgent } from '../services/voiceAgent';

const QUICK_PROMPTS = [
  "How do you qualify leads?",
  "What CRM platforms do you integrate with?",
  "Can you transfer calls to human sales reps?",
  "How fast are your response times?",
];

/**
 * Live Mic demo. Microphone is requested only after the user confirms —
 * never on modal open, and never for camera / location / motion sensors.
 */
export function TalkToMeModal({ isOpen, onClose, onSelectBotState }) {
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [statusText, setStatusText] = useState(
    'Press the microphone or select a question below to speak with Voxly.'
  );
  const [errorMessage, setErrorMessage] = useState(null);
  const [micPhase, setMicPhase] = useState('idle'); // idle | consent | requesting
  const [conversationHistory, setConversationHistory] = useState([
    {
      speaker: 'Voxly',
      text: "Hi! I'm Voxly. Ask me anything about how I handle inbound calls, qualify leads, or book meetings.",
    },
  ]);

  useEffect(() => {
    if (!isOpen) {
      voiceAgent.stopConversation();
      setIsListening(false);
      setIsSpeaking(false);
      setErrorMessage(null);
      setMicPhase('idle');
      if (onSelectBotState) onSelectBotState('IDLE');
    }
  }, [isOpen, onSelectBotState]);

  useEffect(() => {
    const unsubscribe = voiceAgent.subscribe((event, data) => {
      if (event === 'stateChange') {
        if (data.state === 'LISTENING') {
          setIsListening(true);
          setIsSpeaking(false);
          setMicPhase('idle');
          setStatusText('Listening on your microphone…');
          if (onSelectBotState) onSelectBotState('LISTENING');
        } else if (data.state === 'THINKING') {
          setIsListening(false);
          setIsSpeaking(false);
          setStatusText('Processing...');
          if (data.userText) {
            setConversationHistory((prev) => [...prev, { speaker: 'You', text: data.userText }]);
          }
          if (onSelectBotState) onSelectBotState('THINKING');
        } else if (data.state === 'TALKING') {
          setIsListening(false);
          setIsSpeaking(true);
          setStatusText('Voxly is speaking...');
          if (data.responseText) {
            setConversationHistory((prev) => [
              ...prev,
              { speaker: 'Voxly', text: data.responseText },
            ]);
          }
          if (onSelectBotState) onSelectBotState('TALKING');
        } else if (data.state === 'IDLE') {
          setIsListening(false);
          setIsSpeaking(false);
          setStatusText('Ready. Select another prompt or speak again.');
          if (onSelectBotState) onSelectBotState('IDLE');
        }
      } else if (event === 'error') {
        setIsListening(false);
        setMicPhase('idle');
        setErrorMessage(data.message || 'Microphone access is needed for live conversation.');
        if (onSelectBotState) onSelectBotState('IDLE');
      }
    });

    return () => unsubscribe();
  }, [onSelectBotState]);

  const activateMicrophone = async () => {
    setMicPhase('requesting');
    setErrorMessage(null);
    const ok = await voiceAgent.startListening({
      onError: (err) => {
        setMicPhase('idle');
        setErrorMessage(
          err?.message ||
            'Microphone access was denied. You can still test with the prompt buttons below — those do not need the mic.'
        );
      },
    });
    if (!ok) setMicPhase('idle');
  };

  const beginMicConsent = async () => {
    setErrorMessage(null);
    const existing = await voiceAgent.getMicrophonePermissionState();
    if (existing === 'denied') {
      setErrorMessage(
        'Microphone access is blocked in your browser settings. Allow microphone for this site, or use the prompt buttons below (no mic needed).'
      );
      return;
    }
    // Already allowed → open the mic immediately; never re-prompt the OS dialog.
    if (existing === 'granted') {
      await activateMicrophone();
      return;
    }
    // First time only: explain in-app before the browser mic prompt (Samsung/Firefox
    // may label it vaguely as “other apps and services”).
    setMicPhase('consent');
  };

  const handleMicButton = () => {
    if (isListening) {
      voiceAgent.stopListening();
      setMicPhase('idle');
      return;
    }
    if (micPhase === 'consent') {
      activateMicrophone();
      return;
    }
    beginMicConsent();
  };

  const handleQuickPrompt = (promptText) => {
    setErrorMessage(null);
    setMicPhase('idle');
    voiceAgent.stopConversation();
    voiceAgent.handleUserInput(promptText);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#0F0E17]/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-md bg-white rounded-2xl p-5 sm:p-6 shadow-2xl border border-[#E4E2EB] overflow-hidden">
        <div className="flex items-center justify-between pb-3.5 border-b border-[#E4E2EB] mb-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#0F0E17] flex items-center justify-center text-white shadow-xs">
              <Mic className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-[#0F0E17]">Live Mic Experience</h3>
              <p className="text-[11px] text-[#524E5E]">
                Browser microphone only — no camera or other apps
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-7 h-7 rounded-lg bg-[#FAF9FD] hover:bg-[#F0EEF6] border border-[#E4E2EB] flex items-center justify-center text-[#524E5E] hover:text-[#0F0E17] transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="space-y-2.5 mb-5 max-h-[220px] overflow-y-auto pr-1">
          {conversationHistory.map((item, i) => {
            const isVoxly = item.speaker === 'Voxly';
            return (
              <div
                key={`${item.speaker}-${i}`}
                className={`flex ${isVoxly ? 'justify-start' : 'justify-end'}`}
              >
                <div
                  className={`max-w-[85%] px-3 py-2 rounded-xl text-xs leading-relaxed ${
                    isVoxly
                      ? 'bg-[#FAF9FD] text-[#0F0E17] border border-[#E4E2EB]'
                      : 'bg-[#0F0E17] text-white'
                  }`}
                >
                  <span className="block text-[10px] font-bold uppercase tracking-wider opacity-60 mb-0.5">
                    {item.speaker}
                  </span>
                  {item.text}
                </div>
              </div>
            );
          })}
        </div>

        <div className="mb-4">
          <div className="flex items-center justify-center gap-2 text-[11px] font-medium text-[#524E5E]">
            {isListening && <span className="w-2 h-2 rounded-full bg-red-500 animate-ping" />}
            {isSpeaking && <Volume2 className="w-3.5 h-3.5 text-[#10B981]" />}
            <span>{statusText}</span>
          </div>
        </div>

        {micPhase === 'consent' && (
          <div className="mb-4 p-3.5 rounded-xl bg-[#F7F3FF] border border-[#DCD5FF] text-left">
            <div className="flex items-start gap-2.5">
              <Shield className="w-4 h-4 text-[#6344E7] shrink-0 mt-0.5" />
              <div className="space-y-2">
                <p className="text-xs font-bold text-[#0F0E17]">Microphone permission next</p>
                <p className="text-[11px] text-[#524E5E] leading-relaxed">
                  Your browser will ask to use the <strong>microphone</strong> so Voxly can hear
                  you. We do <strong>not</strong> use camera, location, motion sensors, or other
                  apps on your device. You can deny and still try the text prompts below.
                </p>
                <div className="flex flex-wrap gap-2 pt-1">
                  <button
                    type="button"
                    onClick={activateMicrophone}
                    className="px-3 py-1.5 rounded-lg text-[11px] font-semibold text-white bg-[#0F0E17] hover:bg-[#232130]"
                  >
                    Allow microphone &amp; start
                  </button>
                  <button
                    type="button"
                    onClick={() => setMicPhase('idle')}
                    className="px-3 py-1.5 rounded-lg text-[11px] font-semibold text-[#524E5E] bg-white border border-[#E4E2EB]"
                  >
                    Not now
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {errorMessage && (
          <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-xs text-red-600 flex items-start gap-2 mb-4 text-left">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{errorMessage}</span>
          </div>
        )}

        <div className="flex flex-col items-center justify-center mb-4">
          <button
            type="button"
            onClick={handleMicButton}
            disabled={micPhase === 'requesting'}
            className={`w-14 h-14 rounded-xl flex items-center justify-center transition-all duration-150 shadow-sm active:scale-[0.96] disabled:opacity-60 ${
              isListening
                ? 'bg-red-500 text-white animate-pulse'
                : micPhase === 'consent'
                  ? 'bg-[#6344E7] text-white'
                  : 'bg-[#0F0E17] text-white hover:bg-[#232130]'
            }`}
            aria-label={
              isListening
                ? 'Stop listening'
                : micPhase === 'consent'
                  ? 'Confirm microphone access'
                  : 'Start speaking with microphone'
            }
          >
            {isListening ? <MicOff className="w-6 h-6" /> : <Mic className="w-6 h-6" />}
          </button>
          <span className="text-[11px] font-semibold text-[#524E5E] mt-2 text-center px-2">
            {isListening
              ? 'Click to stop'
              : micPhase === 'consent'
                ? 'Confirm above, then allow microphone'
                : micPhase === 'requesting'
                  ? 'Waiting for microphone permission…'
                  : 'Click to speak via microphone'}
          </span>
        </div>

        <div>
          <span className="text-[10px] font-mono font-bold text-[#524E5E] uppercase tracking-wider block mb-2 text-center">
            Or click a test query (no mic):
          </span>
          <div className="flex flex-wrap gap-1.5 justify-center">
            {QUICK_PROMPTS.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => handleQuickPrompt(prompt)}
                className="text-xs font-medium px-3 py-1.5 rounded-lg bg-[#FAF9FD] hover:bg-[#F0EEF6] text-[#0F0E17] border border-[#E4E2EB] transition-colors"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
