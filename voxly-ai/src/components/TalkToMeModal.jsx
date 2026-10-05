import React, { useCallback, useEffect, useState } from 'react';
import { X, Mic, Volume2, AlertCircle, ArrowRight, LogIn } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { VOICE_SAMPLES, playVoiceSample, sampleDurationLabel } from '../services/marketingVoice';
import { voiceAgent } from '../services/voiceAgent';

/**
 * Live-voice entry point.
 *
 * This modal used to run a fake conversation: the browser's speech recogniser
 * transcribed you, then `voiceAgent.handleUserInput` replied from a hard-coded array
 * with `speechSynthesis` speaking it. Nothing about that was the product, and it asked
 * for microphone permission to do it — a bad trade for a visitor who just arrived.
 *
 * Now: a visitor hears the real voice on real industry lines and can press one button
 * to start a real live session (which needs an agent, so it asks for a workspace first).
 * The microphone is only requested inside that real session, which already runs the
 * production pipeline.
 */
export function TalkToMeModal({ isOpen, onClose, onSelectBotState, onStartLive }) {
  const { isAuthenticated } = useAuth();
  const [activeId, setActiveId] = useState(VOICE_SAMPLES[0]?.id ?? null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [stopRef, setStopRef] = useState(null);

  const stop = useCallback(() => {
    stopRef?.();
    setStopRef(null);
    setIsPlaying(false);
    voiceAgent.stopTTS();
    if (onSelectBotState) onSelectBotState('IDLE');
  }, [onSelectBotState]);

  useEffect(() => {
    if (!isOpen) {
      stop();
      setErrorMessage(null);
    }
    return undefined;
  }, [isOpen, stop]);

  useEffect(() => () => stop(), [stop]);

  const activeSample = VOICE_SAMPLES.find((s) => s.id === activeId) || VOICE_SAMPLES[0] || null;

  const handlePlay = useCallback(() => {
    if (isPlaying) {
      stop();
      return;
    }
    setErrorMessage(null);
    setIsPlaying(true);
    if (onSelectBotState) onSelectBotState('TALKING');
    setStopRef(
      playVoiceSample(activeSample, {
        onEnd: () => {
          setStopRef(null);
          setIsPlaying(false);
          if (onSelectBotState) onSelectBotState('IDLE');
        },
      })
    );
  }, [activeSample, isPlaying, onSelectBotState, stop]);

  const handleStartLive = useCallback(() => {
    stop();
    if (onStartLive) onStartLive();
    else setErrorMessage('Live voice is unavailable in this build.');
  }, [onStartLive, stop]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#0F0E17]/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Audio sample player"
        className="relative w-full max-w-md bg-white rounded-2xl p-5 sm:p-6 shadow-2xl border border-[#E4E2EB] overflow-hidden max-h-[90vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between pb-3.5 border-b border-[#E4E2EB] mb-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#0F0E17] flex items-center justify-center text-white shadow-xs">
              <Mic className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-[#0F0E17]">Hear it. Then try it.</h3>
              <p className="text-[11px] text-[#524E5E]">Samples are real audio from the live voice model</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              stop();
              onClose();
            }}
            className="w-8 h-8 sm:w-7 sm:h-7 min-w-[36px] min-h-[36px] rounded-lg bg-[#FAF9FD] hover:bg-[#F0EEF6] border border-[#E4E2EB] flex items-center justify-center text-[#524E5E] hover:text-[#0F0E17] transition-colors"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Real sample */}
        <div className="rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] p-4 mb-4">
          <div className="flex items-center justify-between gap-2 mb-2">
            <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#524E5E]">
              {activeSample?.industry} · {sampleDurationLabel(activeSample?.durationSeconds)}
            </span>
            {isPlaying && <Volume2 className="w-3.5 h-3.5 text-[#10B981]" />}
          </div>
          <p className="text-xs text-[#0F0E17] leading-relaxed mb-3" data-testid="talk-modal-transcript">
            &ldquo;{activeSample?.text}&rdquo;
          </p>
          <div className="grid grid-cols-2 gap-1.5 mb-3">
            {VOICE_SAMPLES.slice(0, 6).map((sample) => (
              <button
                key={sample.id}
                type="button"
                onClick={() => {
                  stop();
                  setActiveId(sample.id);
                }}
                data-testid={`talk-modal-sample-${sample.id}`}
                className={`px-2.5 py-2 min-h-[36px] rounded-lg text-[11px] font-semibold border transition-colors ${
                  sample.id === activeId
                    ? 'bg-[#0F0E17] text-white border-[#0F0E17]'
                    : 'bg-white text-[#524E5E] border-[#E4E2EB] hover:bg-[#F0EEF6]'
                }`}
              >
                {sample.industry}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={handlePlay}
            data-testid="talk-modal-play"
            className="w-full py-2.5 min-h-[44px] rounded-xl text-xs font-semibold text-white bg-[#0F0E17] hover:bg-[#232130] active:scale-[0.98] transition-all flex items-center justify-center"
          >
            {isPlaying ? 'Stop' : 'Play sample'}
          </button>
        </div>

        {errorMessage && (
          <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-xs text-red-600 flex items-start gap-2 mb-4 text-left">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Live session */}
        <div className="rounded-xl border border-[#DCD5FF] bg-[#F7F3FF] p-4">
          <p className="text-xs font-bold text-[#0F0E17] mb-1">
            Talk to a live agent, in your browser
          </p>
          <p className="text-[11px] text-[#524E5E] leading-relaxed mb-3">
            {isAuthenticated
              ? 'Opens your agent console and asks for the microphone once, then streams the same pipeline your callers hear.'
              : 'A live session needs an agent — it uses your phone number, script and knowledge base. Create a free workspace and the mic is requested once, at the start.'}
          </p>
          <button
            type="button"
            onClick={handleStartLive}
            data-testid="talk-modal-start-live"
            className="w-full inline-flex items-center justify-center gap-2 py-2.5 min-h-[44px] rounded-xl text-xs font-semibold text-white bg-[#6344E7] hover:bg-[#5440d0] active:scale-[0.98] transition-all"
          >
            {isAuthenticated ? <Mic className="w-3.5 h-3.5" /> : <LogIn className="w-3.5 h-3.5" />}
            <span>{isAuthenticated ? 'Start live voice' : 'Create a workspace to talk live'}</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
          <p className="text-[10px] text-[#635F70] mt-2 leading-relaxed">
            Audio only. No camera, location, or motion sensors. You can deny the mic and still use
            the samples above.
          </p>
        </div>
      </div>
    </div>
  );
}

export default TalkToMeModal;