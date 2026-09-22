import React, { useState } from 'react';
import {
  Users,
  Volume2,
  CheckCircle2,
  Play,
  ArrowRight
} from 'lucide-react';
import { AI_TEAM_MEMBERS } from '../data/siteContent';
import { voiceAgent } from '../services/voiceAgent';

export function AiTeamSection({ onGetStarted }) {
  const [activeMemberId, setActiveMemberId] = useState(AI_TEAM_MEMBERS[0].id);
  const [playingId, setPlayingId] = useState(null);

  const activeAgent = AI_TEAM_MEMBERS.find((m) => m.id === activeMemberId) || AI_TEAM_MEMBERS[0];

  const handlePlayVoice = (agent) => {
    setPlayingId(agent.id);
    voiceAgent.playTTS(agent.sampleDialogue, () => {
      setPlayingId(null);
    });
  };

  return (
    <section id="team" className="py-20 sm:py-28 bg-[#FAF9FD] relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        
        {/* Section Header */}
        <div className="max-w-3xl mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-white border border-[#E4E2EB] text-[#6344E7] text-xs font-bold tracking-wider uppercase mb-4 shadow-craft-xs">
            <span>Specialized Agents</span>
          </div>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-[#0F0E17] tracking-tight leading-[1.12] mb-4">
            Build an AI team, not just one agent.
          </h2>
          <p className="text-base sm:text-lg text-[#524E5E] leading-relaxed">
            Assign each voice employee a distinct role, acoustic persona, knowledge boundary, and operational objective across sales, support, frontdesk, and retention.
          </p>
        </div>

        {/* 4 Specialized Employee Profile Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
          {AI_TEAM_MEMBERS.map((member) => {
            const isSelected = activeMemberId === member.id;
            const isSpeaking = playingId === member.id;

            return (
              <div
                key={member.id}
                onClick={() => setActiveMemberId(member.id)}
                className={`p-6 rounded-2xl border transition-all duration-150 cursor-pointer flex flex-col justify-between text-left ${
                  isSelected
                    ? 'bg-white border-[#0F0E17] shadow-craft-sm ring-1 ring-[#0F0E17]'
                    : 'bg-white/80 hover:bg-white border-[#E4E2EB] hover:border-[#D1CFDB]'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <div className="w-10 h-10 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-[#0F0E17] font-mono font-bold text-xs flex items-center justify-center">
                      {member.avatar}
                    </div>
                    <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded bg-[#FAF9FD] border border-[#E4E2EB] text-[#524E5E]">
                      {member.badge}
                    </span>
                  </div>

                  <h3 className="text-base font-bold text-[#0F0E17] mb-0.5">
                    {member.name}
                  </h3>
                  <h4 className="text-xs font-semibold text-[#6344E7] mb-2.5">
                    {member.role}
                  </h4>
                  <p className="text-xs text-[#524E5E] leading-relaxed mb-4">
                    {member.desc}
                  </p>

                  {/* Skill tags */}
                  <div className="flex flex-wrap gap-1.5 mb-4">
                    {member.tags.map((tag, i) => (
                      <span key={i} className="text-[10px] font-mono bg-[#FAF9FD] text-[#524E5E] border border-[#E4E2EB] px-2 py-0.5 rounded">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Voice button */}
                <div className="pt-3 border-t border-[#E4E2EB]">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handlePlayVoice(member);
                    }}
                    className={`w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-semibold transition-all duration-150 ${
                      isSpeaking
                        ? 'bg-[#10B981] text-white animate-pulse'
                        : 'bg-[#FAF9FD] hover:bg-[#F0EEF6] border border-[#E4E2EB] text-[#0F0E17]'
                    }`}
                  >
                    <Volume2 className="w-3.5 h-3.5" />
                    <span>{isSpeaking ? 'Playing Voice...' : `Sample Voice`}</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>

        {/* Active Employee Deep-Dive Spotlight Card */}
        <div className="max-w-4xl bg-white rounded-2xl border border-[#E4E2EB] shadow-craft-md p-6 sm:p-8">
          <div className="flex flex-wrap items-center justify-between gap-4 pb-5 mb-5 border-b border-[#E4E2EB]">
            <div className="flex items-center gap-3.5">
              <div className="w-12 h-12 rounded-xl bg-[#0F0E17] text-white font-mono font-bold text-sm flex items-center justify-center">
                {activeAgent.avatar}
              </div>
              <div>
                <h4 className="text-base font-bold text-[#0F0E17] flex items-center gap-2">
                  {activeAgent.name} • {activeAgent.title}
                </h4>
                <p className="text-xs font-mono text-[#524E5E]">Acoustic Profile: {activeAgent.voice}</p>
              </div>
            </div>
            <button
              onClick={() => handlePlayVoice(activeAgent)}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-[#0F0E17] text-white hover:bg-[#232130] active:scale-[0.98] shadow-xs transition-all"
            >
              <Play className="w-3 h-3 fill-current" />
              <span>Preview Voice Sample</span>
            </button>
          </div>

          <div className="bg-[#FAF9FD] p-4 rounded-xl border border-[#E4E2EB] text-xs mb-5">
            <span className="text-[10px] font-mono font-bold text-[#524E5E] uppercase tracking-wider block mb-1">
              Sample Live Phone Greeting:
            </span>
            <p className="font-mono text-[#0F0E17] leading-relaxed text-xs">
              "{activeAgent.sampleDialogue}"
            </p>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-4 text-xs">
            <span className="text-[#524E5E]">Ready to deploy as an autonomous phone agent</span>
            <button
              onClick={onGetStarted}
              className="inline-flex items-center gap-1.5 text-[#0F0E17] font-semibold hover:underline"
            >
              <span>Build Your Agent with {activeAgent.name}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

      </div>
    </section>
  );
}
