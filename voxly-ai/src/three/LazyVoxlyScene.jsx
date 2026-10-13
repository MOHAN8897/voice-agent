import React, { Suspense, useEffect, useState, Component } from 'react';

const LazyScene = React.lazy(() =>
  import('./VoxlyScene').then((m) => ({ default: m.VoxlyScene }))
);

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
    console.warn('3D Scene WebGL error, gracefully falling back to preview:', error);
  }

  render() {
    if (this.state.hasError) {
      return <SceneFallback className={this.props.className} onBotClick={this.props.onBotClick} />;
    }
    return this.props.children;
  }
}

/**
 * The fallback is the real rendered preview image, not a spinner, so the hero never
 * collapses or shifts: the container keeps its height either way.
 */
function SceneFallback({ className = '', eager = true, onBotClick }) {
  return (
    <div className={`relative w-full h-full flex items-center justify-center ${className}`}>
      <button type="button" onClick={onBotClick} disabled={!onBotClick} aria-label="Interact with Dialtact" className="border-0 bg-transparent p-0 disabled:cursor-default">
      <img
        src="/images/VoxlyBot_preview.png"
        alt="Dialtact AI voice agent"
        width="320"
        height="320"
        loading={eager ? 'eager' : 'lazy'}
        decoding="async"
        className="max-h-[320px] object-contain drop-shadow-xl"
      />
      </button>
    </div>
  );
}

function deviceCanRender3D() {
  if (typeof window === 'undefined') return false;
  try {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      return false;
    }
  } catch {}
  try {
    const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (conn && conn.saveData) {
      return false;
    }
  } catch {}
  try {
    const canvas = document.createElement('canvas');
    // Three r163+ requires WebGL2. Release this probe before Canvas allocates its renderer.
    const gl = canvas.getContext('webgl2');
    if (!gl) return false;
    gl.getExtension('WEBGL_lose_context')?.loseContext();
    return true;
  } catch {
    return false;
  }
}

export function LazyVoxlyScene(props = {}) {
  const [shouldLoad, setShouldLoad] = useState(false);

  useEffect(() => {
    if (!deviceCanRender3D()) return undefined;
    setShouldLoad(true);

    return undefined;
  }, []);

  if (!shouldLoad) {
    return <SceneFallback className={props.className} onBotClick={props.onBotClick} />;
  }

  return (
    <SceneErrorBoundary className={props.className} onBotClick={props.onBotClick}>
      <Suspense fallback={<SceneFallback className={props.className} onBotClick={props.onBotClick} />}>
        <div className="w-full h-full transition-opacity duration-500 animate-fade-in">
          <LazyScene {...props} />
        </div>
      </Suspense>
    </SceneErrorBoundary>
  );
}

export default LazyVoxlyScene;
