import React, { useEffect } from 'react';
import Lenis from 'lenis';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { MarketingNav } from './MarketingNav';
import { HeroSection, StatementSection } from './HeroSection';
import { HowItWorksSection } from './HowItWorksSection';
import { RealCallSection } from './RealCallSection';
import { CapabilitiesSection } from './CapabilitiesSection';
import { UseCasesSection, WorkspaceSection } from './ProofSections';
import { FaqSection, FinalCtaSection, MarketingFooter, PricingSection } from './ClosingSections';
import { ScrollBot } from './ScrollBot';
import './mascot.css';
import './marketing.css';

gsap.registerPlugin(ScrollTrigger);

/**
 * Smooth scrolling for the home page. Lenis drives the scroll and GSAP's ticker drives
 * Lenis, so ScrollTrigger pins and scrubs read the same position the user sees.
 * Skipped entirely under reduced motion.
 */
function useSmoothScroll() {
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined;
    const root = document.documentElement;
    const hadSmooth = root.classList.contains('scroll-smooth');
    root.classList.remove('scroll-smooth');
    const lenis = new Lenis({ lerp: 0.1, smoothWheel: true, syncTouch: false });
    window.__dialtactLenis = lenis;
    lenis.on('scroll', ScrollTrigger.update);
    const raf = (time) => lenis.raf(time * 1000);
    gsap.ticker.add(raf);
    gsap.ticker.lagSmoothing(0);

    // Arriving on /#pricing etc.: jump there once the layout (and pins) exist.
    const id = window.location.hash.slice(1);
    let timer = 0;
    if (id && !id.startsWith('dashboard')) {
      timer = window.setTimeout(() => {
        const el = document.getElementById(id);
        if (el) lenis.scrollTo(el, { offset: -72, immediate: true });
      }, 350);
    }
    return () => {
      window.clearTimeout(timer);
      gsap.ticker.remove(raf);
      lenis.destroy();
      if (window.__dialtactLenis === lenis) delete window.__dialtactLenis;
      if (hadSmooth) root.classList.add('scroll-smooth');
    };
  }, []);
}

export function MarketingPage({
  onGetStarted,
  onSignIn,
  onEnterConsole,
  onSelectPlan,
  onNavigatePage,
  botControllerRef,
  isModalOpen,
}) {
  useSmoothScroll();

  // The body is light for the rest of the app; match it to this page so overscroll
  // and rubber-banding never flash a pale edge.
  useEffect(() => {
    const previous = document.body.style.backgroundColor;
    document.body.style.backgroundColor = '#050506';
    return () => { document.body.style.backgroundColor = previous; };
  }, []);

  // Fonts and the lazy 3D chunk shift layout after first paint; re-measure triggers.
  useEffect(() => {
    const refresh = () => ScrollTrigger.refresh();
    document.fonts?.ready?.then(refresh);
    window.addEventListener('load', refresh);
    return () => window.removeEventListener('load', refresh);
  }, []);

  return (
    <div className="mk">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:bg-white focus:text-black focus:px-4 focus:py-2 focus:rounded">
        Skip to content
      </a>
      <MarketingNav onNavigatePage={onNavigatePage} onSignIn={onSignIn} onEnterConsole={onEnterConsole} />
      <main id="main">
        <HeroSection onCreateAgent={onGetStarted} />
        <StatementSection />
        <HowItWorksSection />
        <RealCallSection />
        <CapabilitiesSection />
        <UseCasesSection />
        <WorkspaceSection />
        <PricingSection onSelectPlan={onSelectPlan} />
        <FaqSection />
        <FinalCtaSection onGetStarted={onGetStarted} />
      </main>
      <MarketingFooter onNavigatePage={onNavigatePage} />
      <ScrollBot controllerRef={botControllerRef} hidden={isModalOpen} />
    </div>
  );
}

export default MarketingPage;
