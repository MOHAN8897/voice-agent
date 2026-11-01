import React, { useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { useGSAP } from '@gsap/react';
import { AI_EMPLOYEE_CAPABILITIES } from '../data/siteContent';
import { commandBot } from './ScrollBot';
import { ReflectiveCard } from './effects';

gsap.registerPlugin(ScrollTrigger, useGSAP);

const STEP = 360 / 14; // degrees between wheel items
const RADIUS = 210;
const BOT_MOOD = ['CURIOUS', 'THINKING', 'CONFIDENT', 'HAPPY', 'LISTENING', 'THINKING', 'CONFIDENT', 'EXCITED'];

/**
 * A drum of capabilities that turns as the section scrolls (pinned on desktop), or
 * with click, drag-free arrow keys, on any device. The selected one is shown on a
 * reflective card beside it.
 */
export function CapabilitiesSection() {
  const scope = useRef(null);
  const wheelRef = useRef(null);
  const reduce = useReducedMotion();
  const [active, setActive] = useState(0);
  const items = AI_EMPLOYEE_CAPABILITIES;
  const cap = items[active];
  const activeRef = useRef(0);

  const select = (index, fromScroll = false) => {
    const next = Math.max(0, Math.min(items.length - 1, index));
    if (next === activeRef.current) return;
    activeRef.current = next;
    setActive(next);
    commandBot({ state: BOT_MOOD[next % BOT_MOOD.length], say: `${items[next].title}: ${items[next].highlight.toLowerCase()}.`, title: items[next].badge });
    if (!fromScroll) {
      // Keep the pinned scroll position in step with a click, so scrolling resumes from here.
      const st = ScrollTrigger.getById('mk-cap-pin');
      if (st) {
        const y = st.start + (st.end - st.start) * (next / (items.length - 1));
        if (window.__dialtactLenis) window.__dialtactLenis.scrollTo(y, { duration: 0.8 });
        else window.scrollTo({ top: y, behavior: 'smooth' });
      }
    }
  };

  useGSAP(() => {
    const mm = gsap.matchMedia();
    mm.add('(min-width: 1024px) and (prefers-reduced-motion: no-preference)', () => {
      ScrollTrigger.create({
        id: 'mk-cap-pin',
        trigger: '.mk-cap-pin',
        start: 'top top+=72',
        end: `+=${items.length * 32}%`,
        pin: true,
        scrub: true,
        onUpdate: (self) => select(Math.round(self.progress * (items.length - 1)), true),
      });
    });
    return () => mm.revert();
  }, { scope });

  const onKey = (event) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') { event.preventDefault(); select(active + 1); }
    if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') { event.preventDefault(); select(active - 1); }
  };

  return (
    <section
      ref={scope}
      id="capabilities"
      className="mk-section"
      aria-label="What the AI voice agent can do"
      data-bot-say="Scroll to turn the wheel."
      data-bot-gesture="SCAN"
      data-bot-state="CURIOUS"
      data-bot-title="Capabilities"
    >
      <div className="mk-cap-pin">
        <div className="mk-container">
          <h2 className="mk-h2">Everything a good receptionist does.</h2>

          <div className="mk-cap">
            <div>
              <div
                ref={wheelRef}
                className="mk-wheel"
                role="listbox"
                tabIndex={0}
                aria-label="Capabilities"
                aria-activedescendant={`mk-cap-${cap.id}`}
                onKeyDown={onKey}
              >
                <motion.div
                  className="mk-wheel-drum"
                  style={{ z: -RADIUS }}
                  animate={{ rotateX: active * STEP }}
                  transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 110, damping: 20 }}
                >
                  {items.map((item, index) => (
                    <div
                      key={item.id}
                      id={`mk-cap-${item.id}`}
                      role="option"
                      aria-selected={index === active}
                      className={`mk-wheel-item${index === active ? ' is-active' : ''}`}
                      style={{ transform: `rotateX(${-index * STEP}deg) translateZ(${RADIUS}px)`, opacity: Math.max(0, 1 - Math.abs(index - active) * 0.22) }}
                      onClick={() => select(index)}
                    >
                      {item.title}
                    </div>
                  ))}
                </motion.div>
                <div className="mk-wheel-lens" aria-hidden="true" />
              </div>
              <p className="mk-wheel-hint">Scroll, click or use the arrow keys.</p>
            </div>

            <ReflectiveCard>
              <AnimatePresence mode="wait">
                <motion.div key={cap.id} initial={{ opacity: 0, y: 14, filter: 'blur(6px)' }} animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                  exit={{ opacity: 0, y: -10, filter: 'blur(6px)' }} transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}>
                  <span className="mk-reflect-badge">{cap.badge}</span>
                  <h3>{cap.title}</h3>
                  <p>{cap.desc}</p>
                </motion.div>
              </AnimatePresence>
              <div className="mk-reflect-foot"><span>{cap.highlight}</span><b>● ready</b></div>
            </ReflectiveCard>
          </div>
        </div>
      </div>
    </section>
  );
}
