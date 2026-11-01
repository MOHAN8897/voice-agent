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
import { MarketingPage } from './marketing/MarketingPage';
import { SignInPage } from './marketing/SignInPage';

const ConsoleEntry = React.lazy(() => import('./console/ConsoleEntry'));

function AppInner({ initialView = 'landing' }) {
  const { isAuthenticated, isLoading, logout: authLogout, signOutReason, user } = useAuth();

  const [currentView, setCurrentView] = useState(() => {
    if (typeof window !== 'undefined') {
      const view = viewFromLocation(window.location);
      if (view === 'dashboard' && !authService.getSession()) {
        return 'landing';
      }
      return view;
    }
    return initialView;
  });

  const [isDemoModalOpen, setIsDemoModalOpen] = useState(false);
  const [isTalkModalOpen, setIsTalkModalOpen] = useState(false);
  const [isLegalModalOpen, setIsLegalModalOpen] = useState(false);
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
      showSignInPage();
    }
    const params = new URLSearchParams(window.location.search);
    const notice = params.get('notice');
    if (notice === 'workspace_quarantined' || notice === 'workspace_deleted') {
      setAuthModalMode('signin');
      setQuarantineNotice(
        notice === 'workspace_deleted'
          ? 'This workspace was permanently deleted after its grace period ended, so it can no longer be restored.'
          : 'Your workspace is scheduled for deletion. You have 14 days to change your mind: sign in as the owner to restore it or download your data.'
      );
      showSignInPage();
      window.setTimeout(() => {
        window.history.replaceState({}, '', window.location.pathname + window.location.hash);
      }, 0);
    }
    const authErr = params.get('auth_error');
    if (authErr) {
      setAuthModalMode('signin');
      showSignInPage();
      const msg =
        authErr === 'google_state'
          ? 'Google sign-in expired. Please try again.'
          : authErr === 'workspace_deleted'
            ? 'This workspace was permanently deleted after its grace period ended, so it can no longer be restored.'
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
        setAuthModalMode('reset'); showSignInPage(); return;
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
          const tab = window.location.hash.match(/#dashboard\/([a-z0-9_-]+)/i)?.[1] || '';
          openAuthModal('signin', tab || DEFAULT_CONSOLE_TAB, { replace: true });
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


  /**
   * Sign-in is a page at /signin, not a dialog: a real URL the visitor can come back to
   * and share. A password-reset link keeps its #reset-password?token=… fragment, which
   * the form reads when it is submitted.
   */
  const showSignInPage = ({ replace = false } = {}) => {
    setCurrentView('signin');
    const hash = window.location.hash.includes('reset-password') ? window.location.hash : '';
    const target = `/signin${window.location.search}${hash}`;
    if (window.location.pathname !== '/signin' || replace) {
      window.history[replace ? 'replaceState' : 'pushState']({}, '', target);
    }
    applyPageMetadata('signin');
    window.scrollTo(0, 0);
  };

  const openAuthModal = (mode = 'signin', postAuthTab = DEFAULT_CONSOLE_TAB, options) => {
    rememberPostAuthTab(postAuthTab);
    setAuthModalMode(mode);
    showSignInPage(options);
  };

  /** Signed out, the console opens the sign-in page; it navigates only after sign-in. */
  const enterConsole = (tab = DEFAULT_CONSOLE_TAB) => {
    const targetTab = tab || DEFAULT_CONSOLE_TAB;
    if (!isAuthenticated) {
      openAuthModal('signin', targetTab);
      return;
    }
    setCurrentView("dashboard");
    window.history.pushState({}, "", "/" + consoleHash(targetTab));
    applyPageMetadata("dashboard", targetTab);
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  };

  const handleGetStarted = () => enterConsole(DEFAULT_CONSOLE_TAB);

  /** "Create your own agent": new visitors start on sign-up; the builder opens after. */
  const handleCreateAgent = () => {
    if (isAuthenticated) enterConsole(DEFAULT_CONSOLE_TAB);
    else openAuthModal('signup', DEFAULT_CONSOLE_TAB);
  };

  const handleAuthSuccess = () => {
    const tab = consumePostAuthTab();
    setCurrentView('dashboard');
    window.history.replaceState({}, '', '/' + consoleHash(tab));
    applyPageMetadata('dashboard', tab);
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  };

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
    // Links arrive as '#pricing', '/#pricing', '/company' or 'company'.
    const cleanTarget = String(target || '').replace(/^\/?#?/, '');
    if (!cleanTarget || cleanTarget === 'landing' || cleanTarget === 'home') {
      goToLanding();
      return;
    }
    if (cleanTarget.startsWith('dashboard')) {
      const tab = cleanTarget.replace('dashboard/', '').replace('dashboard', '');
      enterConsole(tab || DEFAULT_CONSOLE_TAB);
      return;
    }
    if (cleanTarget === 'signin') {
      openAuthModal('signin', DEFAULT_CONSOLE_TAB);
      return;
    }
    if (['contact', 'support', 'company', 'about', 'privacy', 'terms', 'security', 'legacy'].includes(cleanTarget)) {
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
    // Landing section anchor (e.g. how-it-works, capabilities, industries, pricing, faq).
    // The previous home page keeps its own anchors so its links stay on /legacy.
    const anchorView = currentView === 'legacy' ? 'legacy' : 'landing';
    if (currentView !== anchorView) {
      setCurrentView(anchorView);
    }
    window.history.pushState({}, '', `${PUBLIC_PATHS[anchorView]}#${cleanTarget}`);
    applyPageMetadata(anchorView);
    window.setTimeout(() => {
      const elem = document.getElementById(cleanTarget);
      if (!elem) return;
      // The new home page scrolls through Lenis; native smooth scroll fights it.
      if (window.__dialtactLenis) window.__dialtactLenis.scrollTo(elem, { offset: -72 });
      else elem.scrollIntoView({ behavior: 'smooth' });
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
      window.history.replaceState({}, '', window.location.pathname);
      openAuthModal('signin', parseDashboardTabFromHash('#dashboard/employees'), { replace: true });
    }
  }, []);

  useEffect(() => {
    if (currentView !== 'signin' || isLoading || !isAuthenticated || authModalMode === 'reset') return;
    handleAuthSuccess();
  }, [currentView, isLoading, isAuthenticated, authModalMode]); // eslint-disable-line react-hooks/exhaustive-deps

  // An idle sign-out happens wherever the person happened to be. Put them back in
  // front of the sign-in form with the reason, instead of leaving them on a console
  // shell that silently stopped working.
  useEffect(() => {
    if (!signOutReason) return;
    setAuthModalMode('signin');
    showSignInPage();
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
      ) : currentView === 'signin' ? (
        <SignInPage
          mode={authModalMode}
          notice={quarantineNotice || signOutReason}
          onAuthSuccess={handleAuthSuccess}
          onBack={goToLanding}
        />
      ) : currentView === 'support' ? (
        <SupportPage
          onBackToLanding={goToLanding}
          onEnterConsole={enterConsole}
          onSignIn={() => openAuthModal('signin', DEFAULT_CONSOLE_TAB)}
          onNavigatePage={handleNavigatePage}
        />
      ) : currentView === 'company' ? (
        <CompanyPage
          onBackToLanding={goToLanding}
          onEnterConsole={enterConsole}
          onSignIn={() => openAuthModal('signin', DEFAULT_CONSOLE_TAB)}
          onNavigatePage={handleNavigatePage}
        />
      ) : currentView === 'privacy' ? (
        <PrivacyPage
          onBackToLanding={goToLanding}
          onEnterConsole={enterConsole}
          onSignIn={() => openAuthModal('signin', DEFAULT_CONSOLE_TAB)}
          onNavigatePage={handleNavigatePage}
        />
      ) : currentView === 'terms' ? (
        <TermsPage
          onBackToLanding={goToLanding}
          onEnterConsole={enterConsole}
          onSignIn={() => openAuthModal('signin', DEFAULT_CONSOLE_TAB)}
          onNavigatePage={handleNavigatePage}
        />
      ) : currentView === 'security' ? (
        <SecurityPage
          onBackToLanding={goToLanding}
          onEnterConsole={enterConsole}
          onSignIn={() => openAuthModal('signin', DEFAULT_CONSOLE_TAB)}
          onNavigatePage={handleNavigatePage}
        />
      ) : currentView === 'legacy' ? (
        <div className="min-h-screen flex flex-col bg-[#FAF9FD] selection:bg-[#F0EEF6] selection:text-[#6344E7]">
          {/* The previous home page, kept intact at /legacy. */}
          <Navbar
            onEnterConsole={enterConsole}
            onSignIn={() => openAuthModal('signin', DEFAULT_CONSOLE_TAB)}
            onWatchDemo={() => setIsDemoModalOpen(true)}
            onNavigatePage={handleNavigatePage}
          />
          <main className="flex-1">
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
          <Footer onNavigatePage={handleNavigatePage} onOpenLegal={handleOpenLegal} />
        </div>
      ) : (
        <MarketingPage
          onGetStarted={handleCreateAgent}
          onSignIn={() => openAuthModal('signin', DEFAULT_CONSOLE_TAB)}
          onEnterConsole={enterConsole}
          onSelectPlan={handleSelectPlan}
          onNavigatePage={handleNavigatePage}
          botControllerRef={botControllerRef}
          isModalOpen={isDemoModalOpen || isTalkModalOpen}
        />
      )}

      {currentView === 'landing' || currentView === 'legacy' ? (
        <>
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
        </>
      ) : null}

        <VerifyEmailBanner
          onSignIn={() => openAuthModal('signin', DEFAULT_CONSOLE_TAB)}
        />
    </>
  );
}

export function App({ initialView }) {
  return (
    <AuthProvider>
      <WorkspaceProvider>
        <AppInner initialView={initialView} />
      </WorkspaceProvider>
    </AuthProvider>
  );
}

export default App;
