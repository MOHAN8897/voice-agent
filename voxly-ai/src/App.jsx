import React, { useState, useRef, useEffect } from 'react';
import { AuthProvider } from './context/AuthContext';
import { WorkspaceProvider } from './console/context/WorkspaceContext';
import { AppShell } from './console/AppShell';
import { Navbar } from './components/Navbar';
import { Hero } from './components/Hero';
import { AiEmployeeSection } from './components/AiEmployeeSection';
import { TalkToAiSection } from './components/TalkToAiSection';
import { PhoneChannelsSection } from './components/PhoneChannelsSection';
import { LeadEngineSection } from './components/LeadEngineSection';
import { CampaignScaleSection } from './components/CampaignScaleSection';
import { TrainingSection } from './components/TrainingSection';
import { AiTeamSection } from './components/AiTeamSection';
import { ConversationHistorySection } from './components/ConversationHistorySection';
import { AnalyticsSection } from './components/AnalyticsSection';
import { IndustriesSection } from './components/IndustriesSection';
import { HowItWorksSection } from './components/HowItWorksSection';
import { PricingSection } from './components/PricingSection';
import { FAQSection } from './components/FAQSection';
import { FinalCTA } from './components/FinalCTA';
import { Footer } from './components/Footer';
import { WatchDemoModal } from './components/WatchDemoModal';
import { TalkToMeModal } from './components/TalkToMeModal';
import { LegalModals } from './components/LegalModals';
import { AuthModal } from './components/AuthModal';
import { VerifyEmailBanner } from './components/VerifyEmailBanner';
import { ConsoleGate } from './components/ConsoleGate';
import { useAuth } from './context/AuthContext';
import {
  consoleHash,
  consumePostAuthTab,
  DEFAULT_CONSOLE_TAB,
  parseDashboardTabFromHash,
  rememberPostAuthTab,
} from './lib/consoleEntry';

function AppInner() {
  const { isAuthenticated, logout: authLogout } = useAuth();

  const [currentView, setCurrentView] = useState(() => {
    if (typeof window !== 'undefined' && window.location.hash.startsWith('#dashboard')) {
      return 'dashboard';
    }
    return 'landing';
  });

  const [isDemoModalOpen, setIsDemoModalOpen] = useState(false);
  const [isTalkModalOpen, setIsTalkModalOpen] = useState(false);
  const [isLegalModalOpen, setIsLegalModalOpen] = useState(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [authModalMode, setAuthModalMode] = useState('signin');
  const [legalModalTab, setLegalModalTab] = useState('privacy');
  const botControllerRef = useRef(null);

  useEffect(() => {
    if (window.location.hash.includes('reset-password')) {
      setAuthModalMode('reset');
      setIsAuthModalOpen(true);
    }
    const params = new URLSearchParams(window.location.search);
    const authErr = params.get('auth_error');
    if (authErr) {
      setAuthModalMode('signin');
      setIsAuthModalOpen(true);
      const msg =
        authErr === 'google_state'
          ? 'Google sign-in expired. Please try again.'
          : 'Google sign-in failed. Check API GOOGLE_OAUTH_* settings and redirect URI.';
      window.setTimeout(() => {
        window.history.replaceState({}, '', window.location.pathname + window.location.hash);
      }, 0);
      window.dispatchEvent(new CustomEvent('voxly:auth-error', { detail: { code: authErr, message: msg } }));
    }
  }, []);

  useEffect(() => {
    const handleHashChange = () => {
      if (window.location.hash.includes('reset-password')) {
        setAuthModalMode('reset');
        setIsAuthModalOpen(true);
        return;
      }
      if (window.location.hash.startsWith('#dashboard')) {
        setCurrentView('dashboard');
      } else if (!window.location.hash || window.location.hash === '#' || !window.location.hash.includes('dashboard')) {
        setCurrentView('landing');
      }
    };
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const openAuthModal = (mode = 'signin', postAuthTab = DEFAULT_CONSOLE_TAB) => {
    rememberPostAuthTab(postAuthTab);
    setAuthModalMode(mode);
    setIsAuthModalOpen(true);
  };

  /** Sign-in and "Build your agent" use the same path: console after auth. */
  const enterConsole = (tab = DEFAULT_CONSOLE_TAB) => {
    const targetTab = tab || DEFAULT_CONSOLE_TAB;
    setCurrentView('dashboard');
    window.location.hash = consoleHash(targetTab);
    if (!isAuthenticated) {
      openAuthModal('signin', targetTab);
    }
  };

  const handleGetStarted = () => enterConsole(DEFAULT_CONSOLE_TAB);

  const goToLanding = () => {
    setCurrentView('landing');
    window.location.hash = '';
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleSignOut = async () => {
    await authLogout();
    goToLanding();
  };

  const handleSelectPlan = () => enterConsole('billing');

  const handleOpenLegal = (tab = 'privacy') => {
    setLegalModalTab(tab);
    setIsLegalModalOpen(true);
  };

  useEffect(() => {
    const isConsole = currentView === 'dashboard';
    let tag = document.querySelector('meta[name="robots"][data-voxly-console]');
    if (isConsole) {
      if (!tag) {
        tag = document.createElement('meta');
        tag.setAttribute('name', 'robots');
        tag.setAttribute('data-voxly-console', '1');
        tag.setAttribute('content', 'noindex, nofollow');
        document.head.appendChild(tag);
      }
    } else if (tag) {
      tag.remove();
    }
  }, [currentView]);

  useEffect(() => {
    const hash = window.location.hash || '';
    if (hash === '#signin' || hash.startsWith('#signin?')) {
      setCurrentView('landing');
      openAuthModal('signin', parseDashboardTabFromHash('#dashboard/employees'));
      window.location.hash = '';
    }
  }, []);

  return (
    <>
        {currentView === 'dashboard' ? (
          <ConsoleGate
            onSignIn={() => openAuthModal('signin', parseDashboardTabFromHash(window.location.hash))}
            onBackToMarketing={() => {
              setCurrentView('landing');
              window.location.hash = '';
            }}
          >
            <AppShell onBackToLanding={goToLanding} onSignOut={handleSignOut} />
          </ConsoleGate>
        ) : (
          <div className="min-h-screen flex flex-col bg-[#FAF9FD] selection:bg-[#F0EEF6] selection:text-[#6344E7]">
            {/* Navigation Header */}
            <Navbar
              onEnterConsole={enterConsole}
              onWatchDemo={() => setIsDemoModalOpen(true)}
            />

      {/* Main Content Sections: Streamlined, Intuitive User Architecture */}
      <main className="flex-1">
        {/* 01: Hero — AI Voice Agent & 3D Interactive Mascot */}
        <Hero
          onTalkToMe={() => setIsTalkModalOpen(true)}
          onWatchDemo={() => setIsDemoModalOpen(true)}
          onGetStarted={handleGetStarted}
          botControllerRef={botControllerRef}
          isModalOpen={isDemoModalOpen || isTalkModalOpen}
        />

        {/* 02: Immediate Live Voice Lab & Speech Acoustic Player */}
        <TalkToAiSection
          onOpenTalkModal={() => setIsTalkModalOpen(true)}
        />

        {/* 03: Autonomous AI Workforce Fleet (Sales, Support, Receptionist, Follow-up) */}
        <AiTeamSection
          onGetStarted={handleGetStarted}
        />

        {/* 04: Fast Setup & Production Telephony Onboarding (5 Steps) */}
        <HowItWorksSection
          onGetStarted={handleGetStarted}
        />

        {/* 05: Telephony Channels (Inbound 24/7, Outbound SDR, Virtual DIDs) */}
        <PhoneChannelsSection
          onGetStarted={handleGetStarted}
        />

        {/* 06: Core Capabilities & Visual Agent Builder */}
        <AiEmployeeSection
          onGetStarted={handleGetStarted}
        />

        {/* 07: Autonomous Lead Qualification Engine (BANT Deals & Pipeline) */}
        <LeadEngineSection
          onGetStarted={handleGetStarted}
        />

        {/* 08: Bulk Outbound Campaigns at Scale (Dialing Engine) */}
        <CampaignScaleSection
          onGetStarted={handleGetStarted}
        />

        {/* 09: Train Your AI (Knowledge Base, SOP Documents & AI Brain) */}
        <TrainingSection />

        {/* 10: Call History & Diarized Transcript Inspector */}
        <ConversationHistorySection />

        {/* 11: Operational Intelligence Dashboard (12k+ Calls & Telemetry) */}
        <AnalyticsSection />

        {/* 12: Vertical Industry Playbooks (Healthcare, Finance, Real Estate, SaaS) */}
        <IndustriesSection
          onGetStarted={handleGetStarted}
        />

        {/* 13: Transparent Economics & Fleet Pricing */}
        <PricingSection
          onSelectPlan={handleSelectPlan}
        />

        {/* 14: Frequently Asked Questions */}
        <FAQSection />

        {/* 15: Executive Call to Action */}
        <FinalCTA
          onGetStarted={handleGetStarted}
          onTalkToMe={() => setIsTalkModalOpen(true)}
        />
      </main>

      {/* Footer */}
      <Footer onOpenLegal={handleOpenLegal} />

      {/* Modals */}
      <WatchDemoModal
        isOpen={isDemoModalOpen}
        onClose={() => setIsDemoModalOpen(false)}
        onSelectBotState={(st) => botControllerRef.current?.setState(st)}
      />

      <TalkToMeModal
        isOpen={isTalkModalOpen}
        onClose={() => setIsTalkModalOpen(false)}
        onSelectBotState={(st) => botControllerRef.current?.setState(st)}
      />

      <LegalModals
        isOpen={isLegalModalOpen}
        onClose={() => setIsLegalModalOpen(false)}
        defaultTab={legalModalTab}
      />
      </div>
        )}

        <VerifyEmailBanner
          onSignIn={() => openAuthModal('signin', DEFAULT_CONSOLE_TAB)}
        />

        <AuthModal
          isOpen={isAuthModalOpen}
          onClose={() => setIsAuthModalOpen(false)}
          initialMode={authModalMode}
          onAuthSuccess={() => {
            const tab = consumePostAuthTab();
            setCurrentView('dashboard');
            window.location.hash = consoleHash(tab);
          }}
        />
    </>
  );
}

export function App() {
  return (
    <AuthProvider>
      <WorkspaceProvider>
        <AppInner />
      </WorkspaceProvider>
    </AuthProvider>
  );
}

export default App;
