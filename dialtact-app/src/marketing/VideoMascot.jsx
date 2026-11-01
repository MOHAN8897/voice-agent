import React, { useEffect, useRef } from 'react';
import { videoFormat } from '../lib/renderSupport';

const BASE = '/media/mascot';
const NOOP = () => {};

/**
 * The home page's mascot as recorded video: every gesture and mood captured from the real
 * 3D mascot (scripts/capture), for devices that cannot run WebGL well, and as the first
 * thing anyone sees while the 3D one loads.
 *
 * It hands `onReady` a controller shaped like the 3D one, so ScrollBot drives both the
 * same way: `setState('REACH_RIGHT')` plays that gesture once, `setState('LISTENING')`
 * sets the mood it loops in once the gesture is done. The next clip loads in a second
 * layer and fades in over the first only once it has a frame, so a switch never flashes.
 */
export function VideoMascot({ onReady }) {
  const rootRef = useRef(null);
  const layerA = useRef(null);
  const layerB = useRef(null);
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;

  useEffect(() => {
    const root = rootRef.current;
    const videos = [layerA.current, layerB.current];
    const format = videoFormat();
    root.dataset.format = format;
    videos.forEach((video) => { video.muted = true; video.playsInline = true; });

    let alive = true;
    let clips = null;
    let size = [950, 706];
    let front = 0;
    let token = 0;
    let shown = null;
    let mood = 'IDLE';
    let gesture = null;
    let gestureTimer = 0;

    const place = (video, [x, y, w, h]) => {
      video.style.left = `${(x / size[0]) * 100}%`;
      video.style.top = `${(y / size[1]) * 100}%`;
      video.style.width = `${(w / size[0]) * 100}%`;
      video.style.height = `${(h / size[1]) * 100}%`;
    };

    const finishGesture = (mine) => {
      if (!alive || mine !== token) return;
      gesture = null;
      show(mood);
    };

    function show(name, { first = false } = {}) {
      const clip = clips?.[name];
      if (!clip) return;
      const mine = ++token;
      window.clearTimeout(gestureTimer);
      const next = first ? videos[front] : videos[1 - front];
      const current = videos[front];
      next.onended = null;
      next.loop = clip.loop;
      place(next, clip.box);
      if (first) {
        next.poster = `${BASE}/poster.webp`;
        next.style.opacity = '1';
      }
      next.src = `${BASE}/${name}.${format}`;
      next.addEventListener('loadeddata', () => {
        if (!alive || mine !== token) return;
        next.play().catch(NOOP); // blocked autoplay (iOS Low Power Mode) keeps the frame
        next.style.opacity = '1';
        if (next !== current) {
          current.style.opacity = '0';
          front = 1 - front;
          window.setTimeout(() => { if (mine === token) current.pause(); }, 200);
        }
        shown = name;
        root.dataset.clip = name;
      }, { once: true });
      if (!clip.loop) {
        next.onended = () => finishGesture(mine);
        // If playback never starts, do not stay on the gesture's first frame.
        gestureTimer = window.setTimeout(() => finishGesture(mine), (clip.frames / 30) * 1000 + 1500);
      }
    }

    const controller = {
      get state() { return gesture || mood; },
      setState(name) {
        const upper = String(name).toUpperCase();
        const key = upper === 'SPEAKING' ? 'TALKING' : upper;
        const clip = clips?.[key];
        if (!clip) return;
        if (!clip.loop) {
          gesture = key;
          show(key);
          return;
        }
        mood = key;
        if (!gesture && shown !== key) show(key);
      },
      setExpression(name) { controller.setState(name); },
      playGesture(name) { controller.setState(name); },
      setPointer: NOOP,
      setAudioAmplitude: NOOP,
      attachAnalyser: NOOP,
      setReducedMotion: NOOP,
      update: NOOP,
      dispose: NOOP,
    };

    fetch(`${BASE}/manifest.json`)
      .then((response) => response.json())
      .then((manifest) => {
        if (!alive) return;
        clips = manifest.clips;
        size = [manifest.width, manifest.height];
        show('IDLE', { first: true });
        onReadyRef.current?.(controller);
      })
      .catch(NOOP);

    return () => {
      alive = false;
      window.clearTimeout(gestureTimer);
      videos.forEach((video) => { video.pause(); video.removeAttribute('src'); video.load(); });
    };
  }, []);

  return (
    <div ref={rootRef} className="mk-bot-video" aria-hidden="true">
      <video ref={layerA} preload="auto" disablePictureInPicture />
      <video ref={layerB} preload="auto" disablePictureInPicture />
    </div>
  );
}
