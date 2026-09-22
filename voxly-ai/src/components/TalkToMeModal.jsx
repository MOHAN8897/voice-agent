import React, { useState, useEffect } from 'react';
import { X, Mic, MicOff, Volume2, AlertCircle } from 'lucide-react';
import { voiceAgent } from '../services/voiceAgent';

const QUICK_PROMPTS = [
  "How do you qualify leads?",
  "What CRM platforms do you integrate with?",
  "Can you transfer calls to human sales reps?",
  "How fast are your response times?",
];

export function TalkToMeModal({ isOpen, onClose, onSelectBotState }) {
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [statusText, setStatusText] = useState("Press the microphone or select a question below to speak with Voxly.");
  const [errorMessage, setErrorMessage] = useState(null);
  const [conversationHistory, setConversationHistory] = useState([
    { speaker: 'Voxly', text: "Hi! I'm Voxly. Ask me anything about how I handle inbound calls, qualify leads, or book meetings." }
  ]);

  useEffect(() => {
    if (!isOpen) {
      voiceAgent.stopConversation();
      setIsListening(false);
      setIsSpeaking(false);
      setErrorMessage(null);
      if (onSelectBotState) onSelectBotState('IDLE');
    }
  }, [isOpen, onSelectBotState]);

  useEffect(() => {
    const unsubscribe = voiceAgent.subscribe((event, data) => {
      if (event === 'stateChange') {
        if (data.state === 'LISTENING') {
          setIsListening(true);
          setIsSpeaking(false);
          setStatusText("Listening to your microphone...");
          if (onSelectBotState) onSelectBotState('LISTENING');
        } else if (data.state === 'THINKING') {
          setIsListening(false);
          setIsSpeaking(false);
          setStatusText("Processing...");
          if (data.userText) {
            setConversationHistory((prev) => [...prev, { speaker: 'You', text: data.userText }]);
          }
          if (onSelectBotState) onSelectBotState('THINKING');
        } else if (data.state === 'TALKING') {
          setIsListening(false);
          setIsSpeaking(true);
          setStatusText("Voxly is speaking...");
          if (data.responseText) {
            setConversationHistory((prev) => [...prev, { speaker: 'Voxly', text: data.responseText }]);
          }
          if (onSelectBotState) onSelectBotState('TALKING');
        } else if (data.state === 'IDLE') {
          setIsListening(false);
          setIsSpeaking(false);
          setStatusText("Ready. Select another prompt or speak again.");
          if (onSelectBotState) onSelectBotState('IDLE');
        }
      } else if (event === 'error') {
        setIsListening(false);
        setErrorMessage(data.message || "Microphone access is needed for live conversation.");
        if (onSelectBotState) onSelectBotState('IDLE');
      }
    });

    return () => unsubscribe();
  }, [onSelectBotState]);

  const handleStartMic = async () => {
    setErrorMessage(null);
    await voiceAgent.startListening({
      onError: () => {
        setErrorMessage("Microphone access was denied or is not supported. You can still test with the prompt buttons below!");
      },
    });
  };

  const handleQuickPrompt = (promptText) => {
    setErrorMessage(null);
    voiceAgent.stopConversation();
    voiceAgent.handleUserInput(promptText);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#0F0E17]/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-md bg-white rounded-2xl p-5 sm:p-6 shadow-2xl border border-[#E4E2EB] overflow-hidden">
        
        {/* Header */}
        <div className="flex items-center justify-between pb-3.5 border-b border-[#E4E2EB] mb-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#0F0E17] flex items-center justify-center text-white shadow-xs">
              <Mic className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-[#0F0E17]">
                Live Mic Experience
              </h3>
              <p className="text-[11px] text-[#524E5E]">
                Autonomous voice agent with sub-500ms neural response
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-lg bg-[#FAF9FD] hover:bg-[#F0EEF6] border border-[#E4E2EB] flex items-center justify-center text-[#524E5E] hover:text-[#0F0E17] transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Message Log */}
        <div className="space-y-2.5 mb-5 max-h-[220px] overflow-y-auto pr-1">
          {conversationHistory.map((item, i) => {
            const isVoxly = item.speaker === 'Voxly';
            return (
              <div
                key={i}
                className={`p-3 rounded-xl text-xs leading-relaxed ${
                  isVoxly
                    ? 'bg-[#FAF9FD] text-[#0F0E17] border border-[#E4E2EB] mr-5 text-left'
                    : 'bg-[#0F0E17] text-white ml-5 text-right'
                }`}
              >
                <div className={`text-[10px] font-mono uppercase font-bold mb-1 ${isVoxly ? 'text-[#6344E7]' : 'text-[#D1CFDB]'}`}>
                  {item.speaker}
                </div>
                <p>{item.text}</p>
              </div>
            );
          })}
        </div>

        {/* Status Indicator */}
        <div className="p-2.5 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] text-center mb-4">
          <div className="text-xs font-mono text-[#524E5E] flex items-center justify-center gap-2">
            {isListening && <span className="w-2 h-2 rounded-full bg-red-500 animate-ping" />}
            {isSpeaking && <Volume2 className="w-3.5 h-3.5 text-[#10B981]" />}
            <span>{statusText}</span>
          </div>
        </div>

        {/* Error message banner */}
        {errorMessage && (
          <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-xs text-red-600 flex items-start gap-2 mb-4 text-left">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Microphone Button */}
        <div className="flex flex-col items-center justify-center mb-4">
          <button
            onClick={isListening ? () => voiceAgent.stopListening() : handleStartMic}
            className={`w-14 h-14 rounded-xl flex items-center justify-center transition-all duration-150 shadow-sm active:scale-[0.96] ${
              isListening
                ? 'bg-red-500 text-white animate-pulse'
                : 'bg-[#0F0E17] text-white hover:bg-[#232130]'
            }`}
            aria-label={isListening ? 'Stop listening' : 'Start speaking'}
          >
            {isListening ? <MicOff className="w-6 h-6" /> : <Mic className="w-6 h-6" />}
          </button>
          <span className="text-[11px] font-semibold text-[#524E5E] mt-2">
            {isListening ? 'Click to Stop' : 'Click to Speak via Mic'}
          </span>
        </div>

        {/* Quick Question Chips */}
        <div>
          <span className="text-[10px] font-mono font-bold text-[#524E5E] uppercase tracking-wider block mb-2 text-center">
            Or Click a Test Query:
          </span>
          <div className="flex flex-wrap gap-1.5 justify-center">
            {QUICK_PROMPTS.map((prompt) => (
              <button
                key={prompt}
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
