import React, { Suspense, useCallback, useEffect, useMemo, useRef, useState, Component } from 'react';

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
      const SceneFallback = this.props.Fallback;
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
function DefaultSceneFallback({ className = '', eager = true, onBotClick, message, onRetry }) {
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

const CHUNK_RELOAD_KEY = 'dialtact:3d-chunk-reload';

function isChunkLoadError(error) {
  const text = String(error?.message || error || '');
  return /dynamically imported module|Importing a module script failed|error loading dynamically|Outdated Optimize Dep/i.test(text);
}

function device3DStatus({ ignoreDataSaver = false } = {}) {
  if (typeof window === 'undefined') return 'Loading 3D…';
  try {
    const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (conn && conn.saveData && !ignoreDataSaver) {
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

/**
 * `renderFallback` replaces the preview image in every non-3D state (loading, retrying,
 * unavailable). It receives `{ message, onRetry, loading }`; the home page uses it to
 * show a holographic placeholder instead of a flat picture.
 *
 * `ignoreDataSaver` loads the model even when the browser reports data saver, for a
 * page where the 3D mascot is the content rather than decoration.
 */
export function LazyDialtactScene(props = {}) {
  const { renderFallback } = props;
  const SceneFallback = useMemo(() => (renderFallback
    ? ({ message, onRetry }) => renderFallback({ message, onRetry, loading: /Loading|taking longer/.test(message || '') })
    : DefaultSceneFallback), [renderFallback]);
  const [shouldLoad, setShouldLoad] = useState(false);
  const [message, setMessage] = useState('Loading 3D…');
  const [attempt, setAttempt] = useState(0);
  const [modelReady, setModelReady] = useState(false);
  const [loadTimedOut, setLoadTimedOut] = useState(false);
  const LazyScene = useMemo(() => React.lazy(() => import('./DialtactScene').then((m) => {
    if (attempt > 0) m.clearBotModelCache();
    return { default: m.DialtactScene };
  })), [attempt]);
  const retry = () => {
    setModelReady(false);
    setLoadTimedOut(false);
    setAttempt(value => value + 1);
    setShouldLoad(true);
  };
  const handleModelReady = useCallback((controller) => {
    try { sessionStorage.removeItem(CHUNK_RELOAD_KEY); } catch { /* storage blocked */ }
    setModelReady(true);
    setLoadTimedOut(false);
    props.onControllerReady?.(controller);
  }, [props.onControllerReady]);
  // A failed chunk or model request (a dev rebuild, a flaky network) usually succeeds
  // on a second try, so retry twice on its own before showing the Retry button.
  const autoRetries = useRef(0);
  const handleLoadError = useCallback((error) => {
    // A missing code chunk means this tab predates a new build (or a dev-server
    // re-optimisation): retrying asks for the same deleted file. Reload once to pick
    // up the current build; the session flag stops a reload loop.
    if (isChunkLoadError(error) && typeof window !== 'undefined') {
      try {
        if (!sessionStorage.getItem(CHUNK_RELOAD_KEY)) {
          sessionStorage.setItem(CHUNK_RELOAD_KEY, '1');
          window.location.reload();
          return;
        }
      } catch {
        // Storage blocked: fall through to the in-place retries.
      }
    }
    setModelReady(true);
    setLoadTimedOut(false);
    if (autoRetries.current < 2) {
      autoRetries.current += 1;
      window.setTimeout(() => {
        setModelReady(false);
        setAttempt((value) => value + 1);
      }, 1500 * autoRetries.current);
    }
  }, []);

  useEffect(() => {
    if (!shouldLoad || modelReady) return undefined;
    const timeout = window.setTimeout(() => setLoadTimedOut(true), LOAD_RECOVERY_TIMEOUT_MS);
    return () => window.clearTimeout(timeout);
  }, [attempt, modelReady, shouldLoad]);

  useEffect(() => {
    const status = device3DStatus({ ignoreDataSaver: props.ignoreDataSaver === true });
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
      <SceneErrorBoundary key={attempt} Fallback={SceneFallback} className={props.className} onBotClick={props.onBotClick}
        onRetry={retry} onError={handleLoadError}>
        <Suspense fallback={<SceneFallback className={props.className} onBotClick={props.onBotClick} message="Loading 3D…" />}>
          <div className="w-full h-full transition-opacity duration-500 animate-fade-in">
            <LazyScene {...props} onControllerReady={handleModelReady} />
          </div>
        </Suspense>
      </SceneErrorBoundary>
      {loadTimedOut && !modelReady && (
        <div className={`absolute inset-0 z-30 rounded-3xl ${renderFallback ? '' : 'bg-[#FAF9FD]'}`}>
          <SceneFallback className={props.className} onBotClick={props.onBotClick}
            message="3D is taking longer than usual. You can keep waiting or retry."
            onRetry={retry} />
        </div>
      )}
    </div>
  );
}

export default LazyDialtactScene;
