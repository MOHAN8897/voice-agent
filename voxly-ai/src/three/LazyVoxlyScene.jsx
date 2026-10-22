import React, { Suspense, useCallback, useEffect, useMemo, useState, Component } from 'react';

const LOAD_RECOVERY_TIMEOUT_MS = 15_000;

/**
 * Class-based ErrorBoundary to catch any Three.js / WebGL / Suspense exceptions
 * so the page degrades cleanly to the preview image instead of freezing.
 */
class SceneErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error) {
    this.props.onError?.(error);
    console.warn('3D Scene WebGL error, gracefully falling back to preview:', error);
  }

  render() {
    if (this.state.hasError) {
      return <SceneFallback className={this.props.className} onBotClick={this.props.onBotClick}
        message="3D could not load. Please try again." onRetry={this.props.onRetry} />;
    }
    return this.props.children;
  }
}

/**
 * The fallback is the real rendered preview image, not a spinner, so the hero never
 * collapses or shifts: the container keeps its height either way.
 */
function SceneFallback({ className = '', eager = true, onBotClick, message, onRetry }) {
  return (
    <div data-mascot-state="preview" className={`relative w-full h-full flex flex-col items-center justify-center ${className}`}>
      <button type="button" onClick={onBotClick} disabled={!onBotClick} aria-label="Interact with Dialtact" className="border-0 bg-transparent p-0 disabled:cursor-default">
      <img
        src="/images/Dialtact_call_assistant_fallback.png"
        alt="Dialtact AI call assistant"
        width="320"
        height="320"
        loading={eager ? 'eager' : 'lazy'}
        decoding="async"
        className="max-h-[320px] object-contain drop-shadow-xl"
      />
      </button>
      {message && <p role="status" className="absolute bottom-2 text-xs text-[#524E5E] bg-white/90 rounded px-2 py-1">{message}</p>}
      {onRetry && <button type="button" className="absolute bottom-10 text-sm underline bg-white/90 rounded px-2 py-1"
        onClick={(event) => { event.stopPropagation(); onRetry(); }}>Retry 3D</button>}
    </div>
  );
}

function device3DStatus() {
  if (typeof window === 'undefined') return 'Loading 3D…';
  try {
    const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (conn && conn.saveData) {
      return 'Data saver is on. Retry 3D to load the animation.';
    }
  } catch {}
  try {
    // Let React Three Fiber create the one real renderer context. A throwaway
    // WebGL probe can consume a scarce mobile GPU context and its forced release
    // produces the same context-loss signal as a real renderer failure.
    if (typeof WebGL2RenderingContext === 'undefined') {
      return '3D is unavailable in this browser.';
    }
    return '';
  } catch {
    return '3D is unavailable in this browser.';
  }
}

export function LazyVoxlyScene(props = {}) {
  const [shouldLoad, setShouldLoad] = useState(false);
  const [message, setMessage] = useState('Loading 3D…');
  const [attempt, setAttempt] = useState(0);
  const [modelReady, setModelReady] = useState(false);
  const [loadTimedOut, setLoadTimedOut] = useState(false);
  const LazyScene = useMemo(() => React.lazy(() => import('./VoxlyScene').then((m) => {
    if (attempt > 0) m.clearBotModelCache();
    return { default: m.VoxlyScene };
  })), [attempt]);
  const retry = () => {
    setModelReady(false);
    setLoadTimedOut(false);
    setAttempt(value => value + 1);
    setShouldLoad(true);
  };
  const handleModelReady = useCallback((controller) => {
    setModelReady(true);
    setLoadTimedOut(false);
    props.onControllerReady?.(controller);
  }, [props.onControllerReady]);
  const handleLoadError = useCallback(() => {
    setModelReady(true);
    setLoadTimedOut(false);
  }, []);

  useEffect(() => {
    if (!shouldLoad || modelReady) return undefined;
    const timeout = window.setTimeout(() => setLoadTimedOut(true), LOAD_RECOVERY_TIMEOUT_MS);
    return () => window.clearTimeout(timeout);
  }, [attempt, modelReady, shouldLoad]);

  useEffect(() => {
    const status = device3DStatus();
    setMessage(status);
    setShouldLoad(!status);

    return undefined;
  }, []);

  if (!shouldLoad) {
    return <SceneFallback className={props.className} onBotClick={props.onBotClick} message={message}
      onRetry={message.startsWith('Data saver') || message.startsWith('3D is unavailable') ? retry : undefined} />;
  }

  return (
    <div className="relative w-full h-full">
      <SceneErrorBoundary key={attempt} className={props.className} onBotClick={props.onBotClick}
        onRetry={retry} onError={handleLoadError}>
        <Suspense fallback={<SceneFallback className={props.className} onBotClick={props.onBotClick} message="Loading 3D…" />}>
          <div className="w-full h-full transition-opacity duration-500 animate-fade-in">
            <LazyScene {...props} onControllerReady={handleModelReady} />
          </div>
        </Suspense>
      </SceneErrorBoundary>
      {loadTimedOut && !modelReady && (
        <div className="absolute inset-0 z-30 rounded-3xl bg-[#FAF9FD]">
          <SceneFallback className={props.className} onBotClick={props.onBotClick}
            message="3D is taking longer than usual. You can keep waiting or retry."
            onRetry={retry} />
        </div>
      )}
    </div>
  );
}

export default LazyVoxlyScene;
