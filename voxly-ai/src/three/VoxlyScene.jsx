import React, { Suspense, useState, useEffect, useRef, useCallback } from 'react';
import { Canvas } from '@react-three/fiber';
import { VoxlyBot } from './VoxlyBot';
import { BotLights } from './BotLights';
import { AmbientElements } from './AmbientElements';
export { clearBotModelCache } from './VoxlyBot';

function CanvasLoader() {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#FAF9FD]/70 backdrop-blur-sm z-10 transition-opacity duration-500">
      <div className="relative flex items-center justify-center">
        <div className="w-12 h-12 rounded-full border-2 border-[#E4E2EB] border-t-[#6344E7] animate-spin" />
        <div className="absolute w-6 h-6 rounded-full bg-[#6344E7]/20 animate-pulse" />
      </div>
      <p className="mt-3 text-xs font-semibold text-[#524E5E] tracking-wide animate-pulse">
        Preparing your AI employee...
      </p>
    </div>
  );
}

export function VoxlyScene({
  state = 'IDLE',
  expression = null,
  onBotClick,
  onControllerReady,
  onExpressionChange,
  audioAnalyser = null,
  audioAmplitude = 0,
  pointerRef = null,
  externalPointer = null,
  className = '',
  isInView = true,
}) {
  const internalPointer = useRef({ x: 0, y: 0 });
  const containerRef = useRef(null);
  const rendererRef = useRef(null);
  const [hasWebGLError, setHasWebGLError] = useState(false);
  const [rendererKey, setRendererKey] = useState(0);
  const [sceneVisible, setSceneVisible] = useState(true);
  const [trackPointer, setTrackPointer] = useState(() =>
    window.matchMedia('(hover: hover) and (pointer: fine)').matches &&
    !window.matchMedia('(any-pointer: coarse)').matches);
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768);
  const [isPageVisible, setIsPageVisible] = useState(() => !document.hidden);
  const contextCleanup = useRef(null);

  useEffect(() => {
    const onVisibility = () => {
      setIsPageVisible(!document.hidden);
      if (!document.hidden) rendererRef.current?.invalidate();
    };
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('pageshow', onVisibility);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('pageshow', onVisibility);
      contextCleanup.current?.();
    };
  }, []);

  useEffect(() => {
    const query = window.matchMedia('(hover: hover) and (pointer: fine)');
    const coarse = window.matchMedia('(any-pointer: coarse)');
    const sync = () => setTrackPointer(query.matches && !coarse.matches);
    sync();
    query.addEventListener('change', sync);
    coarse.addEventListener('change', sync);
    return () => {
      query.removeEventListener('change', sync);
      coarse.removeEventListener('change', sync);
    };
  }, []);

  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => setSceneVisible(entry.isIntersecting));
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  const handleCreated = useCallback(({ gl, invalidate }) => {
    rendererRef.current = { gl, invalidate };
    gl.setClearColor(0x000000, 0);
    const onContextLost = (event) => {
      event.preventDefault();
      setHasWebGLError(true);
    };
    const onContextRestored = () => {
      setHasWebGLError(false);
      invalidate();
    };
    contextCleanup.current?.();
    gl.domElement.addEventListener('webglcontextlost', onContextLost);
    gl.domElement.addEventListener('webglcontextrestored', onContextRestored);
    contextCleanup.current = () => {
      gl.domElement.removeEventListener('webglcontextlost', onContextLost);
      gl.domElement.removeEventListener('webglcontextrestored', onContextRestored);
    };
  }, []);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const handlePointerMove = (e) => {
    if (!trackPointer || e.pointerType !== 'mouse' || pointerRef || externalPointer) return;
    const rect = e.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    const y = -(((e.clientY - rect.top) / rect.height) * 2 - 1);
    internalPointer.current = {
      x: Number.isFinite(x) ? Math.max(-1, Math.min(1, x)) : 0,
      y: Number.isFinite(y) ? Math.max(-1, Math.min(1, y)) : 0,
    };
  };

  const handlePointerLeave = () => {
    if (pointerRef || externalPointer) return;
    internalPointer.current = { x: 0, y: 0 };
  };

  const active = isInView !== false && sceneVisible && isPageVisible && !hasWebGLError;
  const lightweight = isMobile || !trackPointer;
  return (
    <div ref={containerRef} data-mascot-state={hasWebGLError ? 'recovering' : active ? 'active' : 'paused'}
      className={`relative w-full h-full select-none ${className}`}
      onPointerMove={handlePointerMove} onPointerLeave={handlePointerLeave}>
      {hasWebGLError && (
      <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-[#FAF9FD] rounded-3xl">
        <button type="button" onClick={onBotClick} disabled={!onBotClick} aria-label="Interact with Dialtact" className="border-0 bg-transparent p-0 disabled:cursor-default">
        <img
          src="/images/Dialtact_call_assistant_fallback.png"
          alt="Dialtact AI call assistant"
          width="320"
          height="320"
          loading="eager"
          decoding="async"
          className="max-h-[240px] sm:max-h-[320px] object-contain drop-shadow-xl"
        />
        </button>
        <p role="status" className="text-xs text-[#524E5E]">Restoring 3D animation…</p>
        <button type="button" className="mt-2 text-sm underline" onClick={(event) => {
          event.stopPropagation();
          contextCleanup.current?.();
          setHasWebGLError(false);
          setRendererKey(key => key + 1);
        }}>Retry 3D</button>
      </div>
      )}
      <Suspense fallback={<CanvasLoader />}>
        <Canvas
          key={rendererKey}
          frameloop={active ? 'always' : 'never'}
          camera={{
            position: isMobile ? [0, 0.2, 5.2] : [0, 0.35, 4.6],
            fov: isMobile ? 40 : 36,
            near: 0.1,
            far: 100,
          }}
          dpr={lightweight ? 1 : [1, 1.5]}
          gl={{
            // The model already renders at DPR 1 on touch/low-pointer devices;
            // disabling multisample AA there avoids extra GPU memory and fill cost.
            antialias: !lightweight,
            alpha: true,
            powerPreference: 'default',
            failIfMajorPerformanceCaveat: false,
          }}
          onCreated={handleCreated}
          onError={() => setHasWebGLError(true)}
        >
          <BotLights />
          {!lightweight && <AmbientElements />}
          <VoxlyBot
            state={state}
            expression={expression}
            onBotClick={onBotClick}
            onControllerReady={onControllerReady}
            onExpressionChange={onExpressionChange}
            pointerRef={pointerRef || (externalPointer ? null : internalPointer)}
            pointer={externalPointer}
            audioAnalyser={audioAnalyser}
            audioAmplitude={audioAmplitude}
            trackPointer={trackPointer}
          />
        </Canvas>
      </Suspense>
    </div>
  );
}
