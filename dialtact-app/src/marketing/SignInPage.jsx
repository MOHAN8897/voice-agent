import React, { useRef, useState } from 'react';
import { ArrowLeft, AudioLines } from 'lucide-react';
import GhostFibers from '@/components/reactbits/GhostFibers';
import LaserFlow from '@/components/reactbits/LaserFlow';
import { AuthModal } from '../components/AuthModal';
import { renderMode, videoFormat } from '../lib/renderSupport';
import './marketing.css';
import './signin.css';

const NEXT = [
  ['Describe your business', 'Paste your website or upload your FAQs and prices.'],
  ['Pick a voice', 'Hear each one before you choose.'],
  ['Test it, then go live', 'Call it in the browser, then put it on a number.'],
];

/**
 * A recorded effect (scripts/capture), looping, for devices that cannot run the live one.
 * Under reduced motion it drifts at a third of the speed, as the live effects do.
 */
function EffectVideo({ name, className }) {
  const slow = (event) => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) event.currentTarget.playbackRate = 0.35;
  };
  return (
    <video
      className={className}
      src={`/media/effects/${name}.${videoFormat()}`}
      poster={`/media/effects/${name}.webp`}
      autoPlay
      muted
      loop
      playsInline
      disablePictureInPicture
      onLoadedMetadata={slow}
      aria-hidden="true"
    />
  );
}

/**
 * `/signin`: sign in or make an account, and the agent builder opens straight after.
 * One page for both, in the home page's black and white. Ghost Fibers drift behind it,
 * and a Laser Flow beam lands on the form card; both are recorded video where WebGL
 * cannot run them well (lib/renderSupport).
 */
export function SignInPage({ mode = 'signin', notice = '', onAuthSuccess, onBack }) {
  const cardRef = useRef(null);
  const [live] = useState(() => renderMode() === 'live');
  const back = (event) => {
    event.preventDefault();
    onBack?.();
  };

  return (
    <div className="mk signin" data-testid="signin-page">
      <div className="signin-bg" aria-hidden="true">
        {live ? (
          <GhostFibers glowColor="#ffffff" lineColor="#e5e5e5" secondaryColor="#8a8a8a" speed={0.35} threads={64} vignette={0.55} grain={0} brightness={0.85} mouseInteraction={false} />
        ) : (
          <EffectVideo name="fibers" className="signin-bg-video" />
        )}
      </div>

      <header className="mk-container signin-top">
        <a href="/" className="mk-brand" onClick={back}>
          <span className="mk-brand-mark"><AudioLines size={17} aria-hidden="true" /></span>
          Dialtact
        </a>
        <a href="/" className="mk-btn mk-btn-ghost signin-back" onClick={back}>
          <ArrowLeft size={16} aria-hidden="true" /> Back to home
        </a>
      </header>

      <main className="mk-container signin-grid">
        <section className="signin-copy" aria-labelledby="signin-title">
          <h1 id="signin-title">Create your AI voice agent.</h1>
          <p className="mk-lede">Sign in or make an account. Your agent builder opens right after.</p>
          <ol className="signin-next">
            {NEXT.map(([title, body]) => (
              <li key={title}>
                <h2>{title}</h2>
                <p>{body}</p>
              </li>
            ))}
          </ol>
        </section>

        <div className="signin-stage">
          {live ? (
            <div className="signin-laser" aria-hidden="true">
              {/* The beam lands on the card's top-right corner (the stage's layer is 1.8x the
                  card's width, so the card ends at 0.778; LaserFlow pulls 0.76 just
                  inside the rounded corner), softly. */}
              <LaserFlow surfaceRef={cardRef} color="#ffffff" beamPosition={0.76} intensity={0.65} flare={1} fog={0.08} dust={0.5} streaks={1} mouseInteraction={false} />
            </div>
          ) : (
            <EffectVideo name="laser" className="signin-laser-video" />
          )}
          <div ref={cardRef} className="signin-card">
            <AuthModal variant="page" initialMode={mode} notice={notice} onAuthSuccess={onAuthSuccess} />
          </div>
        </div>
      </main>
    </div>
  );
}

export default SignInPage;
