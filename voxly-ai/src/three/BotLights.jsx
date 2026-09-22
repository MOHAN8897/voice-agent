import React from 'react';

export function BotLights() {
  return (
    <>
      {/* Soft overall ambient fill */}
      <ambientLight intensity={0.9} color="#FAF9FD" />

      {/* Main key light with subtle warm lavender warmth */}
      <directionalLight
        position={[4, 6, 5]}
        intensity={2.2}
        color="#FFFFFF"
        castShadow={false}
      />

      {/* Soft secondary fill from left */}
      <directionalLight
        position={[-4, 3, 3]}
        intensity={1.2}
        color="#E4DCFF"
      />

      {/* Rim light from behind-top to give beautiful silhouette on the white bot shell */}
      <directionalLight
        position={[0, 5, -5]}
        intensity={2.8}
        color="#C3ACFF"
      />

      {/* Under-glow pointing up towards the pedestal and bot chin */}
      <pointLight
        position={[0, -1.8, 1]}
        intensity={3.2}
        distance={6}
        color="#8369F5"
      />

      {/* Side lavender accent light */}
      <pointLight
        position={[2.5, 0.5, 2]}
        intensity={1.8}
        distance={5}
        color="#6344E7"
      />
    </>
  );
}
