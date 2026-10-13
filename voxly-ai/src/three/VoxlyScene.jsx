import React, { Suspense, useState, useEffect, useRef, useCallback } from 'react';
import { Canvas } from '@react-three/fiber';
import { VoxlyBot } from './VoxlyBot';
import { BotLights } from './BotLights';
import { AmbientElements } from './AmbientElements';

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
  const [hasWebGLError, setHasWebGLError] = useState(false);
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768);
  const [isPageVisible, setIsPageVisible] = useState(() => !document.hidden);
  const contextCleanup = useRef(null);

  useEffect(() => {
    const onVisibility = () => setIsPageVisible(!document.hidden);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      contextCleanup.current?.();
    };
  }, []);

  const handleCreated = useCallback(({ gl }) => {
    gl.setClearColor(0x000000, 0);
    const onContextLost = (event) => {
      event.preventDefault();
      setHasWebGLError(true);
    };
    contextCleanup.current?.();
    gl.domElement.addEventListener('webglcontextlost', onContextLost);
    contextCleanup.current = () => gl.domElement.removeEventListener('webglcontextlost', onContextLost);
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
    if (pointerRef || externalPointer) return;
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

  if (hasWebGLError) {
    return (
      <div className={`relative flex items-center justify-center p-8 bg-[#FAF9FD] rounded-3xl ${className}`}>
        <button type="button" onClick={onBotClick} disabled={!onBotClick} aria-label="Interact with Dialtact" className="border-0 bg-transparent p-0 disabled:cursor-default">
        <img
          src="/images/VoxlyBot_preview.png"
          alt="Dialtact AI Employee Preview"
          width="320"
          height="320"
          loading="lazy"
          decoding="async"
          className="max-h-[320px] object-contain drop-shadow-xl"
        />
        </button>
      </div>
    );
  }

  return (
    <div
      className={`relative w-full h-full select-none ${className}`}
      onPointerMove={handlePointerMove}
      onPointerLeave={handlePointerLeave}
    >
      <Suspense fallback={<CanvasLoader />}>
        <Canvas
          frameloop={isInView === false || !isPageVisible ? 'never' : 'always'}
          camera={{
            position: isMobile ? [0, 0.2, 5.2] : [0, 0.35, 4.6],
            fov: isMobile ? 40 : 36,
            near: 0.1,
            far: 100,
          }}
          dpr={[1, 1.5]}
          gl={{
            antialias: true,
            alpha: true,
            powerPreference: 'default',
            failIfMajorPerformanceCaveat: false,
          }}
          onCreated={handleCreated}
          onError={() => setHasWebGLError(true)}
        >
          <BotLights />
          <AmbientElements />
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
          />
        </Canvas>
      </Suspense>
    </div>
  );
}
