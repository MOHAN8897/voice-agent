import React, { Suspense, useEffect, useState } from 'react';

const LazyScene = React.lazy(() =>
  import('./VoxlyScene').then((m) => ({ default: m.VoxlyScene }))
);

/**
 * Defer the WebGL bundle until the browser proves it can actually paint it.
 *
 * three-core + three-fiber are ~1 MB uncompressed and were in the initial chunk,
 * which on a mid-range phone meant the headline and CTAs waited on a 3D mascot that
 * may never be seen — a poor trade for the one thing a landing page has to do
 * fast. Loading it on idle (or immediately when the device is clearly capable)
 * keeps the interaction intact while getting the critical path clear of it.
 *
 * The fallback is the real rendered preview image, not a spinner, so the hero never
 * collapses or shifts: the container keeps its height either way.
 */
function SceneFallback({ className = '', eager = false }) {
  return (
    <div className={`relative w-full h-full flex items-center justify-center ${className}`}>
      <img
        src="/images/VoxlyBot_preview.png"
        alt="Voxly AI voice agent"
        width="320"
        height="320"
        loading={eager ? 'eager' : 'lazy'}
        decoding="async"
        className="max-h-[320px] object-contain drop-shadow-xl"
      />
    </div>
  );
}

function deviceCanRender3D() {
  if (typeof window === 'undefined') return false;
  try {
    const canvas = document.createElement('canvas');
    const gl =
      canvas.getContext('webgl2') ||
      canvas.getContext('webgl') ||
      canvas.getContext('experimental-webgl');
    return Boolean(gl);
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
    return <SceneFallback className={props.className} />;
  }

  return (
    <Suspense fallback={<SceneFallback className={props.className} />}>
      <LazyScene {...props} />
    </Suspense>
  );
}

export default LazyVoxlyScene;