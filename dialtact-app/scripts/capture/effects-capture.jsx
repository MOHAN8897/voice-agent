import React, { useRef } from 'react';
import { createRoot } from 'react-dom/client';
import LaserFlow from '../../src/components/reactbits/LaserFlow';

/**
 * The sign-in page's Laser Flow with the props SignInPage gives it, on the desktop stage
 * (a 480px card under a layer 1.8x as wide, the card's top 240px down), faded at its
 * edges by the same mask signin.css gives it. The card itself is invisible: on the page
 * it covers that part of the beam.
 */
const FADES = 'linear-gradient(90deg, transparent, #000 30%, #000 88%, transparent), linear-gradient(180deg, transparent, #000 32%)';
const LASER_STAGE = { width: 864, height: 820, card: { left: 192, top: 240, width: 480, height: 580 } };

function Laser() {
  const cardRef = useRef(null);
  const { width, height, card } = LASER_STAGE;
  return (
    <div style={{ position: 'relative', width, height }}>
      <div style={{ position: 'absolute', inset: 0, maskImage: FADES, WebkitMaskImage: FADES, maskComposite: 'intersect', WebkitMaskComposite: 'source-in' }}>
        <LaserFlow surfaceRef={cardRef} color="#ffffff" beamPosition={0.76} intensity={0.65} flare={1} fog={0.08} dust={0.5} streaks={1} mouseInteraction={false} intro={false} />
      </div>
      <div ref={cardRef} style={{ position: 'absolute', ...card, borderRadius: 28, visibility: 'hidden' }} />
    </div>
  );
}

createRoot(document.getElementById('root')).render(<Laser />);
