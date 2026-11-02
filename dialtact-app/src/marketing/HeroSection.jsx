import React, { useEffect, useLayoutEffect, useRef } from 'react';
import { motion, useMotionValue, useReducedMotion, useScroll, useSpring, useTransform } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
import { SonarGrid } from '@/components/ui/sonar-grid';
import { BotAnchor } from './ScrollBot';
import { WordsReveal } from './effects';

const EASE = [0.22, 1, 0.36, 1];

/**
 * The first screen, layered for parallax: the promise set huge behind the mascot and the
 * mascot standing in front of it. Scrolling pulls the layers apart (the words sink and
 * fade, the mascot rises); the mouse shifts the words. Reduced motion keeps them still.
 */
export function HeroSection({ onCreateAgent }) {
  const reduce = useReducedMotion();
  const ref = useRef(null);
  const giantRef = useRef(null);
  const stageRef = useRef(null);

  // Stand the mascot so its head is ~40% of the way down the giant letters: it hides
  // their lower part only, and the words above it stay readable. Measured from layout
  // offsets, which the parallax transforms do not change.
  useLayoutEffect(() => {
    const place = () => {
      const hero = ref.current;
      const giant = giantRef.current;
      if (!hero || !giant || !stageRef.current) return;
      let top = 0;
      for (let el = giant; el && el !== hero; el = el.offsetParent) top += el.offsetTop;
      stageRef.current.style.setProperty('--stage-top', `${Math.round(top + giant.offsetHeight * 0.4)}px`);
      hero.style.setProperty('--say-top', `${Math.round(top - 12)}px`);
    };
    place();
    document.fonts?.ready?.then(place);
    window.addEventListener('resize', place);
    return () => window.removeEventListener('resize', place);
  }, []);
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end start'] });
  const still = useMotionValue(0);
  const progress = reduce ? still : scrollYProgress;
  const words = useTransform(progress, [0, 1], [0, 220]);
  const wordsScale = useTransform(progress, [0, 1], [1, 1.12]);
  const wordsFade = useTransform(progress, [0, 0.8], [1, 0.15]);
  const stage = useTransform(progress, [0, 1], [0, -90]);
  const mxRaw = useMotionValue(0);
  const mx = useSpring(mxRaw, { stiffness: 60, damping: 18 });
  const wordsX = useTransform(mx, (v) => v * -14);

  useEffect(() => {
    if (reduce) return undefined;
    const onMove = (event) => {
      if (event.pointerType !== 'mouse') return;
      mxRaw.set(event.clientX / window.innerWidth - 0.5);
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    return () => window.removeEventListener('pointermove', onMove);
  }, [reduce, mxRaw]);

  const enter = (delay) => (reduce ? {} : {
    initial: { opacity: 0, y: 16 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.7, delay, ease: EASE },
  });

  return (
    <SonarGrid
      ref={ref}
      id="top"
      className="mk-hero"
      color="#ffffff"
      spacing={28}
      baseOpacity={0.06}
      pingEvery={3.4}
      pingArea={[0.3, 0.3, 0.7, 0.7]}
      role="region"
      aria-labelledby="mk-hero-title"
      data-bot-say="Hi, I’m Dialtact. Scroll — I’ll walk you through a call."
      data-bot-gesture="RIGHT_HAND_WAVE"
      data-bot-state="HAPPY"
      data-bot-side="center"
      data-bot-bubble-at=".mk-hero-say"
    >
      {/* Where the speech bubble sits: above "call.", clear of the letters. */}
      <span className="mk-hero-say" aria-hidden="true" />

      <h1 id="mk-hero-title" className="mk-hero-title">
        <motion.span className="mk-hero-lockup" style={{ y: words, x: wordsX, scale: wordsScale, opacity: wordsFade }}>
          <motion.span className="mk-hero-lead" {...enter(0.1)}>AI voice agents that answer </motion.span>
          <span ref={giantRef} className="mk-hero-giant"><WordsReveal text="every call." delay={0.2} stagger={0.12} /></span>
        </motion.span>
      </h1>

      <motion.div ref={stageRef} className="mk-hero-stage" style={{ y: stage }}>
        <BotAnchor />
      </motion.div>

      <div className="mk-container mk-hero-foot">
        <motion.p className="mk-hero-sub" {...enter(0.55)}>
          Dialtact answers your business line day and night, books appointments and qualifies leads,
          then logs every call where your team already works.
        </motion.p>
        <motion.div className="mk-actions" {...enter(0.7)}>
          <a href="/signin" className="mk-btn mk-btn-primary mk-btn-lg" data-bot-hover="Let’s build yours. It takes an afternoon." data-bot-hover-move="HOP" onClick={(event) => { event.preventDefault(); onCreateAgent(); }}>
            Create your own agent <ArrowRight size={18} aria-hidden="true" />
          </a>
        </motion.div>
      </div>
    </SonarGrid>
  );
}

/** The mascot comes to the centre of the page and makes the one promise. */
export function StatementSection() {
  return (
    <section
      className="mk-section mk-statement"
      aria-labelledby="mk-statement-title"
      data-bot-say="First ring, every time. Even at 2 a.m."
      data-bot-gesture="STRETCH"
      data-bot-state="CONFIDENT"
      data-bot-side="center"
    >
      <div className="mk-container">
        <div className="mk-statement-stage"><BotAnchor /></div>
        <h2 id="mk-statement-title" className="mk-h2 mk-center">Picks up on the first ring.</h2>
        <p className="mk-lede mk-center">No hold music, no voicemail. Every caller gets an answer, day or night.</p>
      </div>
    </section>
  );
}
