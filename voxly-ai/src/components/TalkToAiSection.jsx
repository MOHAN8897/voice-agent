import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Mic,
  Volume2,
  Play,
  Square,
  ArrowRight,
  Headphones,
  Radio,
  Building2,
  Sparkles,
} from 'lucide-react';
import {
  VOICE_SAMPLES,
  playVoiceSample,
  playBrowserVoiceSample,
  sampleDurationLabel,
} from '../services/marketingVoice';
import { voiceAgent } from '../services/voiceAgent';

const BAR_COUNT = 34;

/**
 * The voice showcase.
 *
 * This section used to play `window.speechSynthesis` and a hard-coded list of replies.
 * That is the *browser's* voice reading marketing copy — it sounds nothing like the
 * product and, worse, it is evidence against the claim on screen. Every clip here is
 * rendered by the same live speech model that answers a customer's call, one per
 * industry, with the transcript that was actually spoken.
 */
export function TalkToAiSection({ onOpenTalkModal, onGetStarted }) {
  const [activeId, setActiveId] = useState(VOICE_SAMPLES[0]?.id ?? null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [mode, setMode] = useState('product'); // 'product' | 'browser'
  const [level, setLevel] = useState(0);
  const stopRef = useRef(null);
  const barsRef = useRef([]);

  const activeSample = useMemo(
    () => VOICE_SAMPLES.find((s) => s.id === activeId) || VOICE_SAMPLES[0] || null,
    [activeId]
  );

  // A rolling waveform seeded with the sample's real energy, pushed by the analyser
  // while audio plays. Bars stay static when idle instead of pretending to be a signal.
  useEffect(() => {
    const bars = barsRef.current;
    if (!bars?.length) return undefined;
    let raf = 0;
    const seed = Array.from({ length: bars.length }, (_, i) => {
      const wave = Math.sin((i / bars.length) * Math.PI);
      return 0.12 + wave * 0.18;
    });
    bars.forEach((el, i) => {
      if (el) el.style.height = `${Math.round(seed[i] * 100)}%`;
    });
    const tick = () => {
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [activeId]);

  // Push the live amplitude into whichever bars are on screen.
  useEffect(() => {
    if (!isPlaying) {
      const bars = barsRef.current;
      bars.forEach((el, i) => {
        if (!el) return;
        const wave = Math.sin((i / bars.length) * Math.PI);
        el.style.height = `${Math.round((0.12 + wave * 0.18) * 100)}%`;
      });
      return;
    }
    setLevel(0);
  }, [isPlaying]);

  useEffect(() => () => stopRef.current?.(), []);

  const handleStop = useCallback(() => {
    stopRef.current?.();
    stopRef.current = null;
    setIsPlaying(false);
    setLevel(0);
  }, []);

  const handlePlay = useCallback(() => {
    if (!activeSample) return;
    stopRef.current?.();
    if (isPlaying) {
      handleStop();
      return;
    }
    setIsPlaying(true);
    const opts = {
      onLevel: (v) => {
        setLevel(v);
        const bars = barsRef.current;
        bars.forEach((el, i) => {
          if (!el) return;
          const wave = 0.35 + Math.sin((i / bars.length) * Math.PI) * 0.65;
          const jitter = ((i * 37 + Math.round(Date.now() / 90)) % 11) / 11;
          const h = Math.max(8, Math.min(100, wave * (0.45 + v * 2.4) * (0.75 + jitter * 0.5) * 100));
          el.style.height = `${Math.round(h)}%`;
        });
      },
      onEnd: () => {
        stopRef.current = null;
        setIsPlaying(false);
        setLevel(0);
      },
    };
    stopRef.current =
      mode === 'browser'
        ? playBrowserVoiceSample(activeSample, { onEnd: opts.onEnd })
        : playVoiceSample(activeSample, opts);
  }, [activeSample, handleStop, isPlaying, mode]);

  const selectSample = useCallback(
    (id) => {
      handleStop();
      setMode('product');
      setActiveId(id);
    },
    [handleStop]
  );

  const handleStartConversation = useCallback(() => {
    handleStop();
    if (onOpenTalkModal) onOpenTalkModal();
  }, [handleStop, onOpenTalkModal]);

  return (
    <section id="talk-to-ai" className="py-20 sm:py-28 bg-[#111019] text-white relative overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 sm:px-8 relative z-10">
        <div className="max-w-3xl mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-white/10 border border-white/10 text-white text-xs font-bold tracking-wider uppercase mb-4">
            <Radio className="w-3.5 h-3.5 text-[#10B981]" />
            <span>Real Voice, Not A Recording Effect</span>
          </div>
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-white tracking-tight leading-[1.12] mb-4">
            Hear your industry answered{' '}
            <span className="block text-white">on the first ring.</span>
          </h2>
          <p className="text-base sm:text-lg text-[#D1CFDB] leading-relaxed">
            Every clip below was spoken by the same neural voice that answers your customers'
            calls — not your browser, not a prerecorded ad. Pick your business and press play.
          </p>
        </div>

        {/* Architecture strip: kept short, because the demo below now carries the proof. */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-10">
          {[
            {
              icon: Mic,
              tag: 'LISTEN',
              title: 'Caller speech, mid-sentence',
              body: 'Turn-taking on real pauses, so nobody talks over your customer.',
              color: 'text-[#10B981]',
            },
            {
              icon: Sparkles,
              tag: 'DECIDE',
              title: 'Your playbook, in your language',
              body: 'Pricing, eligibility, tone and escalation rules come from your workspace.',
              color: 'text-[#8369F5]',
            },
            {
              icon: Volume2,
              tag: 'SPEAK',
              title: 'One neural voice end to end',
              body: 'The same voice you hear here is the one your callers hear.',
              color: 'text-white',
            },
          ].map((item) => (
            <div key={item.tag} className="bg-[#181724] border border-white/10 rounded-2xl p-5 text-left">
              <div className="flex items-center gap-2 mb-2">
                <item.icon className={`w-4 h-4 ${item.color}`} />
                <span className={`text-[10px] font-bold uppercase tracking-wider ${item.color}`}>
                  {item.tag}
                </span>
              </div>
              <p className="text-sm font-semibold text-white mb-1">{item.title}</p>
              <p className="text-xs text-[#D1CFDB] leading-relaxed">{item.body}</p>
            </div>
          ))}
        </div>

        <div className="max-w-5xl mx-auto">
          <div className="bg-[#181724] border border-white/10 rounded-2xl p-6 sm:p-8 shadow-craft-lg">
            {/* Industry picker */}
            <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
              <span className="text-xs font-bold uppercase tracking-wider text-[#D1CFDB] flex items-center gap-2">
                <Building2 className="w-3.5 h-3.5" />
                Choose your business
              </span>
              <span className="text-[10px] font-mono text-[#A19EAD]">
                {VOICE_SAMPLES.length} live-rendered samples
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 mb-6">
              {VOICE_SAMPLES.map((sample) => {
                const isActive = sample.id === activeId;
                return (
                  <button
                    key={sample.id}
                    type="button"
                    onClick={() => selectSample(sample.id)}
                    data-testid={`voice-industry-${sample.id}`}
                    aria-pressed={isActive}
                    className={`text-left px-3 py-2.5 rounded-xl border transition-all ${
                      isActive
                        ? 'bg-white text-[#0F0E17] border-white'
                        : 'bg-white/5 hover:bg-white/10 border-white/5 text-[#D1CFDB] hover:text-white'
                    }`}
                  >
                    <span className="block text-xs font-bold truncate">{sample.industry}</span>
                    <span
                      className={`block text-[10px] truncate mt-0.5 ${
                        isActive ? 'text-[#524E5E]' : 'text-[#A19EAD]'
                      }`}
                    >
                      {sample.label} · {sampleDurationLabel(sample.durationSeconds)}
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Player */}
            <div className="bg-[#111019] border border-white/10 rounded-xl p-5 sm:p-6">
              <div className="flex items-center justify-between gap-3 mb-4">
                <div className="min-w-0">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-[#A19EAD] font-mono">
                    {activeSample?.industry} · {activeSample?.label}
                  </p>
                  <p
                    className="text-sm font-semibold text-white mt-0.5"
                    data-testid="voice-sample-transcript"
                  >
                    &ldquo;{activeSample?.text}&rdquo;
                  </p>
                </div>
                <span
                  className={`shrink-0 text-[11px] font-mono px-2 py-1 rounded border ${
                    isPlaying
                      ? 'bg-[#10B981]/20 text-[#10B981] border-[#10B981]/30'
                      : 'bg-white/10 text-[#D1CFDB] border-white/10'
                  }`}
                  data-testid="voice-sample-status"
                >
                  {isPlaying ? '● Playing' : 'Ready'}
                </span>
              </div>

              {/* Waveform driven by the real analyser */}
              <div
                className="flex items-end gap-[3px] h-16 mb-5"
                aria-hidden="true"
                data-testid="voice-sample-waveform"
                data-level={level.toFixed(3)}
              >
                {Array.from({ length: BAR_COUNT }, (_, i) => (
                  <span
                    key={i}
                    ref={(el) => {
                      barsRef.current[i] = el;
                    }}
                    className={`flex-1 rounded-full transition-[height] duration-100 ${
                      mode === 'browser' ? 'bg-[#F59E0B]/70' : 'bg-white/85'
                    }`}
                    style={{ height: '18%' }}
                  />
                ))}
              </div>

              {/* A/B: our voice vs the browser's built-in voice, same line */}
              <div className="inline-flex rounded-xl border border-white/10 bg-white/5 p-1 mb-5">
                {[
                  { id: 'product', label: 'Voxly voice' },
                  { id: 'browser', label: "Your browser's voice" },
                ].map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => {
                      handleStop();
                      setMode(opt.id);
                    }}
                    data-testid={`voice-mode-${opt.id}`}
                    aria-pressed={mode === opt.id}
                    className={`px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all ${
                      mode === opt.id
                        ? 'bg-white text-[#0F0E17]'
                        : 'text-[#D1CFDB] hover:text-white'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>

              {mode === 'browser' && (
                <p className="text-[11px] text-amber-200/90 mb-4 leading-relaxed">
                  This is the voice most automated phone systems ship: your browser reading the same
                  sentence. Switch back and hear the difference on your own hardware.
                </p>
              )}

              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={handlePlay}
                  data-testid="voice-sample-play"
                  className="inline-flex items-center justify-center gap-2.5 px-6 py-3 rounded-xl text-xs font-semibold text-[#0F0E17] bg-white hover:bg-[#FAF9FD] active:scale-[0.98] transition-all shadow-xs"
                >
                  {isPlaying ? <Square className="w-3.5 h-3.5 fill-current" /> : <Play className="w-3.5 h-3.5 fill-current" />}
                  <span>{isPlaying ? 'Stop' : 'Play this sample'}</span>
                </button>

                <button
                  type="button"
                  onClick={handleStartConversation}
                  data-testid="talk-to-ai-live"
                  className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-xs font-semibold text-white bg-white/10 hover:bg-white/15 border border-white/15 active:scale-[0.98] transition-all"
                >
                  <Headphones className="w-3.5 h-3.5" />
                  <span>Talk to a live agent</span>
                </button>

                {onGetStarted && (
                  <button
                    type="button"
                    onClick={onGetStarted}
                    className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-xs font-semibold text-[#8369F5] hover:bg-[#8369F5]/10 transition-all"
                  >
                    Build your own
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default TalkToAiSection;