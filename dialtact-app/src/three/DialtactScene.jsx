import React, { Suspense, useState, useEffect, useRef, useCallback } from 'react';
import { Canvas } from '@react-three/fiber';
import { DialtactBot } from './DialtactBot';
import { BotLights } from './BotLights';
import { AmbientElements } from './AmbientElements';
export { clearBotModelCache } from './DialtactBot';

function CanvasLoader({ tone = 'light' }) {
  const dark = tone === 'dark';
  return (
    <div className={`absolute inset-0 flex flex-col items-center justify-center z-10 transition-opacity duration-500 ${dark ? 'bg-transparent' : 'bg-[#FAF9FD]/70 backdrop-blur-sm'}`}>
      <div className="relative flex items-center justify-center">
        <div className={`w-12 h-12 rounded-full border-2 animate-spin ${dark ? 'border-white/20 border-t-white' : 'border-[#E4E2EB] border-t-[#6344E7]'}`} />
        <div className={`absolute w-6 h-6 rounded-full animate-pulse ${dark ? 'bg-white/20' : 'bg-[#6344E7]/20'}`} />
      </div>
      <p className={`mt-3 text-xs font-semibold tracking-wide animate-pulse ${dark ? 'text-[#8B909A]' : 'text-[#524E5E]'}`}>
        Preparing your AI employee...
      </p>
    </div>
  );
}

export function DialtactScene({
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
  tone = 'light',
  ambient = true,
  variant = 'color',
  centered = false,
  onBotHover,
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
  const autoRebuilds = useRef(0);

  const rebuildRenderer = useCallback(() => {
    contextCleanup.current?.();
    setHasWebGLError(false);
    setRendererKey(key => key + 1);
  }, []);

  // Most context losses are restored by the browser within a moment. If not, build a
  // fresh renderer a few times before leaving it to the Retry button.
  useEffect(() => {
    if (!hasWebGLError || autoRebuilds.current >= 3) return undefined;
    const timer = window.setTimeout(() => {
      autoRebuilds.current += 1;
      rebuildRenderer();
    }, 2500);
    return () => window.clearTimeout(timer);
  }, [hasWebGLError, rebuildRenderer]);

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
      {/* A lost context keeps the canvas mounted: the browser restores the same one
          (its listeners must stay attached for that), and if it does not, the renderer
          is rebuilt automatically. Never swap the scene for a flat picture. */}
      {hasWebGLError && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 p-4 pointer-events-none">
          <p role="status" className={`text-xs font-semibold tracking-wide animate-pulse ${tone === 'dark' ? 'text-white' : 'text-[#6344E7]'}`}>Restoring 3D animation…</p>
          <button type="button" className={`pointer-events-auto text-xs font-semibold px-3 py-1 rounded-lg border transition-all cursor-pointer ${tone === 'dark' ? 'text-black border-white bg-white hover:bg-white/80' : 'text-[#6344E7] border-[#6344E7]/30 bg-white/80 hover:bg-white'}`} onClick={(event) => {
            event.stopPropagation();
            rebuildRenderer();
          }}>Retry 3D</button>
        </div>
      )}
      <Suspense fallback={<CanvasLoader tone={tone} />}>
          <Canvas
          key={rendererKey}
          frameloop={active ? 'always' : 'never'}
          // Measure layout size, not the transformed box: the home page flies this
          // canvas around with a CSS scale, which must not resize the WebGL buffer.
          resize={{ offsetSize: true, scroll: false }}
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
          {!lightweight && ambient && <AmbientElements />}
          <DialtactBot
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
            variant={variant}
            centered={centered}
            onBotHover={onBotHover}
          />
        </Canvas>
      </Suspense>
    </div>
  );
}
