import React, { useEffect, useId, useRef, useState } from 'react';
import { AnimatePresence, motion, useInView, useReducedMotion } from 'framer-motion';

const EASE = [0.22, 1, 0.36, 1];
const FLAP_GLYPHS = ' ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+()-→·';

/** Fades and lifts its children in the first time they scroll into view. */
export function Reveal({ as = 'div', delay = 0, y = 28, className, children, ...rest }) {
  const reduce = useReducedMotion();
  const Tag = motion[as] || motion.div;
  return (
    <Tag
      className={className}
      initial={reduce ? false : { opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-10% 0px' }}
      transition={{ duration: 0.8, delay, ease: EASE }}
      {...rest}
    >
      {children}
    </Tag>
  );
}

/**
 * Word-by-word headline reveal. The words are real text in the server-rendered HTML
 * (visible without JS), so the hero heading is never hidden from crawlers or LCP.
 */
export function WordsReveal({ text, className = '', delay = 0, stagger = 0.06 }) {
  const words = text.split(' ');
  // CSS keyframes, not JS: the animation starts with the first paint of the
  // prerendered HTML, before React hydrates.
  return words.map((word, index) => (
    <span
      key={`${word}-${index}`}
      className={`mk-word mk-word-in ${className}`}
      style={{ animationDelay: `${(delay + index * stagger).toFixed(2)}s` }}
    >
      {word}
      {index < words.length - 1 ? ' ' : ''}
    </span>
  ));
}

/**
 * Departure-board text: each cell cycles through glyphs and lands on its letter, left
 * to right. Starts when scrolled into view; `value` changes re-run the flip.
 */
export function SplitFlap({ value, className = '', speed = 38, cycles = 6 }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: '-15% 0px' });
  const reduce = useReducedMotion();
  const target = String(value).toUpperCase();
  const [shown, setShown] = useState(() => target.replace(/[^ ]/g, ' '));

  useEffect(() => {
    if (!inView) return undefined;
    if (reduce) { setShown(target); return undefined; }
    let frame = 0;
    const total = target.length + cycles;
    const id = window.setInterval(() => {
      frame += 1;
      setShown(
        target
          .split('')
          .map((char, index) => {
            if (char === ' ') return ' ';
            if (frame >= index + cycles) return char;
            if (frame < index * 0.5) return ' ';
            return FLAP_GLYPHS[1 + Math.floor(Math.random() * (FLAP_GLYPHS.length - 1))];
          })
          .join('')
      );
      if (frame >= total) window.clearInterval(id);
    }, speed);
    return () => window.clearInterval(id);
  }, [inView, target, reduce, speed, cycles]);

  return (
    <span ref={ref} className={`mk-flap ${className}`} aria-label={value} role="img">
      {shown.split('').map((char, index) => (
        <span key={index} className={`mk-flap-cell${target[index] === ' ' ? ' is-space' : ''}`} aria-hidden="true">
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.span
              key={char + index}
              className="mk-flap-char"
              initial={reduce ? false : { rotateX: -90, opacity: 0.4 }}
              animate={{ rotateX: 0, opacity: 1 }}
              exit={{ rotateX: 90, opacity: 0 }}
              transition={{ duration: 0.09 }}
            >
              {char === ' ' ? ' ' : char}
            </motion.span>
          </AnimatePresence>
        </span>
      ))}
    </span>
  );
}

/** One rolling digit reel. */
function SlotDigit({ digit, reduce }) {
  return (
    <span className="mk-slot" aria-hidden="true">
      <motion.span
        className="mk-slot-reel"
        animate={{ y: `${-digit * 1.3}em` }}
        transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 120, damping: 18, mass: 0.9 }}
      >
        {Array.from({ length: 10 }, (_, n) => <span key={n}>{n}</span>)}
      </motion.span>
    </span>
  );
}

/** Slot-machine number: each digit rolls to its value whenever `value` changes. */
export function CodeSlots({ value, pad = 1, className = '' }) {
  const reduce = useReducedMotion();
  const digits = String(Math.max(0, Math.round(value))).padStart(pad, '0').split('').map(Number);
  return (
    <span className={`mk-slots ${className}`} aria-label={String(value)} role="img">
      {digits.map((digit, index) => <SlotDigit key={digits.length - index} digit={digit} reduce={reduce} />)}
    </span>
  );
}

/** Hover/focus tooltip with a warm glow. The trigger stays keyboard reachable. */
export function WarmTooltip({ label, children }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span
      className="mk-tip-trigger"
      tabIndex={0}
      aria-describedby={id}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {children}
      <AnimatePresence>
        {open && (
          <motion.span
            id={id}
            role="tooltip"
            className="mk-tip"
            initial={{ opacity: 0, y: 6, x: '-50%', scale: 0.96 }}
            animate={{ opacity: 1, y: 0, x: '-50%', scale: 1 }}
            exit={{ opacity: 0, y: 4, x: '-50%', scale: 0.98 }}
            transition={{ duration: 0.18, ease: EASE }}
          >
            {label}
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  );
}

/**
 * A card that tilts toward the pointer while a specular sheen and a conic rim follow
 * it, like light on glass. Pure CSS variables — no camera, no WebGL.
 */
export function ReflectiveCard({ className = '', children, ...rest }) {
  const ref = useRef(null);
  const reduce = useReducedMotion();
  const move = (event) => {
    if (reduce || event.pointerType === 'touch') return;
    const el = ref.current;
    const rect = el.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    el.classList.add('is-hover');
    el.style.setProperty('--rx', `${((0.5 - y) * 7).toFixed(2)}deg`);
    el.style.setProperty('--ry', `${((x - 0.5) * 9).toFixed(2)}deg`);
    el.style.setProperty('--mx', `${(x * 100).toFixed(1)}%`);
    el.style.setProperty('--my', `${(y * 100).toFixed(1)}%`);
    el.style.setProperty('--angle', String(Math.round(Math.atan2(y - 0.5, x - 0.5) * (180 / Math.PI))));
  };
  const leave = () => {
    const el = ref.current;
    el.classList.remove('is-hover');
    el.style.setProperty('--rx', '0deg');
    el.style.setProperty('--ry', '0deg');
    el.style.setProperty('--mx', '50%');
    el.style.setProperty('--my', '50%');
  };
  return (
    <div ref={ref} className={`mk-reflect ${className}`} onPointerMove={move} onPointerLeave={leave} {...rest}>
      {children}
    </div>
  );
}
