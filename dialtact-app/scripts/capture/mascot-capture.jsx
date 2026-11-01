import React, { Suspense, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { Canvas, useThree } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import { DialtactBot, GLB_URL } from '../../src/three/DialtactBot';
import { BotLights } from '../../src/three/BotLights';

/**
 * The home page's mascot exactly as it renders there (same model, lights, camera, black
 * and white materials, 760x565 canvas), on a transparent background and a clock that
 * only moves when capture-mascot.mjs says so. Exposes:
 *   window.__bot      the controller (setState, setExpression, setAudioAmplitude…)
 *   window.__clips    { clipName: seconds }
 *   window.__step(t)  render the frame at t seconds
 *   window.__frame(t) render the frame at t seconds and return it as a PNG data URL
 */
function Driver() {
  const { advance, gl } = useThree();
  const { animations } = useGLTF(GLB_URL);
  useEffect(() => {
    window.__clips = Object.fromEntries(animations.map((clip) => [clip.name, clip.duration]));
    window.__step = (t) => advance(t);
    window.__frame = (t) => {
      advance(t);
      return gl.domElement.toDataURL('image/png');
    };
  }, [advance, gl, animations]);
  return null;
}

function Capture() {
  return (
    <Canvas
      frameloop="never"
      dpr={1.25}
      camera={{ position: [0, 0.35, 4.6], fov: 36, near: 0.1, far: 100 }}
      gl={{ alpha: true, antialias: true, preserveDrawingBuffer: true }}
      onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}
      style={{ width: 760, height: 565 }}
    >
      <BotLights />
      <Suspense fallback={null}>
        <DialtactBot variant="mono" centered trackPointer={false} onControllerReady={(ctrl) => { window.__bot = ctrl; }} />
        <Driver />
      </Suspense>
    </Canvas>
  );
}

createRoot(document.getElementById('root')).render(<Capture />);
