import React, { useState, useRef, useEffect, useCallback } from 'react';
import { AuthProvider } from './context/AuthContext';
import { WorkspaceProvider } from './console/context/WorkspaceContext';
import { Navbar } from './components/Navbar';
import { Hero } from './components/Hero';
import { LandingSections } from './components/LandingSections';
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
import { applyPageMetadata, PUBLIC_PATHS, viewFromLocation } from './lib/siteMetadata';
import { authService } from './services/authService';

import { ConsoleSkeleton } from './console/ConsoleSkeleton';

const ConsoleEntry = React.lazy(() => import('./console/ConsoleEntry'));

function AppInner() {
  const { isAuthenticated, isLoading, logout: authLogout, signOutReason, user } = useAuth();

  const [currentView, setCurrentView] = useState(() => {
    if (typeof window !== 'undefined') {
      const view = viewFromLocation(window.location);
      if (view === 'dashboard' && !authService.getSession()) {
        return 'landing';
      }
      return view;
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
    window.addEventListener('dialtact:open-tour', handleOpenTour);
    return () => {
      window.removeEventListener('dialtact:open-tour', handleOpenTour);
      window.removeEventListener('dialtact:open-tour', handleOpenTour);
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
      window.dispatchEvent(new CustomEvent('dialtact:auth-error', { detail: { code: authErr, message: msg } }));
    }
  }, []);

  useEffect(() => {
    const handleRouteChange = () => {
      if (window.location.hash.includes('reset-password')) {
        setAuthModalMode('reset'); setIsAuthModalOpen(true); return;
      }
      const view = viewFromLocation(window.location);
      if (view === 'dashboard') {
        const hasStoredSession = Boolean(authService.getSession());
        if (isLoading || hasStoredSession) {
          setCurrentView('dashboard');
          const tab = window.location.hash.match(/#dashboard\/([a-z0-9_-]+)/i)?.[1] || '';
          applyPageMetadata('dashboard', tab);
          return;
        }
        if (!isAuthenticated) {
          setCurrentView('landing');
          const tab = window.location.hash.match(/#dashboard\/([a-z0-9_-]+)/i)?.[1] || '';
          openAuthModal('signin', tab || DEFAULT_CONSOLE_TAB);
          window.history.replaceState({}, '', '/');
          applyPageMetadata('landing');
          return;
        }
      }
      setCurrentView(view);
      const tab = window.location.hash.match(/#dashboard\/([a-z0-9_-]+)/i)?.[1] || '';
      applyPageMetadata(view, tab);
    };
    handleRouteChange();
    window.addEventListener('hashchange', handleRouteChange);
    window.addEventListener('popstate', handleRouteChange);
    return () => {
      window.removeEventListener('hashchange', handleRouteChange);
      window.removeEventListener('popstate', handleRouteChange);
    };
  }, [isAuthenticated, isLoading]);


  const openAuthModal = (mode = 'signin', postAuthTab = DEFAULT_CONSOLE_TAB) => {
    rememberPostAuthTab(postAuthTab);
    setAuthModalMode(mode);
    setIsAuthModalOpen(true);
  };

  /** Sign-in and "Build your agent" open the modal in-place on the home page when unauthenticated, and navigate only post-auth. */
  const enterConsole = (tab = DEFAULT_CONSOLE_TAB) => {
    const targetTab = tab || DEFAULT_CONSOLE_TAB;
    if (!isAuthenticated) {
      if (currentView !== 'landing') {
        goToLanding();
      }
      openAuthModal("signin", targetTab);
      return;
    }
    setCurrentView("dashboard");
    window.history.pushState({}, "", "/" + consoleHash(targetTab));
    applyPageMetadata("dashboard", targetTab);
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  };

  const handleGetStarted = () => enterConsole(DEFAULT_CONSOLE_TAB);

  const goToLanding = () => {
    setCurrentView('landing');
    window.history.pushState({}, '', '/');
    applyPageMetadata('landing');
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
      window.history.pushState({}, '', PUBLIC_PATHS[targetView]);
      applyPageMetadata(targetView);
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
    // Landing section anchor (e.g. how-it-works, capabilities, industries, pricing, faq)
    if (currentView !== 'landing') {
      setCurrentView('landing');
    }
    window.history.pushState({}, '', `/#${cleanTarget}`);
    applyPageMetadata('landing');
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
        <React.Suspense fallback={<ConsoleSkeleton />}>
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
          onSignIn={() => { goToLanding(); openAuthModal('signin', DEFAULT_CONSOLE_TAB); }}
          onNavigatePage={handleNavigatePage}
        />
      ) : currentView === 'company' ? (
        <CompanyPage
          onBackToLanding={goToLanding}
          onEnterConsole={enterConsole}
          onSignIn={() => { goToLanding(); openAuthModal('signin', DEFAULT_CONSOLE_TAB); }}
          onNavigatePage={handleNavigatePage}
        />
      ) : currentView === 'privacy' ? (
        <PrivacyPage
          onBackToLanding={goToLanding}
          onEnterConsole={enterConsole}
          onSignIn={() => { goToLanding(); openAuthModal('signin', DEFAULT_CONSOLE_TAB); }}
          onNavigatePage={handleNavigatePage}
        />
      ) : currentView === 'terms' ? (
        <TermsPage
          onBackToLanding={goToLanding}
          onEnterConsole={enterConsole}
          onSignIn={() => { goToLanding(); openAuthModal('signin', DEFAULT_CONSOLE_TAB); }}
          onNavigatePage={handleNavigatePage}
        />
      ) : currentView === 'security' ? (
        <SecurityPage
          onBackToLanding={goToLanding}
          onEnterConsole={enterConsole}
          onSignIn={() => { goToLanding(); openAuthModal('signin', DEFAULT_CONSOLE_TAB); }}
          onNavigatePage={handleNavigatePage}
        />
      ) : (
        <div className="min-h-screen flex flex-col bg-[#FAF9FD] selection:bg-[#F0EEF6] selection:text-[#6344E7]">
          {/* Navigation Header */}
          <Navbar
            onEnterConsole={enterConsole}
            onSignIn={() => openAuthModal('signin', DEFAULT_CONSOLE_TAB)}
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

            <LandingSections
              onGetStarted={handleGetStarted}
              onSelectPlan={handleSelectPlan}
              onNavigatePage={handleNavigatePage}
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
