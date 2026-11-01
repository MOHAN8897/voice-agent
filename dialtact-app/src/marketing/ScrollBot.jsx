import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { LazyDialtactScene } from '../three/LazyDialtactScene';
import { voiceAgent } from '../services/voiceAgent';

/**
 * Fixed canvas size. Size changes are a CSS scale, so WebGL never resizes mid-scroll;
 * it is sized for the largest slot (the hero's) so the mascot is never upscaled. The
 * canvas is wider than the mascot so a full reach toward the cards is never clipped;
 * it takes no clicks itself (a hit area over the body does), so the empty sides never
 * block the page beside it.
 */
const BOT_W = 760;
const BOT_H = 565;

/** Lengths of the Blender-authored one-shot clips (scripts/blender/add_scroll_clips.py). */
const CLIP_MS = {
  ARRIVE: 1400, POINT_LEFT: 2200, POINT_RIGHT: 2200, NOD: 1200, SCAN: 2800, HOP: 1350, PRESENT: 1850,
  STRETCH: 2100, EXPLAIN: 2200, PRESENT_LEFT: 1950, PRESENT_RIGHT: 1950,
  REACH_LEFT: 2500, REACH_RIGHT: 2500,
  RIGHT_HAND_WAVE: 3200, LEFT_HAND_WAVE: 3200, CELEBRATE: 2800, DANCE: 3000, DOUBLE_WAVE: 2800,
};

/**
 * The flight between slots is a slightly underdamped spring: it pulls away gently,
 * peaks mid-way and settles in about 1.2s with a hint of overshoot, never a jump.
 */
const SPRING_W = 4.4;
const SPRING_Z = 0.82;
/** How fast the mascot's size follows the slot it is heading to, per second. */
const SCALE_RATE = 2.6;
/** The crouch before take-off (anticipation), in seconds. */
const WINDUP_S = 0.18;
/** Reduced motion fades out, jumps, and fades back in (seconds each way). */
const FADE_OUT_S = 0.2;
const FADE_IN_S = 0.35;
/** Taps this close together count as a burst of excitement. */
const COMBO_MS = 1600;
/** Within this many pixels of its slot the mascot counts as arrived. */
const ARRIVED_PX = 36;

const CLICK_LINES = [
  { moves: ['STRETCH'], say: 'Ready for the next call.' },
  { moves: ['EXPLAIN'], say: 'I answer from your documents.' },
  { moves: ['DOUBLE_WAVE'], say: 'Many calls at once.' },
  { moves: ['PRESENT'], say: 'Ask me anything a caller would.' },
];

/** Where a tap lands decides the reaction: head, feet, or the hand on that side. */
const TAP_HEAD = { moves: ['NOD'], mood: 'SURPRISED', say: 'Hey, that tickles.' };
const TAP_FEET = { moves: ['HOP'], mood: 'HAPPY', say: 'First ring. Every time.', jump: 620 };
const TAP_LEFT = { moves: ['RIGHT_HAND_WAVE'], mood: 'HAPPY', say: 'Hi there.' };
const TAP_RIGHT = { moves: ['LEFT_HAND_WAVE'], mood: 'HAPPY', say: 'Hello again.' };
const TAP_COMBO = { moves: ['CELEBRATE'], mood: 'EXCITED', say: "Okay, okay. I'm awake!", jump: 820 };

/** Hovering says hello, at most this often. */
const HOVER_COOLDOWN_MS = 9000;

/** Ask the mascot to do something from anywhere on the page. */
export function commandBot(detail) {
  if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('dialtact:bot', { detail }));
}

/**
 * Place a `<BotAnchor />` where the mascot should stand in a section. It is only a slot;
 * its parent sets the size (the hero's is the largest, so the mascot starts big).
 */
export function BotAnchor({ className = '', style }) {
  return <div className={`mk-bot-anchor ${className}`} style={style} aria-hidden="true" />;
}

/**
 * Shown instead of the 3D mascot while it boots, and if WebGL is unavailable: a
 * projector with rings and a scan line, never a flat picture pasted on the page.
 */
function HoloFallback({ message, onRetry, loading }) {
  return (
    <div className={`mk-holo${loading ? ' is-loading' : ''}`} data-mascot-state="preview">
      {!loading && (
        <img className="mk-holo-figure" src="/images/Dialtact_call_assistant_fallback.png" alt="" width="320" height="320" decoding="async" />
      )}
      <div className="mk-holo-scan" aria-hidden="true" />
      <p className="mk-holo-label" role="status">
        {loading ? 'Loading Dialtact…' : message || 'Dialtact'}
      </p>
      {onRetry && (
        <button type="button" className="mk-holo-retry" onClick={(event) => { event.stopPropagation(); onRetry(); }}>
          Retry 3D
        </button>
      )}
    </div>
  );
}

const renderHolo = (props) => <HoloFallback {...props} />;

function visibleBox(rect, vw, vh) {
  return rect.width > 4 && rect.height > 4 && rect.bottom > 60 && rect.top < vh - 60 && rect.right > 0 && rect.left < vw;
}

/**
 * The 3D Dialtact mascot, mounted once and flown between sections as the page scrolls.
 *
 * Each `<section data-bot-say>` declares what happens there: `data-bot-gesture` (a
 * one-shot clip, e.g. REACH_RIGHT to touch the cards beside the slot), `data-bot-state`
 * (the mood it settles into) and `data-bot-side` (where the slot is). The section
 * crossing the middle of the viewport is the active one; if it holds a visible
 * `.mk-bot-anchor`, the mascot glides into that slot over about a second, otherwise it
 * docks small in the corner. The gesture plays once it has arrived. While travelling it
 * leans and looks where it is going; settled, it looks at the content unless the mouse
 * is moving. `commandBot({ moves, state, say, hold })`
 * lets a section take over — the voice demo does, so the mouth follows the audio.
 */
export function ScrollBot({ controllerRef, hidden = false }) {
  const botRef = useRef(null);
  const tiltRef = useRef(null);
  const bubbleRef = useRef(null);
  const pointerRef = useRef({ x: 0, y: 0 });
  const mouse = useRef({ x: 0, y: 0, at: 0 });
  // Position in page coordinates: inside a section the mascot rides with the page like
  // any element; between sections it eases over to the next slot.
  const pos = useRef({
    px: -9999, py: 0, s: 0.4, ready: false, key: null,
    vx: 0, vy: 0, // flight velocity, px/s
    tilt: 0, tiltV: 0, // lean, degrees
    sq: 0, sqV: 0, // squash (<0) and stretch (>0)
    hop: 0, hopV: 0, // a jump, canvas px (negative is up)
    windup: 0, trip: 0, arc: 0, arrived: false, press: false,
    fade: 1, leaving: false,
  });
  const taps = useRef([]);
  const [bursts, setBursts] = useState([]);
  const pending = useRef(null);
  const docked = useRef(true);
  const active = useRef(null);
  const hold = useRef(null);
  const timers = useRef([]);
  const clickIndex = useRef(0);
  const [mountScene, setMountScene] = useState(false);
  const [bubble, setBubble] = useState(null);
  const [isDocked, setIsDocked] = useState(true);
  const bubbleTimer = useRef(0);
  const lastHover = useRef(0);
  const lastFrame = useRef(0);

  const say = useCallback((text, title = 'Dialtact', ttl = 0) => {
    window.clearTimeout(bubbleTimer.current);
    setBubble(text ? { text, title, key: `${title}:${text}` } : null);
    if (ttl) bubbleTimer.current = window.setTimeout(() => setBubble(null), ttl);
  }, []);

  /** Play gestures back to back, then settle into `mood`. Replaces any queued sequence. */
  const perform = useCallback((moves, mood) => {
    timers.current.forEach(window.clearTimeout);
    timers.current = [];
    const ctrl = controllerRef.current;
    if (!ctrl) return;
    // Gestures play under reduced motion too: they move in place, not across the page.
    const queue = moves.filter(Boolean);
    let at = 0;
    const mark = (move) => { if (botRef.current) botRef.current.dataset.botMove = move; };
    queue.forEach((move) => {
      timers.current.push(window.setTimeout(() => { mark(move); controllerRef.current?.setState(move); }, at));
      at += CLIP_MS[move] || 1500;
    });
    // `data-bot-move` names the clip playing now, so the choreography is observable.
    timers.current.push(window.setTimeout(() => mark(mood || 'IDLE'), at));
    // Mood names are expressions: setting one never interrupts a running gesture.
    if (mood) timers.current.push(window.setTimeout(() => controllerRef.current?.setState(mood), queue.length ? 60 : 0));
  }, [controllerRef]);

  const enterSection = useCallback((section) => {
    if (!section) return;
    perform([section.dataset.botGesture], section.dataset.botState || 'IDLE');
  }, [perform]);

  // Start the 3D bundle and model download right away: the placeholder is only a stopgap.
  useEffect(() => {
    const id = window.requestAnimationFrame(() => setMountScene(true));
    return () => window.cancelAnimationFrame(id);
  }, []);

  useEffect(() => () => timers.current.forEach(window.clearTimeout), []);

  useEffect(() => {
    const onCommand = (event) => {
      const detail = event.detail || {};
      if (detail.release) {
        hold.current = null;
        const section = active.current;
        perform([], section?.dataset.botState || 'IDLE');
        say(section?.dataset.botSay || null, section?.dataset.botTitle);
        return;
      }
      if (detail.hold) hold.current = detail;
      if (detail.moves || detail.state) perform(detail.moves || [], detail.state);
      if (detail.say) say(detail.say, detail.title || 'Dialtact', detail.hold ? 0 : 5000);
    };
    window.addEventListener('dialtact:bot', onCommand);
    return () => window.removeEventListener('dialtact:bot', onCommand);
  }, [perform, say]);

  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const sections = Array.from(document.querySelectorAll('[data-bot-say]'));
    let raf = 0;

    const tick = () => {
      const now = performance.now();
      const dt = Math.min(0.1, (now - (lastFrame.current || now)) / 1000);
      lastFrame.current = now;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const sy = window.scrollY;
      const mid = vh * 0.5;
      const section = sections.find((el) => {
        const r = el.getBoundingClientRect();
        return r.top <= mid && r.bottom > mid;
      }) || null;

      const anchor = section?.querySelector('.mk-bot-anchor');
      const rect = anchor?.getBoundingClientRect();
      let tx; let ty; let ts;
      const nowDocked = !(rect && visibleBox(rect, vw, vh));
      if (!nowDocked) {
        ts = rect.height / BOT_H;
        tx = rect.left + rect.width / 2 - (BOT_W * ts) / 2;
        ty = rect.top;
      } else {
        ts = vw < 768 ? 0.21 : 0.28;
        // The mascot's body is the middle ~45% of the canvas; dock that in the corner.
        tx = vw - BOT_W * ts * 0.72 - (vw < 768 ? 4 : 16);
        ty = vh - BOT_H * ts - (vw < 768 ? 4 : 8);
      }

      // A new section (or the slot coming into view) queues its gesture; it plays once
      // the mascot has actually arrived, not while it is still on its way.
      const sectionChanged = section !== active.current;
      const landed = nowDocked !== docked.current && !nowDocked;
      if (sectionChanged || landed) {
        active.current = section;
        if (section && !hold.current) {
          pending.current = section;
          if (vw < 768) say(null);
        }
      }
      if (nowDocked !== docked.current) {
        docked.current = nowDocked;
        setIsDocked(nowDocked);
        if (nowDocked && !hold.current) {
          window.clearTimeout(bubbleTimer.current);
          bubbleTimer.current = window.setTimeout(() => setBubble(null), 2500);
        }
      }

      const p = pos.current;
      const tpy = ty + sy;
      // The springs are stepped at 240Hz or finer, so a slow device's long frames (up to
      // 0.1s) cannot make them overshoot and blow up.
      const steps = Math.max(1, Math.ceil(dt * 240));
      const h = dt / steps;
      const key = nowDocked ? 'dock' : sections.indexOf(section);
      if (!p.ready) {
        // Reduced motion appears in place; otherwise it flies in from the right edge.
        p.px = reduce ? tx : vw + 40; p.py = tpy; p.s = ts; p.ready = true; p.key = key;
      }
      let distance = Math.hypot(tx - p.px, tpy - p.py);
      if (key !== p.key) {
        p.key = key;
        // Leaving a slot it had settled in: crouch first, then fly (a retarget mid-flight
        // just bends the path). Reduced motion fades out and back in instead.
        if (p.arrived && distance > ARRIVED_PX * 3) {
          if (reduce) p.leaving = true;
          else { p.windup = WINDUP_S; p.trip = distance; }
        }
      }

      if (reduce) {
        if (p.leaving) {
          p.fade = Math.max(0, p.fade - dt / FADE_OUT_S);
          if (p.fade === 0) p.leaving = false;
        } else {
          p.fade = Math.min(1, p.fade + dt / FADE_IN_S);
          p.px = tx; p.py = tpy; p.s = ts;
        }
        p.vx = 0; p.vy = 0; p.windup = 0;
      } else if (nowDocked && distance < ARRIVED_PX && !p.windup) {
        // Docked and arrived: stay glued to the corner while the page scrolls.
        p.px = tx; p.py = tpy; p.vx = 0; p.vy = 0;
      } else if (p.windup > 0) {
        p.windup = Math.max(0, p.windup - dt);
      } else {
        // Spring toward the slot: slow out, fast through the middle, slow in.
        const k = SPRING_W * SPRING_W;
        const c = 2 * SPRING_Z * SPRING_W;
        for (let i = 0; i < steps; i += 1) {
          p.vx += (k * (tx - p.px) - c * p.vx) * h;
          p.vy += (k * (tpy - p.py) - c * p.vy) * h;
          p.px += p.vx * h;
          p.py += p.vy * h;
        }
      }
      if (!reduce) p.s += (ts - p.s) * (1 - Math.exp(-dt * SCALE_RATE));
      distance = Math.hypot(tx - p.px, tpy - p.py);
      const speed = Math.hypot(p.vx, p.vy);

      // The body, animated like a drawn character: it crouches before take-off, stretches
      // while it flies, squashes when it lands and when pressed, and its lean overshoots
      // and swings back when it stops. All of it is springs, so it can be interrupted.
      let sqTarget = 0;
      if (p.press) sqTarget = -0.1;
      else if (p.windup > 0) sqTarget = -0.09;
      else if (!reduce) sqTarget = Math.min(0.1, speed / 9000);
      const tiltTarget = reduce ? 0 : Math.max(-10, Math.min(10, p.vx * 0.011));
      for (let i = 0; i < steps; i += 1) {
        p.sqV += (260 * (sqTarget - p.sq) - 13 * p.sqV) * h;
        p.sq = Math.max(-0.2, Math.min(0.2, p.sq + p.sqV * h));
        p.tiltV += (120 * (tiltTarget - p.tilt) - 10 * p.tiltV) * h;
        p.tilt += p.tiltV * h;
        if (p.hop < 0 || p.hopV !== 0) {
          p.hopV += 2600 * h;
          p.hop += p.hopV * h;
          if (p.hop >= 0) { p.hop = 0; p.hopV = 0; p.sqV -= 1.6; }
        }
      }
      // It flies in an arc, not a straight line: highest half-way through the trip.
      const progress = p.trip > 0 ? Math.max(0, Math.min(1, 1 - distance / p.trip)) : 1;
      const arcTarget = reduce || p.trip <= 0 ? 0 : -Math.sin(Math.PI * progress) * Math.min(90, p.trip * 0.14);
      if (progress >= 1) p.trip = 0;
      // Eased, so a new target mid-flight bends the path instead of snapping it.
      p.arc += (arcTarget - p.arc) * (1 - Math.exp(-dt * 8));
      const arc = p.arc;

      // Keep it at least partly on screen while it catches up with a fast scroll.
      const x = p.px;
      const y = Math.max(-BOT_H * p.s * 0.5, Math.min(vh - BOT_H * p.s * 0.5, p.py - sy + arc));

      const arrived = distance < ARRIVED_PX && !p.leaving && p.windup === 0;
      // Touching down: a quick squash, like a landing.
      if (arrived && !p.arrived && !reduce && speed > 60) p.sqV -= 1.4;
      p.arrived = arrived;
      if (arrived && pending.current) {
        const next = pending.current;
        pending.current = null;
        // A section that took over on the way (the demo's call) keeps its line and mood.
        if (!hold.current) {
          enterSection(next);
          if (vw >= 768) say(next.dataset.botSay, next.dataset.botTitle || 'Dialtact', nowDocked ? 4500 : 0);
        }
      }
      if (botRef.current && botRef.current.dataset.arrived !== String(arrived)) botRef.current.dataset.arrived = String(arrived);

      const mouseFresh = now - mouse.current.at < 2500;
      if (!arrived) {
        // Look where it is going.
        pointerRef.current.x = Math.max(-1, Math.min(1, (tx - p.px) / 300));
        pointerRef.current.y = Math.max(-1, Math.min(1, -(tpy - p.py) / 300));
      } else if (mouseFresh) {
        pointerRef.current.x = mouse.current.x;
        pointerRef.current.y = mouse.current.y;
      } else {
        // At rest: face the copy it is standing beside, or the visitor when centred.
        const side = section?.dataset.botSide;
        pointerRef.current.x = nowDocked ? -0.2 : side === 'left' ? 0.3 : side === 'right' ? -0.3 : 0;
        pointerRef.current.y = -0.05;
      }

      if (botRef.current) {
        botRef.current.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0) scale(${p.s.toFixed(4)})`;
      }
      if (tiltRef.current) {
        const sy2 = 1 + p.sq;
        const sx2 = 1 - p.sq * 0.55; // keep the volume: taller is thinner
        tiltRef.current.style.transform = `translate3d(0, ${p.hop.toFixed(1)}px, 0) rotate(${p.tilt.toFixed(2)}deg) scale(${sx2.toFixed(4)}, ${sy2.toFixed(4)})`;
        tiltRef.current.style.opacity = p.fade < 1 ? p.fade.toFixed(3) : '';
      }
      if (bubbleRef.current) {
        const w = BOT_W * p.s;
        const bw = bubbleRef.current.offsetWidth || 260;
        const bh = bubbleRef.current.offsetHeight || 80;
        // Centred above the mascot's head, so it never lands on the copy beside it.
        const bx = Math.max(12, Math.min(vw - bw - 12, x + w / 2 - bw / 2));
        const by = Math.max(76, y + (BOT_H * 0.05 + Math.min(0, p.hop)) * p.s - bh);
        bubbleRef.current.style.transform = `translate3d(${bx.toFixed(1)}px, ${by.toFixed(1)}px, 0)`;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    const onPointer = (event) => {
      if (event.pointerType !== 'mouse') return;
      const p = pos.current;
      const cx = p.px + BOT_W * p.s * 0.5;
      const cy = p.py - window.scrollY + BOT_H * p.s * 0.45;
      mouse.current.x = Math.max(-1, Math.min(1, (event.clientX - cx) / Math.max(window.innerWidth * 0.45, 380)));
      mouse.current.y = -Math.max(-1, Math.min(1, (event.clientY - cy) / Math.max(window.innerHeight * 0.4, 280)));
      mouse.current.at = performance.now();
    };
    window.addEventListener('pointermove', onPointer, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('pointermove', onPointer);
    };
  }, [enterSection, say]);

  const handleHover = useCallback(() => {
    const now = performance.now();
    if (hold.current || pending.current || now - lastHover.current < HOVER_COOLDOWN_MS) return;
    lastHover.current = now;
    perform(['LEFT_HAND_WAVE'], 'HAPPY');
  }, [perform]);

  // Once per controller: a re-render (a new speech bubble, a tap) must not replay the
  // section's gesture over whatever the mascot is doing.
  const handleControllerReady = useCallback((ctrl) => {
    if (controllerRef.current === ctrl) return;
    controllerRef.current = ctrl;
    if (hold.current) ctrl.setState(hold.current.state || 'TALKING');
    else if (!pending.current) enterSection(active.current);
  }, [controllerRef, enterSection]);

  /** A few dots spray out where the mascot was tapped. */
  const burst = useCallback((x, y) => {
    const id = performance.now();
    setBursts((list) => [...list.slice(-2), { id, x, y }]);
    window.setTimeout(() => setBursts((list) => list.filter((item) => item.id !== id)), 700);
  }, []);

  const pressDown = () => { pos.current.press = true; };
  const pressUp = () => { pos.current.press = false; };

  const handleClick = (event) => {
    const p = pos.current;
    const now = performance.now();
    p.press = false;
    p.sqV += 2.2; // released: boing
    taps.current = [...taps.current.filter((at) => now - at < COMBO_MS), now];

    let reaction;
    if (taps.current.length >= 3) {
      taps.current = [];
      reaction = TAP_COMBO;
    } else if (event.detail > 0) {
      // A pointer tap: where it landed on the body decides the reaction.
      const rect = event.currentTarget.getBoundingClientRect();
      const rx = (event.clientX - rect.left) / rect.width;
      const ry = (event.clientY - rect.top) / rect.height;
      if (ry < 0.3) reaction = TAP_HEAD;
      else if (ry > 0.74) reaction = TAP_FEET;
      else if (rx < 0.3) reaction = TAP_LEFT;
      else if (rx > 0.7) reaction = TAP_RIGHT;
    }
    if (event.detail > 0) burst(event.clientX, event.clientY);
    if (!reaction) {
      const line = CLICK_LINES[clickIndex.current % CLICK_LINES.length];
      clickIndex.current += 1;
      reaction = { moves: line.moves, mood: 'HAPPY', say: line.say };
    }
    if (reaction.jump && p.hop === 0) p.hopV = -reaction.jump;
    if (botRef.current) botRef.current.dataset.botTap = reaction.say;
    perform(reaction.moves, reaction.mood);
    say(reaction.say, 'Dialtact', 5000);
  };

  return (
    <>
      <div
        ref={botRef}
        className="mk-bot"
        style={{ opacity: hidden ? 0 : 1, transition: 'opacity .3s' }}
        data-testid="scroll-bot"
        data-docked={isDocked ? 'true' : 'false'}
      >
        <div ref={tiltRef} className="mk-bot-tilt">
          <button
            type="button"
            className="mk-bot-hit"
            aria-label="Play with the Dialtact mascot"
            onClick={handleClick}
            onPointerEnter={handleHover}
            onPointerDown={pressDown}
            onPointerUp={pressUp}
            onPointerLeave={pressUp}
            onPointerCancel={pressUp}
          />
          <div className="mk-bot-canvas">
            {mountScene ? (
              <LazyDialtactScene
                state="IDLE"
                tone="dark"
                ambient={false}
                pointerRef={pointerRef}
                audioAnalyser={voiceAgent.getAnalyser()}
                renderFallback={renderHolo}
                ignoreDataSaver
                variant="mono"
                centered
                onControllerReady={handleControllerReady}
              />
            ) : (
              <HoloFallback loading />
            )}
          </div>
        </div>
      </div>
      {bursts.map((item) => (
        <div key={item.id} className="mk-bot-burst" style={{ transform: `translate3d(${item.x}px, ${item.y}px, 0)` }} aria-hidden="true">
          {Array.from({ length: 9 }, (_, i) => <i key={i} style={{ '--a': `${i * 40 + 10}deg` }} />)}
        </div>
      ))}
      <div ref={bubbleRef} style={{ position: 'fixed', left: 0, top: 0, zIndex: 41, pointerEvents: 'none' }} aria-live="polite">
        <AnimatePresence mode="wait">
          {bubble && !hidden && (
            <motion.div
              key={bubble.key}
              className="mk-bot-bubble"
              style={{ position: 'relative' }}
              initial={{ opacity: 0, y: 8, scale: 0.94 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -4, scale: 0.98 }}
              transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            >
              <b><i />{bubble.title}</b>
              {bubble.text}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </>
  );
}
