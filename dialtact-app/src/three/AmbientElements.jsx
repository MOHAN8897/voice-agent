import React, { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Float } from '@react-three/drei';

export function AmbientElements() {
  const sphere1 = useRef();
  const sphere2 = useRef();
  const sphere3 = useRef();
  const aura = useRef();
  const orbit = useRef();
  const orbitInner = useRef();

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    if (sphere1.current) {
      sphere1.current.position.y = 1.35 + Math.sin(t * 1.2) * 0.12;
      sphere1.current.position.x = -1.95 + Math.cos(t * 0.9) * 0.06;
    }
    if (sphere2.current) {
      sphere2.current.position.y = -0.3 + Math.sin(t * 1.5 + 1.5) * 0.08;
      sphere2.current.position.x = -2.1 + Math.cos(t * 1.1 + 0.8) * 0.05;
    }
    if (sphere3.current) {
      sphere3.current.position.y = 0.9 + Math.sin(t * 1.3 + 3.0) * 0.09;
      sphere3.current.position.x = 2.1 + Math.cos(t * 0.8 + 2.0) * 0.07;
    }
    if (aura.current) {
      aura.current.material.opacity = 0.10 + Math.sin(t * 2.1) * 0.025;
      aura.current.scale.setScalar(1 + Math.sin(t * 1.4) * 0.045);
    }
    if (orbit.current) {
      orbit.current.rotation.z = t * 0.28;
      orbit.current.material.opacity = 0.30 + Math.sin(t * 2.4) * 0.08;
    }
    if (orbitInner.current) {
      orbitInner.current.rotation.z = -t * 0.42;
      orbitInner.current.material.opacity = 0.20 + Math.sin(t * 2.4 + 1) * 0.07;
    }
  });

  return (
    <group position={[0, 0, 0]}>
      {/* Soft aura and orbiting signal rings: these remain deliberately subtle so
          they read as premium glow even on displays without post-processing bloom. */}
      <mesh ref={aura} position={[0, 0.1, -0.7]}>
        <circleGeometry args={[1.75, 64]} />
        <meshBasicMaterial color="#8D6BFF" transparent opacity={0.12} depthWrite={false} />
      </mesh>
      <mesh ref={orbit} position={[0, -1.42, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.32, 0.018, 10, 72]} />
        <meshBasicMaterial color="#A88BFF" transparent opacity={0.32} depthWrite={false} />
      </mesh>
      <mesh ref={orbitInner} position={[0, -1.4, 0.03]} rotation={[-Math.PI / 2, 0, 0.65]}>
        <torusGeometry args={[0.92, 0.012, 10, 56]} />
        <meshBasicMaterial color="#D6C9FF" transparent opacity={0.24} depthWrite={false} />
      </mesh>

      {/* Glossy lavender floating orb 1 (top-left) */}
      <mesh ref={sphere1} position={[-1.95, 1.35, 0.2]}>
        <sphereGeometry args={[0.22, 32, 32]} />
        <meshStandardMaterial
          color="#D4C0FF"
          roughness={0.2}
          metalness={0.15}
          emissive="#6344E7"
          emissiveIntensity={0.25}
        />
      </mesh>

      {/* Glossy lavender floating orb 2 (lower-left) */}
      <mesh ref={sphere2} position={[-2.1, -0.3, 0.4]}>
        <sphereGeometry args={[0.15, 32, 32]} />
        <meshStandardMaterial
          color="#D4C0FF"
          roughness={0.25}
          metalness={0.15}
          emissive="#8369F5"
          emissiveIntensity={0.3}
        />
      </mesh>

      {/* Floating subtle soundwave accent or small orb 3 (right side) */}
      <mesh ref={sphere3} position={[2.1, 0.9, -0.2]}>
        <sphereGeometry args={[0.12, 32, 32]} />
        <meshStandardMaterial
          color="#E8DEFF"
          roughness={0.2}
          metalness={0.1}
          emissive="#6344E7"
          emissiveIntensity={0.2}
        />
      </mesh>

      {/* Soft floor shadow receiver */}
      <mesh position={[0, -2.2, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[12, 12]} />
        <shadowMaterial opacity={0.12} />
      </mesh>
    </group>
  );
}
