import React, { useEffect, useRef, useMemo } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import { MathUtils } from 'three';
import * as SkeletonUtils from 'three/examples/jsm/utils/SkeletonUtils.js';
import { createVoxlyController } from './BotController';

const GLB_URL = '/models/VoxlyBot_AIEmployee_Interactive.glb';

export function VoxlyBot({
  state = 'IDLE',
  expression = null,
  onBotClick,
  onControllerReady,
  onExpressionChange,
  pointerRef = null,
  pointer = null,
  audioAnalyser = null,
  audioAmplitude = 0,
}) {
  const gltf = useGLTF(GLB_URL);
  const { size } = useThree();
  const groupRef = useRef();
  const bodyYawRef = useRef(0);
  const bodyPitchRef = useRef(0);

  // Clone scene with skeletons preserved
  const clonedScene = useMemo(() => {
    return {
      scene: SkeletonUtils.clone(gltf.scene),
      animations: gltf.animations,
    };
  }, [gltf.scene, gltf.animations]);

  // Persistent controller instance: use ref so controller is never torn down or re-instantiated
  const onExpressionChangeRef = useRef(onExpressionChange);
  useEffect(() => {
    onExpressionChangeRef.current = onExpressionChange;
  }, [onExpressionChange]);

  const controller = useMemo(() => {
    return createVoxlyController(clonedScene, {
      onExpressionChange: (expr) => {
        if (onExpressionChangeRef.current) {
          onExpressionChangeRef.current(expr);
        }
      },
    });
  }, [clonedScene]);

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
    if (controller && audioAnalyser) {
      controller.attachAnalyser(audioAnalyser);
    }
  }, [controller, audioAnalyser]);

  // Sync direct audio amplitude
  useEffect(() => {
    if (controller && audioAmplitude !== undefined) {
      controller.setAudioAmplitude(audioAmplitude);
    }
  }, [controller, audioAmplitude]);

  // Frame update: body follows mouse cursor at 60/120fps with zero-rerender ref tracking
  useFrame(({ clock, pointer: r3fPointer }, delta) => {
    const time = clock.getElapsedTime();

    // Zero-rerender cursor tracking:
    // Priority: pointerRef (window-level smooth tracking) -> pointer prop -> R3F Canvas pointer
    const pX = pointerRef?.current?.x !== undefined 
      ? pointerRef.current.x 
      : (pointer?.x !== undefined ? pointer.x : r3fPointer.x);
    const pY = pointerRef?.current?.y !== undefined 
      ? pointerRef.current.y 
      : (pointer?.y !== undefined ? pointer.y : r3fPointer.y);

    // Responsive horizontal offset & vertical clearance:
    // Desktop: Shift robot slightly to left (-0.22) so top-right dialogue box has clean gap without touching.
    // Mobile: Center robot, scale down slightly (0.38), and lower position so dialogue box sits cleanly in top-right without overlap.
    const isDesktop = size.width >= 960;
    const isTablet = size.width >= 640 && size.width < 960;
    const targetX = isDesktop ? -0.22 : isTablet ? -0.15 : 0;
    const basePosY = size.width < 640 ? -1.02 : -0.95;
    const baseScale = size.width < 480 ? 0.38 : size.width < 640 ? 0.40 : 0.42;

    // Snappy, silky-smooth dampening reduced by 20% for natural, precise mouse tracking
    const targetBodyYaw = MathUtils.clamp(pX, -1, 1) * MathUtils.degToRad(40);
    const targetBodyPitch = MathUtils.clamp(-pY, -1, 1) * MathUtils.degToRad(11.2);

    bodyYawRef.current = MathUtils.damp(bodyYawRef.current, targetBodyYaw, 14, delta);
    bodyPitchRef.current = MathUtils.damp(bodyPitchRef.current, targetBodyPitch, 14, delta);

    const rollProg = controller?.rollProgress || 0;
    const isDoubleRoll = (controller?.currentRollDuration || 1.6) > 2;
    const totalSpins = isDoubleRoll ? 2 : 1;
    // True smooth acrobatic spin roll (continuous ease)
    const rollEase = rollProg > 0 ? (1 - Math.cos(rollProg * Math.PI)) * 0.5 : 0;
    const rollAngle = rollEase * Math.PI * 2 * totalSpins;
    const rollHop = Math.sin(rollProg * Math.PI) * (isDoubleRoll ? 0.40 : 0.32);
    const rollTilt = Math.sin(rollProg * Math.PI * 2 * totalSpins) * 0.22;

    if (groupRef.current) {
      // Smoothly interpolate X offset and apply responsive scale
      groupRef.current.position.x = MathUtils.damp(groupRef.current.position.x, targetX, 10, delta);
      // Floating hover motion with celebratory roll hop
      groupRef.current.position.y = basePosY + Math.sin(time * 2.4) * 0.06 + rollHop;
      groupRef.current.scale.setScalar(baseScale);
      // Body rotation following cursor + lively jiggle + 360 roll (dampened by 20%)
      groupRef.current.rotation.y = bodyYawRef.current + Math.sin(time * 1.5) * 0.02 + rollAngle;
      groupRef.current.rotation.x = bodyPitchRef.current;
      groupRef.current.rotation.z = Math.sin(time * 3.0) * 0.012 - MathUtils.clamp(pX, -1, 1) * MathUtils.degToRad(2.4) + rollTilt;
    }

    if (controller) {
      controller.setPointer(pX, pY);
      controller.update(delta);
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
        if (onBotClick) onBotClick();
      }}
      onPointerOver={() => {
        document.body.style.cursor = 'pointer';
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
