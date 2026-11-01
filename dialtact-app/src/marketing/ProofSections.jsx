import React, { useEffect, useRef, useState } from 'react';
import { animate, motion, useMotionValue, useReducedMotion, useScroll, useTransform } from 'framer-motion';
import { ArrowLeft, ArrowRight, Building2, Headphones, ShieldCheck, ShoppingBag, Stethoscope, TrendingUp } from 'lucide-react';
import { INDUSTRIES_DATA } from '../data/siteContent';
import { BotAnchor } from './ScrollBot';
import { Reveal } from './effects';

const ICONS = { TrendingUp, Headphones, Building2, Stethoscope, ShieldCheck, ShoppingBag };

/** Draggable, snapping carousel of industries; arrows, dots and keys do the same. */
export function UseCasesSection() {
  const viewportRef = useRef(null);
  const trackRef = useRef(null);
  const x = useMotionValue(0);
  const reduce = useReducedMotion();
  const [index, setIndex] = useState(0);
  const [step, setStep] = useState(384);
  const [maxIndex, setMaxIndex] = useState(INDUSTRIES_DATA.length - 1);

  useEffect(() => {
    const measure = () => {
      const card = trackRef.current?.children[0];
      const viewport = viewportRef.current;
      if (!card || !viewport) return;
      const s = card.getBoundingClientRect().width + 16;
      setStep(s);
      const visible = Math.max(1, Math.floor((viewport.clientWidth + 16) / s));
      setMaxIndex(Math.max(0, INDUSTRIES_DATA.length - visible));
    };
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, []);

  const goTo = (next) => {
    const clamped = Math.max(0, Math.min(maxIndex, next));
    setIndex(clamped);
    animate(x, -clamped * step, reduce ? { duration: 0 } : { type: 'spring', stiffness: 260, damping: 32 });
  };

  useEffect(() => { goTo(Math.min(index, maxIndex)); }, [step, maxIndex]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <section
      id="industries"
      className="mk-section"
      aria-label="Use cases by industry"
      data-bot-say="Drag the cards — find the calls you’re missing."
      data-bot-gesture="PRESENT_RIGHT"
      data-bot-state="CONFIDENT"
      data-bot-title="Use cases"
      data-bot-side="left"
    >
      <div className="mk-container">
        <div className="mk-head mk-head--bot-left">
          <div className="mk-head-stage"><BotAnchor /></div>
          <div>
            <h2 className="mk-h2">Built for teams that live on the phone.</h2>
            <p className="mk-lede">Start from the calls your customers already make.</p>
          </div>
        </div>

        <div className="mk-carousel" onKeyDown={(e) => { if (e.key === 'ArrowRight') goTo(index + 1); if (e.key === 'ArrowLeft') goTo(index - 1); }}>
          <div ref={viewportRef} className="mk-carousel-viewport" role="region" aria-roledescription="carousel" aria-label="Industries" tabIndex={0}>
            <motion.div
              ref={trackRef}
              className="mk-carousel-track"
              style={{ x }}
              drag="x"
              dragConstraints={{ left: -maxIndex * step, right: 0 }}
              dragElastic={0.12}
              onDragEnd={(_, info) => {
                const projected = x.get() + info.velocity.x * 0.2;
                goTo(Math.round(-projected / step));
              }}
            >
              {INDUSTRIES_DATA.map((item, i) => {
                const Icon = ICONS[item.icon] || Building2;
                const current = i === index;
                return (
                  <article key={item.id} className={`mk-card mk-uc${i < index ? ' is-dim' : ''}`} aria-roledescription="slide" aria-label={`${i + 1} of ${INDUSTRIES_DATA.length}: ${item.title}`}>
                    <span className="mk-uc-icon"><Icon size={20} aria-hidden="true" /></span>
                    <h3>{item.title}</h3>
                    <small>{item.subtitle}</small>
                    <p>{item.desc}</p>
                    <ul>{item.examples.map((example) => <li key={example}>{example}</li>)}</ul>
                  </article>
                );
              })}
            </motion.div>
          </div>
          <div className="mk-carousel-ctrl">
            <button type="button" className="mk-arrow" onClick={() => goTo(index - 1)} disabled={index === 0} aria-label="Previous industry"><ArrowLeft size={18} /></button>
            <button type="button" className="mk-arrow" onClick={() => goTo(index + 1)} disabled={index >= maxIndex} aria-label="Next industry"><ArrowRight size={18} /></button>
            <div className="mk-dots">
              {Array.from({ length: maxIndex + 1 }, (_, i) => (
                <button key={i} type="button" aria-label={`Go to slide ${i + 1}`} aria-current={i === index ? 'true' : undefined} onClick={() => goTo(i)} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/** The workspace screenshot with call cards floating over it at different scroll speeds. */
export function WorkspaceSection() {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'end start'] });
  const shotY = useTransform(scrollYProgress, [0, 1], [80, -60]);
  const shotRotate = useTransform(scrollYProgress, [0, 0.5], [10, 0]);
  const aY = useTransform(scrollYProgress, [0, 1], [180, -160]);
  const bY = useTransform(scrollYProgress, [0, 1], [260, -260]);
  const cY = useTransform(scrollYProgress, [0, 1], [120, -100]);

  return (
    <section
      ref={ref}
      id="workspace"
      className="mk-section"
      aria-label="Review every call in your workspace"
      data-bot-say="After the call: transcript, summary, outcome."
      data-bot-gesture="REACH_LEFT"
      data-bot-state="THINKING"
      data-bot-title="After the call"
      data-bot-side="right"
    >
      <div className="mk-container">
        <div className="mk-head">
          <div>
            <h2 className="mk-h2">Every call, written up.</h2>
            <p className="mk-lede">Transcript, details, outcome and cost for each conversation, plus a lead list to work from.</p>
          </div>
          <div className="mk-head-stage"><BotAnchor /></div>
        </div>

        <div className="mk-parallax" style={{ perspective: 1400 }}>
          <motion.div className="mk-parallax-shot" style={{ y: shotY, rotateX: shotRotate }}>
            <img src="/images/landing/workspace-preview.png" alt="The Dialtact workspace showing calls, transcripts and outcomes" loading="lazy" decoding="async" width="1320" height="850" />
          </motion.div>
          <motion.div className="mk-float" style={{ y: aY, left: 0, top: '18%' }}>
            <b>Captured</b>name · phone · budget<br />preferred day: Tuesday
          </motion.div>
          <motion.div className="mk-float" style={{ y: bY, right: 0, top: '8%' }}>
            <b>Outcome</b><span style={{ color: 'var(--mk-green)' }}>● Qualified</span> → callback booked
          </motion.div>
          <motion.div className="mk-float" style={{ y: cY, right: '12%', bottom: '10%' }}>
            <b>Summary</b>Asked about weekend viewings;<br />wants a 3-bed near the school.
          </motion.div>
        </div>
        <Reveal><p className="mk-caption">Example workspace. Your own calls replace it on day one.</p></Reveal>
      </div>
    </section>
  );
}
