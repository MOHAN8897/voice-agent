import React, { useCallback, useEffect, useRef, useState } from 'react';
import { X, Play, Square, RotateCcw, Mic, CheckCircle2 } from 'lucide-react';
import { voiceAgent } from '../services/voiceAgent';
import { VOICE_SAMPLES, playVoiceSample, sampleDurationLabel } from '../services/marketingVoice';

/**
 * Product walkthrough.
 *
 * This used to play a fictional discovery call — invented company, invented 4.2x
 * speedup, invented savings — through `speechSynthesis`, and it passed the callbacks as
 * `playTTS(text, { onEnd })` when the signature is `playTTS(text, onEnd, onStart, options)`,
 * so the player threw on `onEnd()` and the walkthrough never advanced past line one.
 *
 * Both are fixed here by showing something that is actually true: the real voice
 * samples, the transcript that was spoken, and the states the mascot moves through
 * while it plays. The claims live on the sections below this modal, where they can be
 * checked.
 */
const WALKTHROUGH = [
  {
    id: 'healthcare-clinic',
    botState: 'TALKING',
    caption: 'First ring, in the caller\u2019s language, no hold music.',
  },
  {
    id: 'car-dealership',
    botState: 'CONFIDENT',
    caption: 'Qualifies and books on the call \u2014 the outcome is already in the CRM.',
  },
  {
    id: 'it-support',
    botState: 'THINKING',
    caption: 'Reads your knowledge base before it answers, so it never guesses.',
  },
  {
    id: 'logistics',
    botState: 'LISTENING',
    caption: 'Barge-in handled: the caller can interrupt at any point.',
  },
];

export function WatchDemoModal({ isOpen, onClose, onSelectBotState, onTryLive }) {
  const [index, setIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const stopRef = useRef(null);

  const stop = useCallback(() => {
    stopRef.current?.();
    stopRef.current = null;
    setIsPlaying(false);
    if (onSelectBotState) onSelectBotState('IDLE');
  }, [onSelectBotState]);

  useEffect(() => {
    if (isOpen) return;
    stop();
    setIndex(0);
  }, [isOpen, stop]);

  // Advance the walkthrough when a clip finishes.
  useEffect(() => {
    if (isOpen && isPlaying && !stopRef.current) {
      setIndex((prev) => (prev < WALKTHROUGH.length - 1 ? prev + 1 : 0));
    }
  }, [isOpen, isPlaying, index]);

  useEffect(() => () => stop(), [stop]);

  const playStep = useCallback(
    (stepIndex) => {
      const step = WALKTHROUGH[stepIndex];
      const sample = VOICE_SAMPLES.find((s) => s.id === step.id);
      if (!sample) return;
      stopRef.current?.();
      setIsPlaying(true);
      if (onSelectBotState) onSelectBotState(step.botState);
      stopRef.current = playVoiceSample(sample, {
        onEnd: () => {
          stopRef.current = null;
          setIsPlaying(false);
          if (onSelectBotState) onSelectBotState('IDLE');
          if (stepIndex < WALKTHROUGH.length - 1) {
            setIndex(stepIndex + 1);
            playStep(stepIndex + 1);
          }
        },
      });
    },
    [onSelectBotState]
  );

  const togglePlay = useCallback(() => {
    if (isPlaying) {
      stop();
      return;
    }
    playStep(index);
  }, [index, isPlaying, playStep, stop]);

  if (!isOpen) return null;

  const current = WALKTHROUGH[index];
  const sample = VOICE_SAMPLES.find((s) => s.id === current?.id);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#0F0E17]/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Product walkthrough demo"
        className="relative w-full max-w-lg bg-white rounded-2xl p-5 sm:p-6 shadow-2xl border border-[#E4E2EB] overflow-hidden"
      >
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
              <h3 className="text-sm font-bold text-[#0F0E17]">How a Voxly call sounds</h3>
              <p className="text-[11px] text-[#524E5E]">
                Real audio from the live speech model &mdash; not a scripted voice-over
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              stop();
              onClose();
            }}
            className="w-8 h-8 sm:w-7 sm:h-7 min-w-[36px] min-h-[36px] rounded-lg bg-[#FAF9FD] hover:bg-[#F0EEF6] border border-[#E4E2EB] flex items-center justify-center text-[#524E5E] hover:text-[#0F0E17] transition-colors"
            aria-label="Close walkthrough"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <ol className="space-y-2.5 mb-5 max-h-[300px] overflow-y-auto pr-1">
          {WALKTHROUGH.map((step, i) => {
            const stepSample = VOICE_SAMPLES.find((s) => s.id === step.id);
            const isCurrent = i === index;
            const isPast = i < index;
            return (
              <li
                key={step.id}
                className={`p-3.5 rounded-xl border text-left transition-all duration-200 ${
                  isCurrent ? 'bg-[#FAF9FD] border-[#E4E2EB] ring-1 ring-[#0F0E17]' : 'bg-white border-[#E4E2EB]'
                } ${isPast ? 'opacity-70' : ''}`}
              >
                <div className="flex items-center justify-between mb-1 gap-2">
                  <span className="text-xs font-bold text-[#6344E7]">
                    {stepSample?.industry} &middot; {stepSample?.label}
                  </span>
                  <span className="text-[10px] text-[#524E5E] font-mono shrink-0">
                    {sampleDurationLabel(stepSample?.durationSeconds)}
                  </span>
                </div>
                <p className="text-xs text-[#0F0E17] leading-relaxed">
                  &ldquo;{stepSample?.text}&rdquo;
                </p>
                <p className="text-[11px] text-[#524E5E] leading-relaxed mt-1.5">{step.caption}</p>
              </li>
            );
          })}
        </ol>

        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-3.5 border-t border-[#E4E2EB]">
          <div className="flex items-center gap-1.5 text-xs text-[#10B981] font-mono font-medium">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>{isPlaying ? 'Playing real audio' : 'Real samples'}</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                stop();
                setIndex(0);
              }}
              className="p-2 min-h-[40px] min-w-[40px] flex items-center justify-center rounded-lg bg-[#FAF9FD] hover:bg-[#F0EEF6] border border-[#E4E2EB] text-[#524E5E]"
              title="Restart"
              aria-label="Restart walkthrough"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>

            {onTryLive && (
              <button
                type="button"
                onClick={onTryLive}
                className="flex-1 sm:flex-initial inline-flex items-center justify-center gap-2 px-4 py-2 min-h-[40px] rounded-xl text-xs font-semibold text-[#0F0E17] bg-white border border-[#E4E2EB] hover:bg-[#FAF9FD] active:scale-[0.98] transition-all"
              >
                <Mic className="w-3.5 h-3.5" />
                <span>Try live</span>
              </button>
            )}

            <button
              type="button"
              onClick={togglePlay}
              data-testid="walkthrough-toggle"
              className="flex-1 sm:flex-initial inline-flex items-center justify-center gap-2 px-4 py-2 min-h-[40px] rounded-xl text-xs font-semibold text-white bg-[#0F0E17] hover:bg-[#232130] active:scale-[0.98] transition-all shadow-xs"
            >
              {isPlaying ? <Square className="w-3.5 h-3.5 fill-current" /> : <Play className="w-3.5 h-3.5 fill-current" />}
              <span>{isPlaying ? 'Stop' : 'Play'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default WatchDemoModal;