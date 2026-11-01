import React, { useEffect, useRef, useMemo } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import { MathUtils } from 'three';
import * as SkeletonUtils from 'three/examples/jsm/utils/SkeletonUtils.js';
import { createDialtactController } from './BotController';

// v5: the Blender-authored scroll gestures (see BotController SCROLL_GESTURES), with
// geometry quantized for low-end devices (scripts/blender/optimize_model.mjs).
export const GLB_URL = '/models/DialtactBot_AIEmployee_Interactive_v6.glb?rig=6.0';

/**
 * The home page's black-and-white mascot: every coloured light turns white, the shells
 * go neutral, and the base and hover ring are hidden so the bot floats on its own.
 * Materials are cloned so the cached model (and the previous home page) keeps its colours.
 */
function applyMonochrome(scene) {
  const tone = (material) => {
    const name = material.name || '';
    if (/Glow|Accent/i.test(name)) {
      material.color?.set('#ffffff');
      material.emissive?.set('#ffffff');
      if ('emissiveIntensity' in material) material.emissiveIntensity = Math.min(material.emissiveIntensity, 1.4);
    } else if (/Amber/i.test(name)) {
      material.color?.set('#bdbdbd');
      material.emissive?.set('#000000');
    } else if (/White/i.test(name)) {
      material.color?.set('#ececec');
    } else if (/Seam/i.test(name)) {
      material.color?.set('#2b2b2b');
    } else if (/Dark|Screen|Ring/i.test(name)) {
      material.color?.set('#0a0a0a');
    }
  };
  scene.traverse((node) => {
    if (node.name === 'Base' || node.name === 'HoverRing') node.visible = false;
    if (!node.isMesh) return;
    node.material = Array.isArray(node.material)
      ? node.material.map((m) => { const c = m.clone(); tone(c); return c; })
      : (() => { const c = node.material.clone(); tone(c); return c; })();
  });
}
export const clearBotModelCache = () => useGLTF.clear(GLB_URL);

export function DialtactBot({
  state = 'IDLE',
  expression = null,
  onBotClick,
  onControllerReady,
  onExpressionChange,
  pointerRef = null,
  pointer = null,
  audioAnalyser = null,
  audioAmplitude = 0,
  trackPointer = true,
  variant = 'color',
  centered = false,
  onBotHover,
}) {
  const gltf = useGLTF(GLB_URL);
  const { size } = useThree();
  const groupRef = useRef();
  const bodyYawRef = useRef(0);
  const bodyPitchRef = useRef(0);
  const reducedMotionRef = useRef(false);

  // Clone scene with skeletons preserved
  const clonedScene = useMemo(() => {
    const scene = SkeletonUtils.clone(gltf.scene);
    if (variant === 'mono') applyMonochrome(scene);
    return { scene, animations: gltf.animations };
  }, [gltf.scene, gltf.animations, variant]);

  // Persistent controller instance: use ref so controller is never torn down or re-instantiated
  const onExpressionChangeRef = useRef(onExpressionChange);
  useEffect(() => {
    onExpressionChangeRef.current = onExpressionChange;
  }, [onExpressionChange]);

  const controller = useMemo(() => {
    return createDialtactController(clonedScene, {
      onExpressionChange: (expr) => {
        if (onExpressionChangeRef.current) {
          onExpressionChangeRef.current(expr);
        }
      },
    });
  }, [clonedScene]);

  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const sync = () => {
      reducedMotionRef.current = preference.matches;
      controller.setReducedMotion(preference.matches);
    };
    sync();
    preference.addEventListener('change', sync);
    return () => preference.removeEventListener('change', sync);
  }, [controller]);

  // Sync state & controller ready callback
  useEffect(() => {
    if (controller && onControllerReady) {
      onControllerReady(controller);
    }
  }, [controller, onControllerReady]);

  // Sync external state changes
  useEffect(() => {
    if (controller && state) {
      controller.setState(state);
    }
  }, [controller, state]);

  // Sync external expression changes
  useEffect(() => {
    if (controller && expression) {
      controller.setExpression(expression);
    }
  }, [controller, expression]);

  // Sync audio analyser for real-time lip-sync mouth movement
  useEffect(() => {
    if (controller) {
      controller.attachAnalyser(audioAnalyser);
    }
  }, [controller, audioAnalyser]);

  // Sync direct audio amplitude
  useEffect(() => {
    if (controller && audioAmplitude !== undefined) {
      controller.setAudioAmplitude(audioAmplitude);
    }
  }, [controller, audioAmplitude]);

  // Frame update: body follows pointer (mouse or finger) at display refresh rate
  useFrame(({ clock, pointer: r3fPointer }, delta) => {
    const time = clock.getElapsedTime();
    const safeDelta = MathUtils.clamp(Number.isFinite(delta) ? delta : 0, 0, 0.1);

    // Decorative float/jiggle respects reduced-motion. Look-at still tracks
    // user input so phones with "remove animations" don't look frozen.
    const decor = reducedMotionRef.current ? 0 : 1;
    const lookScale = reducedMotionRef.current ? 0.55 : 1;

    // Priority: pointerRef (window/touch tracking) -> pointer prop -> R3F Canvas pointer
    const rawX = pointerRef?.current?.x !== undefined
      ? pointerRef.current.x
      : (pointer?.x !== undefined ? pointer.x : r3fPointer.x);
    const rawY = pointerRef?.current?.y !== undefined
      ? pointerRef.current.y
      : (pointer?.y !== undefined ? pointer.y : r3fPointer.y);
    const pX = trackPointer && Number.isFinite(rawX) ? rawX : 0;
    const pY = trackPointer && Number.isFinite(rawY) ? rawY : 0;

    // Desktop: Shift robot slightly left so dialogue has gap.
    // Mobile: Center + slightly smaller so the callout fits.
    const isDesktop = size.width >= 960;
    const isTablet = size.width >= 640 && size.width < 960;
    const targetX = centered ? 0 : isDesktop ? -0.22 : isTablet ? -0.15 : 0;
    // Without its base (mono) the bot floats: lift it into the frame and let it fill more.
    const floatLift = variant === 'mono' ? 0.42 : 0;
    const basePosY = (size.width < 640 ? -1.02 : -0.95) + floatLift;
    const baseScale = (size.width < 480 ? 0.38 : size.width < 640 ? 0.40 : 0.42) * (variant === 'mono' ? 0.86 : 1);

    const targetBodyYaw = lookScale * MathUtils.clamp(pX, -1, 1) * MathUtils.degToRad(18);
    const targetBodyPitch = lookScale * MathUtils.clamp(-pY, -1, 1) * MathUtils.degToRad(7);

    bodyYawRef.current = MathUtils.damp(
      Number.isFinite(bodyYawRef.current) ? bodyYawRef.current : 0,
      targetBodyYaw,
      14,
      safeDelta
    );
    bodyPitchRef.current = MathUtils.damp(
      Number.isFinite(bodyPitchRef.current) ? bodyPitchRef.current : 0,
      targetBodyPitch,
      14,
      safeDelta
    );

    const rollProg = controller?.rollProgress || 0;
    const isDoubleRoll = (controller?.currentRollDuration || 1.6) > 2;
    const totalSpins = isDoubleRoll ? 2 : 1;
    const rollEase = rollProg > 0 ? (1 - Math.cos(rollProg * Math.PI)) * 0.5 : 0;
    const rollAngle = rollEase * Math.PI * 2 * totalSpins;
    const rollHop = Math.sin(rollProg * Math.PI) * (isDoubleRoll ? 0.40 : 0.32);
    const rollTilt = Math.sin(rollProg * Math.PI * 2 * totalSpins) * 0.22;

    if (groupRef.current) {
      groupRef.current.position.x = MathUtils.damp(groupRef.current.position.x, targetX, 10, safeDelta);
      groupRef.current.position.y = basePosY + decor * Math.sin(time * 2.4) * 0.06 + rollHop;
      groupRef.current.scale.setScalar(baseScale);
      groupRef.current.rotation.y = (bodyYawRef.current || 0) + decor * Math.sin(time * 1.5) * 0.02 + rollAngle;
      groupRef.current.rotation.x = bodyPitchRef.current || 0;
      groupRef.current.rotation.z =
        decor * (Math.sin(time * 3.0) * 0.012 - MathUtils.clamp(pX, -1, 1) * MathUtils.degToRad(2.4)) +
        rollTilt;
    }

    if (controller) {
      controller.setPointer(pX, pY);
      controller.update(safeDelta);
    }
  });

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (controller) {
        controller.dispose();
      }
    };
  }, [controller]);

  return (
    <group
      ref={groupRef}
      position={[0, -0.95, 0]}
      scale={[0.42, 0.42, 0.42]}
      onClick={(e) => {
        e.stopPropagation();
        if (onBotClick) onBotClick(e);
      }}
      onPointerOver={() => {
        if (trackPointer) document.body.style.cursor = 'pointer';
        onBotHover?.();
      }}
      onPointerOut={() => {
        document.body.style.cursor = 'default';
      }}
    >
      <primitive object={clonedScene.scene} />
    </group>
  );
}

useGLTF.preload(GLB_URL);
