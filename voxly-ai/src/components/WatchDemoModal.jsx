import React, { useState, useEffect } from 'react';
import { X, Play, Pause, RotateCcw, CheckCircle2 } from 'lucide-react';
import { voiceAgent } from '../services/voiceAgent';

const DEMO_STEPS = [
  {
    speaker: "Voxly AI",
    text: "Hello! Thank you for calling CloudMetrics. My name is Voxly, your autonomous voice rep. Are you looking to upgrade your current data warehousing plan or resolve an existing pipeline question?",
    time: "0:03",
  },
  {
    speaker: "Prospect",
    text: "Hi! We're currently processing 40 million events per day on Snowflake and our queries are hitting concurrency limits. What's your integration timeline?",
    time: "0:09",
  },
  {
    speaker: "Voxly AI",
    text: "We deploy a direct zero-copy connector with Snowflake that activates in under 15 minutes. Our enterprise customers typically see a 4.2x speedup on concurrent analytics while cutting compute spend by 30%. Would you like to schedule a 15-minute technical benchmark with our solutions team?",
    time: "0:17",
  },
  {
    speaker: "Prospect",
    text: "Yes, that sounds great. What days do you have open this week?",
    time: "0:23",
  },
  {
    speaker: "Voxly AI",
    text: "I have Thursday at 11 AM Eastern or Friday at 2 PM Eastern available on our solutions architect's calendar. Which one suits your schedule best?",
    time: "0:29",
  },
];

export function WatchDemoModal({ isOpen, onClose, onSelectBotState }) {
  const [currentStep, setCurrentStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      voiceAgent.stopTTS();
      setIsPlaying(false);
      setCurrentStep(0);
      if (onSelectBotState) onSelectBotState('IDLE');
    }
  }, [isOpen, onSelectBotState]);

  useEffect(() => {
    let timer = null;
    if (isPlaying) {
      const step = DEMO_STEPS[currentStep];
      if (step.speaker === 'Voxly AI') {
        if (onSelectBotState) onSelectBotState('TALKING');
        voiceAgent.playTTS(step.text, {
          onEnd: () => {
            proceedToNext();
          },
        });
      } else {
        if (onSelectBotState) onSelectBotState('LISTENING');
        timer = setTimeout(() => {
          proceedToNext();
        }, 3200);
      }
    }
    return () => clearTimeout(timer);
  }, [isPlaying, currentStep]);

  const proceedToNext = () => {
    if (currentStep < DEMO_STEPS.length - 1) {
      setCurrentStep((prev) => prev + 1);
    } else {
      setIsPlaying(false);
      if (onSelectBotState) onSelectBotState('IDLE');
    }
  };

  const handleTogglePlay = () => {
    if (!isPlaying && currentStep >= DEMO_STEPS.length - 1) {
      setCurrentStep(0);
    }
    setIsPlaying(!isPlaying);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#0F0E17]/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-lg bg-white rounded-2xl p-5 sm:p-6 shadow-2xl border border-[#E4E2EB] overflow-hidden">
        
        {/* Header */}
        <div className="flex items-center justify-between pb-3.5 border-b border-[#E4E2EB] mb-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#0F0E17] flex items-center justify-center text-white shadow-xs">
              <svg
                className="w-4 h-4 text-white"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <line x1="18" y1="20" x2="18" y2="10" />
                <line x1="12" y1="20" x2="12" y2="4" />
                <line x1="6" y1="20" x2="6" y2="14" />
              </svg>
            </div>
            <div>
              <h3 className="text-sm font-bold text-[#0F0E17]">
                Live Telephony Simulation
              </h3>
              <p className="text-[11px] text-[#524E5E]">
                Bidirectional call simulation with synthesized neural voice
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

        {/* Live Conversation Display */}
        <div className="space-y-2.5 mb-5 max-h-[280px] overflow-y-auto pr-1">
          {DEMO_STEPS.slice(0, currentStep + 1).map((step, idx) => {
            const isVoxly = step.speaker === 'Voxly AI';
            const isCurrent = idx === currentStep;
            return (
              <div
                key={idx}
                className={`p-3.5 rounded-xl border text-left transition-all duration-200 ${
                  isVoxly
                    ? 'bg-[#FAF9FD] border-[#E4E2EB]'
                    : 'bg-white border-[#E4E2EB]'
                } ${isCurrent ? 'ring-1 ring-[#0F0E17]' : 'opacity-85'}`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className={`text-xs font-bold ${isVoxly ? 'text-[#6344E7]' : 'text-[#0F0E17]'}`}>
                    {step.speaker}
                  </span>
                  <span className="text-[10px] text-[#524E5E] font-mono">{step.time}</span>
                </div>
                <p className="text-xs text-[#0F0E17] leading-relaxed">
                  {step.text}
                </p>
              </div>
            );
          })}
        </div>

        {/* Playback Controls */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-3.5 border-t border-[#E4E2EB]">
          <div className="flex items-center gap-1.5 text-xs text-[#10B981] font-mono font-medium">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>Telemetry Active</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                setCurrentStep(0);
                setIsPlaying(false);
                voiceAgent.stopTTS();
                if (onSelectBotState) onSelectBotState('IDLE');
              }}
              className="p-2 rounded-lg bg-[#FAF9FD] hover:bg-[#F0EEF6] border border-[#E4E2EB] text-[#524E5E]"
              title="Restart Demo"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>

            <button
              onClick={handleTogglePlay}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-[#0F0E17] hover:bg-[#232130] active:scale-[0.98] transition-all shadow-xs"
            >
              {isPlaying ? <Pause className="w-3.5 h-3.5 fill-current" /> : <Play className="w-3.5 h-3.5 fill-current" />}
              <span>{isPlaying ? 'Pause' : 'Play Live Call'}</span>
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
