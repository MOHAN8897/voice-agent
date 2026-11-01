import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Pause, Play } from 'lucide-react';
import { VOICE_SAMPLES, playVoiceSample } from '../services/marketingVoice';
import { BotAnchor, commandBot } from './ScrollBot';

const FEATURED = ['healthcare-clinic', 'real-estate', 'car-dealership', 'restaurant', 'it-support'];
const BARS = 64;

/**
 * What the agent's pipeline is doing while it speaks. Illustrative, and labelled so:
 * the audio is the real model; the log shows the kind of steps a configured agent takes.
 */
const LOGS = {
  'healthcare-clinic': [['understood', 'book appointment', 'ok'], ['looked up', 'doctor schedules', 'ok'], ['found', '2 free slots · Tue', 'blue'], ['holding', 'for caller’s choice', 'warn'], ['next', 'confirm by SMS', 'blue']],
  'real-estate': [['understood', 'property enquiry', 'ok'], ['matched', '3 listings · marina', 'ok'], ['asked', 'buy or rent?', 'blue'], ['captured', 'budget · area', 'ok'], ['next', 'book a viewing', 'blue']],
  'car-dealership': [['understood', 'test drive', 'ok'], ['checked', 'model availability', 'ok'], ['offered', 'Sat 11:00 · Sun 15:30', 'blue'], ['captured', 'licence on file?', 'warn'], ['next', 'calendar invite', 'blue']],
  restaurant: [['understood', 'table reservation', 'ok'], ['checked', 'covers for Friday', 'ok'], ['offered', '19:30 · window', 'blue'], ['noted', 'allergy request', 'warn'], ['next', 'confirmation text', 'blue']],
  'it-support': [['understood', 'tier-one support', 'ok'], ['searched', 'help-centre docs', 'ok'], ['answered', 'reset steps', 'blue'], ['detected', 'needs a human?', 'warn'], ['next', 'warm transfer + notes', 'blue']],
};

function baseWave(seed) {
  return Array.from({ length: BARS }, (_, i) => 0.18 + Math.abs(Math.sin(i * 0.55 + seed) * Math.cos(i * 0.21 + seed * 2)) * 0.8);
}

export function RealCallSection() {
  const samples = useMemo(() => FEATURED.map((id) => VOICE_SAMPLES.find((s) => s.id === id)).filter(Boolean), []);
  const [sampleId, setSampleId] = useState(samples[0]?.id);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const sample = samples.find((s) => s.id === sampleId) || samples[0];
  const shape = useMemo(() => baseWave(samples.indexOf(sample) + 1), [sample, samples]);
  const barsRef = useRef([]);
  const stopRef = useRef(null);
  const startedAt = useRef(0);
  const rafRef = useRef(0);
  const level = useRef(0);

  const stop = () => {
    stopRef.current?.();
    stopRef.current = null;
    cancelAnimationFrame(rafRef.current);
    setPlaying(false);
    commandBot({ release: true });
  };

  useEffect(() => () => { stopRef.current?.(); cancelAnimationFrame(rafRef.current); }, []);

  // Bars breathe with the real analyser level; the played part brightens with progress.
  const animate = () => {
    const elapsed = (performance.now() - startedAt.current) / 1000;
    const p = Math.min(1, elapsed / (sample.durationSeconds || 10));
    setProgress(p);
    barsRef.current.forEach((bar, i) => {
      if (!bar) return;
      const jitter = 0.55 + level.current * 1.6 * (0.6 + Math.random() * 0.4);
      bar.style.transform = `scaleY(${Math.min(1, shape[i] * (i / BARS < p ? jitter : 0.55)).toFixed(3)})`;
    });
    rafRef.current = requestAnimationFrame(animate);
  };

  const toggle = () => {
    if (playing) { stop(); return; }
    setProgress(0);
    setPlaying(true);
    commandBot({ state: 'TALKING', say: `Playing: ${sample.label}. That’s my real voice.`, title: 'On a call', hold: true });
    stopRef.current = playVoiceSample(sample, {
      onLevel: (value) => { level.current = value; },
      onStart: () => { startedAt.current = performance.now(); rafRef.current = requestAnimationFrame(animate); },
      onEnd: () => { setProgress(1); stop(); },
    });
  };

  const choose = (id) => {
    if (playing) stop();
    setSampleId(id);
    setProgress(0);
  };

  const log = LOGS[sample.id] || LOGS['healthcare-clinic'];
  const shownLines = playing || progress >= 1 ? Math.min(log.length, Math.floor(progress * (log.length + 0.6)) + 1) : 0;
  const words = sample.text.split(' ');
  const spoken = Math.round(words.length * progress);

  return (
    <section
      id="demo"
      className="mk-section"
      aria-label="Hear a real call"
      data-bot-say="Press play. This is my real voice."
      data-bot-gesture="EXPLAIN"
      data-bot-state="CURIOUS"
      data-bot-title="A real call"
      data-bot-side="right"
    >
      <div className="mk-container">
        <div className="mk-head">
          <div>
            <h2 className="mk-h2">Hear a real call.</h2>
            <p className="mk-lede">What the caller hears, and what the agent does while it talks.</p>
          </div>
          <div className="mk-head-stage"><BotAnchor /></div>
        </div>

        <div className="mk-card mk-call">
          <div className="mk-call-player">
            <div className="mk-call-top">
              <button type="button" className="mk-play" onClick={toggle} aria-label={playing ? 'Stop the sample call' : `Play the ${sample.label} sample call`} data-testid="mk-demo-play">
                {playing ? <Pause size={18} aria-hidden="true" /> : <Play size={18} className="translate-x-[1px]" aria-hidden="true" />}
              </button>
              <div className="mk-call-meta">
                <strong>Inbound · {sample.industry}</strong>
                <span>{sample.label} · {sample.durationSeconds.toFixed(1)}s · recorded from the live model</span>
              </div>
              <span className={`mk-live-badge${playing ? ' is-on' : ''}`}><span className="mk-rec" />{playing ? 'LIVE' : 'READY'}</span>
            </div>

            <div className="mk-wave" aria-hidden="true">
              {shape.map((h, i) => (
                <span key={i} ref={(el) => { barsRef.current[i] = el; }} className={i / BARS < progress ? 'is-past' : 'is-future'}
                  style={{ height: '100%', transform: `scaleY(${(h * 0.55).toFixed(3)})` }} />
              ))}
            </div>

            <p className="mk-call-quote">
              “<span className="mk-spoken">{words.slice(0, spoken).join(' ')}</span>{spoken ? ' ' : ''}{words.slice(spoken).join(' ')}”
            </p>

            <div className="mk-samples" role="group" aria-label="Choose a sample call">
              {samples.map((s) => (
                <button key={s.id} type="button" className="mk-sample" aria-pressed={s.id === sample.id} onClick={() => choose(s.id)}>
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          <div className="mk-call-log" aria-live="polite">
            <h3 className="mk-call-log-head">Behind the scenes</h3>
            <AnimatePresence initial={false}>
              {log.slice(0, shownLines).map(([verb, what, tone]) => (
                <motion.div key={`${sample.id}-${verb}-${what}`} className="mk-log-line" initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
                  <span>{verb} <span className={tone}>{what}</span></span>
                </motion.div>
              ))}
            </AnimatePresence>
            {shownLines === 0 && <div className="mk-log-line"><span>waiting for a caller <span className="mk-caret" /></span></div>}
            <p className="mk-footnote">Audio from the production voice model. The steps illustrate a configured agent.</p>
          </div>
        </div>
      </div>
    </section>
  );
}
