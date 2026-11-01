import React from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
import { SonarGrid } from '@/components/ui/sonar-grid';
import { BotAnchor } from './ScrollBot';
import { WordsReveal } from './effects';

const EASE = [0.22, 1, 0.36, 1];

/**
 * The first screen: what Dialtact is, in the headline, and the mascot standing large
 * on the right. The dot field behind pings like a phone line; tap it to send one.
 */
export function HeroSection({ onCreateAgent }) {
  const reduce = useReducedMotion();
  const enter = (delay) => (reduce ? {} : {
    initial: { opacity: 0, y: 16 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.7, delay, ease: EASE },
  });

  return (
    <SonarGrid
      id="top"
      className="mk-hero"
      color="#ffffff"
      spacing={28}
      baseOpacity={0.16}
      pingEvery={2.8}
      pingArea={[0.55, 0.25, 0.9, 0.75]}
      role="region"
      aria-labelledby="mk-hero-title"
      data-bot-say="Hi, I’m Dialtact. Scroll — I’ll walk you through a call."
      data-bot-gesture="RIGHT_HAND_WAVE"
      data-bot-state="HAPPY"
      data-bot-side="right"
    >
      <div className="mk-container mk-hero-grid">
        <div className="mk-hero-copy">
          <h1 id="mk-hero-title">
            <WordsReveal text="AI voice agents that answer every call." delay={0.05} />
          </h1>
          <motion.p className="mk-hero-sub" {...enter(0.5)}>
            Dialtact answers your business line day and night, books appointments and qualifies leads,
            then logs every call where your team already works.
          </motion.p>
          <motion.div className="mk-actions" {...enter(0.65)}>
            <a href="/signin" className="mk-btn mk-btn-primary mk-btn-lg" onClick={(event) => { event.preventDefault(); onCreateAgent(); }}>
              Create your own agent <ArrowRight size={18} aria-hidden="true" />
            </a>
          </motion.div>
        </div>
        <div className="mk-hero-stage">
          <BotAnchor />
        </div>
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
