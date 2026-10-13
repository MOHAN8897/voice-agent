import React, { useState, useRef, useEffect, useCallback } from 'react';
import { AuthProvider } from './context/AuthContext';
import { WorkspaceProvider } from './console/context/WorkspaceContext';
import { Navbar } from './components/Navbar';
import { Hero } from './components/Hero';
import { TalkToAiSection } from './components/TalkToAiSection';
import { HowItWorksSection } from './components/HowItWorksSection';
import { PhoneChannelsSection } from './components/PhoneChannelsSection';
import { AiEmployeeSection } from './components/AiEmployeeSection';
import { CampaignScaleSection } from './components/CampaignScaleSection';
import { TrainingSection } from './components/TrainingSection';
import { AnalyticsSection } from './components/AnalyticsSection';
import { IndustriesSection } from './components/IndustriesSection';
import { PricingSection } from './components/PricingSection';
import { FAQSection } from './components/FAQSection';
import { FinalCTA } from './components/FinalCTA';
import { Footer } from './components/Footer';
import { WatchDemoModal } from './components/WatchDemoModal';
import { TalkToMeModal } from './components/TalkToMeModal';
import { LegalModals } from './components/LegalModals';
import { AuthModal } from './components/AuthModal';
import { startTourGuide, isTourCompleted } from './services/tourGuide';
import { VerifyEmailBanner } from './components/VerifyEmailBanner';
import { useAuth } from './context/AuthContext';
import {
  consoleHash,
  consumePostAuthTab,
  DEFAULT_CONSOLE_TAB,
  parseDashboardTabFromHash,
  rememberPostAuthTab,
} from './lib/consoleEntry';
import { SupportPage } from './pages/SupportPage';
import { CompanyPage } from './pages/CompanyPage';
import { PrivacyPage } from './pages/PrivacyPage';
import { TermsPage } from './pages/TermsPage';
import { SecurityPage } from './pages/SecurityPage';
import { applyPageMetadata } from './lib/siteMetadata';

const ConsoleEntry = React.lazy(() => import('./console/ConsoleEntry'));

function AppInner() {
  const { isAuthenticated, logout: authLogout, signOutReason, user } = useAuth();

  const [currentView, setCurrentView] = useState(() => {
    if (typeof window !== 'undefined') {
      const hash = window.location.hash || '';
      if (hash.startsWith('#dashboard')) return 'dashboard';
      if (hash === '#contact' || hash === '#support') return 'support';
      if (hash === '#company' || hash === '#about') return 'company';
      if (hash === '#privacy') return 'privacy';
      if (hash === '#terms') return 'terms';
      if (hash === '#security') return 'security';
    }
    return 'landing';
  });

  const [isDemoModalOpen, setIsDemoModalOpen] = useState(false);
  const [isTalkModalOpen, setIsTalkModalOpen] = useState(false);
  const [isLegalModalOpen, setIsLegalModalOpen] = useState(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [authModalMode, setAuthModalMode] = useState('signin');
  const [quarantineNotice, setQuarantineNotice] = useState('');
  const [legalModalTab, setLegalModalTab] = useState('privacy');
  const botControllerRef = useRef(null);

  const launchTour = useCallback(
    (isForce = false) => {
      if (!isForce && isTourCompleted(user)) {
        return;
      }
      if (currentView !== 'dashboard') {
        setCurrentView('dashboard');
      }
      window.location.hash = '#dashboard/overview';
      startTourGuide(user, { force: isForce });
    },
    [user, currentView]
  );

  useEffect(() => {
    const handleOpenTour = (e) => {
      const isForce = e?.detail?.force === true;
      launchTour(isForce);
    };
    window.addEventListener('dialtact:open-tour', handleOpenTour);
    window.addEventListener('voxly:open-tour', handleOpenTour);
    return () => {
      window.removeEventListener('dialtact:open-tour', handleOpenTour);
      window.removeEventListener('voxly:open-tour', handleOpenTour);
    };
  }, [launchTour]);

  useEffect(() => {
    if (window.location.hash.includes('reset-password')) {
      setAuthModalMode('reset');
      setIsAuthModalOpen(true);
    }
    const params = new URLSearchParams(window.location.search);
    const notice = params.get('notice');
    if (notice === 'workspace_quarantined') {
      setAuthModalMode('signin');
      setQuarantineNotice(
        'This workspace is scheduled for permanent deletion. Sign in as the owner during the 14-day grace period to restore access or export data.'
      );
      setIsAuthModalOpen(true);
      window.setTimeout(() => {
        window.history.replaceState({}, '', window.location.pathname + window.location.hash);
      }, 0);
    }
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
    const updateTitle = () => {
      const hash = window.location.hash || '';
      if (hash.startsWith('#dashboard')) {
        const tabMatch = hash.match(/#dashboard\/([a-z0-9_-]+)/i);
        applyPageMetadata('dashboard', tabMatch ? tabMatch[1] : '');
      } else if (hash === '#contact' || hash === '#support') applyPageMetadata('support');
      else if (hash === '#company' || hash === '#about') applyPageMetadata('company');
      else if (hash === '#privacy') applyPageMetadata('privacy');
      else if (hash === '#terms') applyPageMetadata('terms');
      else if (hash === '#security') applyPageMetadata('security');
      else applyPageMetadata('landing');
    };

    const handleHashChange = () => {
      if (window.location.hash.includes('reset-password')) {
        setAuthModalMode('reset');
        setIsAuthModalOpen(true);
        return;
      }
      const hash = window.location.hash || '';
      if (hash.startsWith('#dashboard')) {
        setCurrentView('dashboard');
      } else if (hash === '#contact' || hash === '#support') {
        setCurrentView('support');
      } else if (hash === '#company' || hash === '#about') {
        setCurrentView('company');
      } else if (hash === '#privacy') {
        setCurrentView('privacy');
      } else if (hash === '#terms') {
        setCurrentView('terms');
      } else if (hash === '#security') {
        setCurrentView('security');
      } else if (!hash || hash === '#' || !hash.includes('dashboard')) {
        setCurrentView('landing');
      }
      updateTitle();
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

  const handleNavigatePage = (target) => {
    if (!target || target === 'landing' || target === 'home' || target === '#') {
      goToLanding();
      return;
    }
    const cleanTarget = target.startsWith('#') ? target.slice(1) : target;
    if (cleanTarget.startsWith('dashboard')) {
      const tab = cleanTarget.replace('dashboard/', '').replace('dashboard', '');
      enterConsole(tab || DEFAULT_CONSOLE_TAB);
      return;
    }
    if (['contact', 'support', 'company', 'about', 'privacy', 'terms', 'security'].includes(cleanTarget)) {
      const targetView =
        cleanTarget === 'contact' || cleanTarget === 'support'
          ? 'support'
          : cleanTarget === 'about' || cleanTarget === 'company'
          ? 'company'
          : cleanTarget;
      setCurrentView(targetView);
      window.location.hash = `#${cleanTarget}`;
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
    // Landing section anchor (e.g. how-it-works, capabilities, industries, pricing, faq)
    if (currentView !== 'landing') {
      setCurrentView('landing');
    }
    window.location.hash = `#${cleanTarget}`;
    window.setTimeout(() => {
      const elem = document.getElementById(cleanTarget);
      if (elem) {
        elem.scrollIntoView({ behavior: 'smooth' });
      }
    }, 50);
  };

  useEffect(() => {
    const isConsole = currentView === 'dashboard';
    const tabMatch = (window.location.hash || '').match(/#dashboard\/([a-z0-9_-]+)/i);
    applyPageMetadata(currentView, tabMatch ? tabMatch[1] : '');
  }, [currentView]);


  useEffect(() => {
    const hash = window.location.hash || '';
    if (hash === '#signin' || hash.startsWith('#signin?')) {
      setCurrentView('landing');
      openAuthModal('signin', parseDashboardTabFromHash('#dashboard/employees'));
      window.location.hash = '';
    }
  }, []);

  // An idle sign-out happens wherever the person happened to be. Put them back in
  // front of the sign-in form with the reason, instead of leaving them on a console
  // shell that silently stopped working.
  useEffect(() => {
    if (!signOutReason) return;
    setCurrentView('landing');
    setAuthModalMode('signin');
    setIsAuthModalOpen(true);
  }, [signOutReason]);

  return (
    <>
      {currentView === 'dashboard' ? (
        <React.Suspense fallback={<div role="status" className="min-h-screen flex items-center justify-center bg-[#FAF9FD] text-sm text-[#524E5E]">Loading workspace…</div>}>
          <ConsoleEntry
            onSignIn={() => openAuthModal('signin', parseDashboardTabFromHash(window.location.hash))}
            onBackToLanding={() => {
              setCurrentView('landing');
              window.location.hash = '';
            }}
            onSignOut={handleSignOut}
          />
        </React.Suspense>
      ) : currentView === 'support' ? (
        <SupportPage
          onBackToLanding={goToLanding}
          onEnterConsole={enterConsole}
          onNavigatePage={handleNavigatePage}
        />
      ) : currentView === 'company' ? (
        <CompanyPage
          onBackToLanding={goToLanding}
          onEnterConsole={enterConsole}
          onNavigatePage={handleNavigatePage}
        />
      ) : currentView === 'privacy' ? (
        <PrivacyPage
          onBackToLanding={goToLanding}
          onEnterConsole={enterConsole}
          onNavigatePage={handleNavigatePage}
        />
      ) : currentView === 'terms' ? (
        <TermsPage
          onBackToLanding={goToLanding}
          onEnterConsole={enterConsole}
          onNavigatePage={handleNavigatePage}
        />
      ) : currentView === 'security' ? (
        <SecurityPage
          onBackToLanding={goToLanding}
          onEnterConsole={enterConsole}
          onNavigatePage={handleNavigatePage}
        />
      ) : (
        <div className="min-h-screen flex flex-col bg-[#FAF9FD] selection:bg-[#F0EEF6] selection:text-[#6344E7]">
          {/* Navigation Header */}
          <Navbar
            onEnterConsole={enterConsole}
            onWatchDemo={() => setIsDemoModalOpen(true)}
            onNavigatePage={handleNavigatePage}
          />

          {/* Main Content Sections */}
          <main className="flex-1">
            {/* 01: Hero — AI Voice Agent & 3D Interactive Mascot */}
            <Hero
              onTalkToMe={() => setIsTalkModalOpen(true)}
              onWatchDemo={() => setIsDemoModalOpen(true)}
              onGetStarted={handleGetStarted}
              botControllerRef={botControllerRef}
              isModalOpen={isDemoModalOpen || isTalkModalOpen}
            />

            {/* 02: Real voice samples per industry, plus the live-agent entry point */}
            <TalkToAiSection
              onOpenTalkModal={() => setIsTalkModalOpen(true)}
              onGetStarted={handleGetStarted}
            />

            {/* 03: The one onboarding path */}
            <HowItWorksSection onGetStarted={handleGetStarted} />

            {/* 04: Telephony channels — inbound and outbound */}
            <PhoneChannelsSection onGetStarted={handleGetStarted} />

            {/* 05: What the employee does on a call */}
            <AiEmployeeSection onGetStarted={handleGetStarted} />

            {/* 06: Bulk list calling */}
            <CampaignScaleSection onGetStarted={handleGetStarted} />

            {/* 07: Teach it your business */}
            <TrainingSection />

            {/* 08: Reporting — the one sample dashboard, labelled as one */}
            <AnalyticsSection />

            {/* 09: Who it is for */}
            <IndustriesSection onGetStarted={handleGetStarted} />

            {/* 10: Pricing */}
            <PricingSection onSelectPlan={handleSelectPlan} />

            {/* 11: FAQ */}
            <FAQSection />

            {/* 12: Closing call to action */}
            <FinalCTA
              onGetStarted={handleGetStarted}
              onTalkToMe={() => setIsTalkModalOpen(true)}
            />
          </main>

          {/* Footer with Page Navigation */}
          <Footer onNavigatePage={handleNavigatePage} onOpenLegal={handleOpenLegal} />

          {/* Modals */}
          <WatchDemoModal
            isOpen={isDemoModalOpen}
            onClose={() => setIsDemoModalOpen(false)}
            onSelectBotState={(st) => botControllerRef.current?.setState(st)}
            onTryLive={() => {
              setIsDemoModalOpen(false);
              setIsTalkModalOpen(true);
            }}
          />

          <TalkToMeModal
            isOpen={isTalkModalOpen}
            onClose={() => setIsTalkModalOpen(false)}
            onSelectBotState={(st) => botControllerRef.current?.setState(st)}
            onStartLive={() => {
              setIsTalkModalOpen(false);
              enterConsole(isAuthenticated ? 'employees' : DEFAULT_CONSOLE_TAB);
            }}
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
          notice={quarantineNotice || signOutReason}
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
