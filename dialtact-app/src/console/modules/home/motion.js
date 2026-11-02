/**
 * Motion presets for the Home feed (DESIGN.md → Motion): short, ease-out, springs
 * with high damping, no bounce. Under prefers-reduced-motion the feed is wrapped in
 * `<MotionConfig reducedMotion="user">`, which drops transform and layout animation
 * and keeps the opacity fades.
 */
export const EASE_OUT = [0.16, 1, 0.3, 1];

/** Rows entering, leaving and reordering. */
export const rowTransition = { type: 'spring', stiffness: 520, damping: 46, mass: 0.8 };

export const rowVariants = {
  initial: { opacity: 0, y: -6 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.22, ease: EASE_OUT } },
  exit: { opacity: 0, transition: { duration: 0.15, ease: 'easeOut' } },
};

/** Filter changes: the list crossfades. */
export const crossfade = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: 0.2, ease: EASE_OUT } },
  exit: { opacity: 0, transition: { duration: 0.12, ease: 'easeOut' } },
};

/** The detail drawer (desktop, from the right) and sheet (phones, from the bottom). */
export const drawerSpring = { type: 'spring', stiffness: 420, damping: 42, mass: 0.9 };

/**
 * Height reveal. `clip`, not `hidden`: a hidden box is a scroll container, so a
 * sticky header inside it (Home's "Needs you") stuck to the box instead of the
 * page and sat over the first row until transitionEnd, which can come late.
 * A clip box clips the same way without capturing sticky positioning.
 */
export const collapse = {
  initial: { opacity: 0, height: 0, overflow: 'clip' },
  animate: { opacity: 1, height: 'auto', transition: { duration: 0.22, ease: EASE_OUT }, transitionEnd: { overflow: 'visible' } },
  exit: { opacity: 0, height: 0, overflow: 'clip', transition: { duration: 0.16, ease: 'easeOut' } },
};
