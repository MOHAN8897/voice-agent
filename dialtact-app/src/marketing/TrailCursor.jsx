import React, { useEffect, useRef } from 'react';

/** How long a point of the trail stays visible, in ms. */
const LIFE_MS = 520;
/** Points closer together than this (CSS px) are merged, so a slow drag stays light. */
const MIN_STEP = 3;
/** The pixel ratio is capped: a soft glow gains nothing from a 3x canvas on a phone. */
const MAX_DPR = 1.5;

/**
 * The home page's cursor glow drawn in 2D: a faint white trail that fades behind the
 * pointer. It needs no WebGL, so it runs on every device the WebGL GlowCursor cannot:
 * the ones that play the recorded mascot, laptops without good graphics and, on touch
 * screens, under the finger while it moves. It draws only while the trail is visible
 * and stops between movements, so an idle page costs nothing.
 */
export function TrailCursor({ className = '' }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return undefined;
    const points = [];
    let raf = 0;
    let dpr = 1;

    const resize = () => {
      dpr = Math.min(MAX_DPR, window.devicePixelRatio || 1);
      canvas.width = Math.round(window.innerWidth * dpr);
      canvas.height = Math.round(window.innerHeight * dpr);
    };

    const draw = () => {
      raf = 0;
      const now = performance.now();
      while (points.length && now - points[0].t > LIFE_MS) points.shift();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (!points.length) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.globalCompositeOperation = 'lighter';
      // A wide faint pass for the glow, then a thin brighter core, both fading with age.
      for (const [width, strength] of [[14, 0.05], [3, 0.16]]) {
        for (let i = 1; i < points.length; i += 1) {
          const a = points[i - 1];
          const b = points[i];
          if (b.gap) continue;
          const fresh = 1 - (now - b.t) / LIFE_MS;
          ctx.strokeStyle = `rgba(255,255,255,${(strength * fresh).toFixed(3)})`;
          ctx.lineWidth = width * (0.35 + 0.65 * fresh);
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
      // The head: a small soft dot where the pointer is now.
      const head = points[points.length - 1];
      const fresh = 1 - (now - head.t) / LIFE_MS;
      const glow = ctx.createRadialGradient(head.x, head.y, 0, head.x, head.y, 18);
      glow.addColorStop(0, `rgba(255,255,255,${(0.18 * fresh).toFixed(3)})`);
      glow.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.fillStyle = glow;
      ctx.fillRect(head.x - 18, head.y - 18, 36, 36);
      ctx.globalCompositeOperation = 'source-over';
      raf = window.requestAnimationFrame(draw);
    };

    const add = (x, y, gap = false) => {
      const last = points[points.length - 1];
      if (!gap && last && Math.hypot(x - last.x, y - last.y) < MIN_STEP) {
        last.t = performance.now();
      } else {
        points.push({ x, y, t: performance.now(), gap });
      }
      if (!raf) raf = window.requestAnimationFrame(draw);
    };

    // A finger lifting and landing elsewhere starts a new stroke instead of a line across.
    let touching = false;
    const onMove = (event) => {
      if (event.pointerType === 'touch' && !touching) return;
      add(event.clientX, event.clientY);
    };
    const onDown = (event) => {
      if (event.pointerType !== 'touch') return;
      touching = true;
      add(event.clientX, event.clientY, true);
    };
    const onUp = () => { touching = false; };
    // A scrolling finger is taken over by the browser (pointercancel); follow it as a touch.
    const onTouchMove = (event) => {
      const touch = event.touches[0];
      if (touch) add(touch.clientX, touch.clientY, !touching);
      touching = true;
    };

    resize();
    window.addEventListener('resize', resize);
    window.addEventListener('pointermove', onMove, { passive: true });
    window.addEventListener('pointerdown', onDown, { passive: true });
    window.addEventListener('pointerup', onUp, { passive: true });
    window.addEventListener('touchmove', onTouchMove, { passive: true });
    window.addEventListener('touchend', onUp, { passive: true });
    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerdown', onDown);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('touchmove', onTouchMove);
      window.removeEventListener('touchend', onUp);
    };
  }, []);

  return <canvas ref={canvasRef} className={className} aria-hidden="true" style={{ width: '100%', height: '100%' }} />;
}

export default TrailCursor;
