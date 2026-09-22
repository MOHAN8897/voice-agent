import React, { useState } from 'react';
import {
  Mic,
  Volume2,
  Play,
  ArrowRight,
  Headphones,
  CheckCircle2,
  RefreshCw,
  Radio
} from 'lucide-react';
import { voiceAgent } from '../services/voiceAgent';

export function TalkToAiSection({ onOpenTalkModal }) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [activePrompt, setActivePrompt] = useState(null);
  const [currentResponse, setCurrentResponse] = useState(
    "Hi there! I'm Voxly, your autonomous voice employee. Click any question below or hit 'Start Voice Test' to hear me speak live!"
  );

  const testScenarios = [
    {
      label: "Sales Lead Qualification",
      question: "Hi Voxly, how do you qualify inbound leads for our sales team?",
      answer: "I answer on ring one, ask the caller their company size and budget, detect buying intent, and automatically book high-value meetings on your account executive's calendar!",
    },
    {
      label: "24/7 Customer Support",
      question: "Can you handle refund inquiries and technical support?",
      answer: "Yes! I can look up customer order IDs, troubleshoot tier-1 issues from your knowledge base, and even process billing adjustments without making customers wait on hold.",
    },
    {
      label: "Human Agent Warm Transfer",
      question: "What happens if a customer asks for a human manager?",
      answer: "I immediately perform a warm transfer to your team, passing a live audio transcript and structured summary so your agent has 100% context before saying hello.",
    },
    {
      label: "Scalability & Speed",
      question: "How fast do you respond, and how many calls can you take?",
      answer: "My voice response latency is under 350 milliseconds — indistinguishable from human conversation — and our distributed telephony cluster can handle over 100,000 calls at once.",
    },
  ];

  const handleTestPrompt = (scenario) => {
    setActivePrompt(scenario.label);
    setCurrentResponse(scenario.answer);
    setIsPlaying(true);
    voiceAgent.playTTS(scenario.answer, () => {
      setIsPlaying(false);
    });
  };

  const handleStartConversation = () => {
    if (onOpenTalkModal) {
      onOpenTalkModal();
    } else {
      const defaultGreeting = "Hello! I am ready to talk. Ask me any question or test my live capabilities!";
      setCurrentResponse(defaultGreeting);
      setIsPlaying(true);
      voiceAgent.playTTS(defaultGreeting, () => {
        setIsPlaying(false);
      });
    }
  };

  return (
    <section id="talk-to-ai" className="py-20 sm:py-28 bg-[#111019] text-white relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 sm:px-8 relative z-10">
        
        {/* Section Header */}
        <div className="max-w-3xl mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-white/10 border border-white/10 text-white text-xs font-bold tracking-wider uppercase mb-4">
            <Radio className="w-3.5 h-3.5 text-[#10B981]" />
            <span>Interactive Voice Demonstration</span>
          </div>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-white tracking-tight leading-[1.12] mb-4">
            Don't take our word for it.{' '}
            <span className="block text-white">Talk to it.</span>
          </h2>
          <p className="text-base sm:text-lg text-[#D1CFDB] leading-relaxed">
            Experience real-time sub-500ms neural speech synthesis, natural interruption handling, and conversational empathy directly in your browser.
          </p>
        </div>

        {/* Central Architecture Visual Flow */}
        <div className="max-w-4xl mx-auto mb-14">
          <div className="bg-[#181724] border border-white/10 rounded-2xl p-6 sm:p-8 shadow-craft-lg">
            
            {/* TOP NODE: AI EMPLOYEE */}
            <div className="flex flex-col items-center justify-center mb-5">
              <div className="px-5 py-2 rounded-xl bg-white text-[#0F0E17] font-bold text-xs tracking-wider uppercase shadow-sm">
                AI EMPLOYEE
              </div>
              <div className="w-px h-6 bg-white/20 my-1" />
            </div>

            {/* SPLIT NODES: LISTEN vs RESPOND */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5 relative">
              {/* LISTEN NODE */}
              <div className="bg-[#111019] border border-white/10 rounded-xl p-5 text-left">
                <div className="flex items-center justify-between mb-2.5">
                  <span className="text-xs font-bold uppercase tracking-wider text-[#10B981] flex items-center gap-1.5">
                    <Mic className="w-3.5 h-3.5" /> LISTEN
                  </span>
                  <span className="text-[10px] font-mono text-[#D1CFDB]">Audio Input • STT</span>
                </div>
                <p className="text-xs text-[#D1CFDB] leading-relaxed mb-3">
                  Stream speech packets, detect pauses, and tokenize intent in &lt;120ms.
                </p>
                {/* Listening visualizer */}
                <div className="flex items-center gap-1 h-5 px-2.5 rounded bg-black/40 border border-white/5">
                  {[8, 16, 11, 18, 9, 15, 7, 17, 12, 8, 14].map((h, i) => (
                    <span
                      key={i}
                      className="w-1 bg-[#10B981] rounded-full"
                      style={{ height: `${h}px` }}
                    />
                  ))}
                  <span className="text-[9px] font-mono text-[#A19EAD] ml-auto">Live Input Frequency</span>
                </div>
              </div>

              {/* RESPOND NODE */}
              <div className="bg-[#111019] border border-white/10 rounded-xl p-5 text-left">
                <div className="flex items-center justify-between mb-2.5">
                  <span className="text-xs font-bold uppercase tracking-wider text-[#8369F5] flex items-center gap-1.5">
                    <Volume2 className="w-3.5 h-3.5 text-white" /> RESPOND
                  </span>
                  <span className="text-[10px] font-mono text-[#D1CFDB]">Neural TTS • 320ms</span>
                </div>
                <p className="text-xs text-[#D1CFDB] leading-relaxed mb-3">
                  Synthesize personalized acoustic speech with cadence and pitch modulation.
                </p>
                {/* Synthesizing visualizer */}
                <div className="flex items-center gap-1 h-5 px-2.5 rounded bg-black/40 border border-white/5">
                  {[14, 9, 18, 12, 17, 8, 16, 11, 15, 9, 17].map((h, i) => (
                    <span
                      key={i}
                      className="w-1 bg-white rounded-full"
                      style={{ height: `${h}px` }}
                    />
                  ))}
                  <span className="text-[9px] font-mono text-[#A19EAD] ml-auto">Neural Output</span>
                </div>
              </div>
            </div>

            {/* BOTTOM CONNECTOR: CONVERSATION */}
            <div className="flex flex-col items-center justify-center mt-5">
              <div className="w-px h-6 bg-white/20 my-1" />
              <div className="px-4 py-1.5 rounded-lg bg-white/10 border border-white/10 text-white font-semibold text-[11px] tracking-wider uppercase">
                REAL-TIME BIDIRECTIONAL CONVERSATION
              </div>
            </div>

            {/* Interactive Live Speech Box */}
            <div className="mt-7 bg-[#111019] border border-white/10 rounded-xl p-5 sm:p-6 text-left">
              <div className="flex items-center justify-between gap-2 mb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-[#D1CFDB]">
                  Acoustic Speech Player:
                </span>
                <span className={`text-[11px] font-mono px-2 py-0.5 rounded ${
                  isPlaying ? 'bg-[#10B981]/20 text-[#10B981] border border-[#10B981]/30' : 'bg-white/10 text-[#D1CFDB]'
                }`}>
                  {isPlaying ? '● Audio Active' : 'Ready'}
                </span>
              </div>

              <p className="text-sm font-medium text-white leading-relaxed mb-4 bg-black/30 p-3.5 rounded-lg border border-white/5 min-h-[60px]">
                "{currentResponse}"
              </p>

              {/* Sample Prompt Chips */}
              <div className="mb-5">
                <span className="text-[10px] font-bold text-[#A19EAD] uppercase tracking-wider block mb-2 font-mono">
                  Select a live scenario to test synthesized response:
                </span>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {testScenarios.map((sc, i) => (
                    <button
                      key={i}
                      onClick={() => handleTestPrompt(sc)}
                      className={`text-left text-xs p-3 rounded-xl border transition-all ${
                        activePrompt === sc.label
                          ? 'bg-white/15 border-white text-white shadow-xs'
                          : 'bg-white/5 hover:bg-white/10 border-white/5 text-[#D1CFDB] hover:text-white'
                      }`}
                    >
                      <span className="font-semibold block text-white">{sc.label}</span>
                      <span className="text-[11px] text-[#D1CFDB] truncate block mt-0.5">"{sc.question}"</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Primary Call to Action Button */}
              <div className="flex flex-wrap items-center gap-3 pt-2">
                <button
                  onClick={handleStartConversation}
                  className="inline-flex items-center justify-center gap-2.5 px-6 py-3 rounded-xl text-xs font-semibold text-[#0F0E17] bg-white hover:bg-[#FAF9FD] active:scale-[0.98] transition-all duration-150 shadow-xs"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>Start Voice Test</span>
                </button>

                <button
                  onClick={() => handleTestPrompt(testScenarios[0])}
                  className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-xs font-semibold text-white bg-white/10 hover:bg-white/15 border border-white/15 active:scale-[0.98] transition-all"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Replay Sample Audio</span>
                </button>
              </div>

            </div>

          </div>
        </div>

      </div>
    </section>
  );
}
