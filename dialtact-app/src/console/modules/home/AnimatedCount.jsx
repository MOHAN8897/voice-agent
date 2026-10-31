import React from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { EASE_OUT } from './motion';

/**
 * A count that rolls when it changes (old value slides up and out, new one in).
 * Only for counts that change occasionally — never for per-second timers.
 * Reduced motion: the surrounding MotionConfig turns this into a plain fade.
 */
export function AnimatedCount({ value, className = '' }) {
  return (
    <span className={`relative inline-grid overflow-hidden align-baseline ${className}`}>
      <AnimatePresence initial={false} mode="popLayout">
        <motion.span
          key={String(value)}
          className="col-start-1 row-start-1 tabular-nums"
          initial={{ y: '60%', opacity: 0 }}
          animate={{ y: 0, opacity: 1, transition: { duration: 0.22, ease: EASE_OUT } }}
          exit={{ y: '-60%', opacity: 0, transition: { duration: 0.15, ease: 'easeOut' } }}
        >
          {value}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}
