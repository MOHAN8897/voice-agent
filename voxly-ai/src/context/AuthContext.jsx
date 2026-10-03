import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
} from 'react';
import { authService } from '../services/authService';
import { api, subscribeSessionPolicy } from '../services/api';
import { initAuthSessionSync } from '../services/authSessionSync';
import { createIdleSessionMonitor, DEFAULT_IDLE_TIMEOUT_MS } from '../services/sessionIdle';
import { IdleWarningModal } from '../components/IdleWarningModal';
import { loadGoogleIdentityScript } from '../utils/loadGoogleIdentity';

const AuthContext = createContext(null);

/** Why the session ended, so the sign-in screen can say something useful. */
const SIGN_OUT_REASONS = {
  idle: 'You were signed out after a period of inactivity. Please sign in again.',
  absolute_max: 'Your session reached its maximum length. Please sign in again.',
  manual: '',
};

function normalizeUser(meOrAuth) {
  const user = meOrAuth?.user || meOrAuth;
  const tenant = meOrAuth?.tenant;
  if (!user) return null;
  const imp = meOrAuth?.impersonation || null;
  return {
    id: user.userId || user.id,
    name: user.fullName || user.name || user.email,
    email: user.email,
    tenantId: tenant?.tenantId,
    tenantName: tenant?.name,
    role: meOrAuth?.role,
    isPlatformAdmin: Boolean(meOrAuth?.isPlatformAdmin),
    isDevTester: Boolean(meOrAuth?.isDevTester),
    impersonation: imp
      ? {
          actor: imp.actor,
          tenantId: imp.tenantId || tenant?.tenantId,
          tenantName: imp.tenantName || tenant?.name,
          userEmail: imp.userEmail || user.email,
          expiresIn: imp.expiresIn,
        }
      : null,
  };
}

const IMP_KEY = 'voxly_impersonation';

function readStoredImpersonation() {
  try {
    const raw = sessionStorage.getItem(IMP_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeStoredImpersonation(imp) {
  try {
    if (imp) sessionStorage.setItem(IMP_KEY, JSON.stringify(imp));
    else sessionStorage.removeItem(IMP_KEY);
  } catch {
    /* ignore */
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  // Session policy, learned from the server on every auth response. Held in state so
  // the idle monitor is rebuilt whenever the server's bounds change.
  const [sessionPolicy, setSessionPolicy] = useState(null);
  const [idleWarning, setIdleWarning] = useState(null);
  const [signOutReason, setSignOutReason] = useState('');
  const idleRef = useRef(null);

  const adoptSessionPolicy = useCallback((policy) => {
    if (!policy || typeof policy !== 'object') return;
    setSessionPolicy((prev) => {
      const next = {
        idleTimeoutMinutes: Number(policy.idleTimeoutMinutes) || 0,
        absoluteMaxHours: Number(policy.absoluteMaxHours) || 0,
        accessTokenMinutes: Number(policy.accessTokenMinutes) || 0,
      };
      if (
        prev &&
        prev.idleTimeoutMinutes === next.idleTimeoutMinutes &&
        prev.absoluteMaxHours === next.absoluteMaxHours
      ) {
        return prev;
      }
      return next;
    });
  }, []);

  const refreshSession = useCallback(async () => {
    if (!api.getToken()) {
      // Cold load with no prior local session → skip refresh. Calling /auth/refresh
      // without a cookie returns 401 and Chrome logs a noisy "Failed to load resource".
      const hadSession = Boolean(authService.getSession());
      if (!hadSession) {
        setUser(null);
        return null;
      }
      const refreshed = await api.refreshAccessToken();
      if (!refreshed) {
        setUser(null);
        return null;
      }
    }
    try {
      const me = await api.auth.getMe();
      const normalized = normalizeUser(me);
      authService.saveSession(normalized);
      setUser(normalized);
      window.dispatchEvent(new Event('voxly:session'));
      return normalized;
    } catch (err) {
      if (import.meta.env.DEV) {
        console.warn('[voxly:auth] Session restore failed:', err?.message || err);
      }
      api.clearToken();
      authService.clearSession();
      setUser(null);
      return null;
    }
  }, []);

  useEffect(() => {
    const run = async () => {
      initAuthSessionSync();
      const hash = window.location.hash || '';
      if (hash.includes('auth/callback')) {
        const qs = hash.split('?')[1] || '';
        const params = new URLSearchParams(qs);
        const handoff = params.get('handoff');
        const access = params.get('accessToken');
        window.location.hash = '#dashboard/employees';
        if (handoff) {
          try {
            const data = await api.auth.consumeHandoff(handoff);
            const normalized = normalizeUser(data);
            if (normalized) {
              if (data?.impersonation) {
                writeStoredImpersonation(data.impersonation);
                normalized.impersonation = {
                  actor: data.impersonation.actor,
                  tenantId: data.impersonation.tenantId,
                  tenantName: data.impersonation.tenantName,
                  userEmail: data.impersonation.userEmail,
                  expiresIn: data.impersonation.expiresIn,
                };
              }
              authService.saveSession(normalized);
              setUser(normalized);
            }
          } catch {
            /* refreshSession below will clear a dead handoff */
          }
        } else if (access) {
          // Legacy redirect put access in the hash but Set-Cookie on the API host —
          // cookie never reaches the SPA origin. Prefer handoff; this still restores access.
          api.setToken(access);
        }
      }

      const stored = authService.getSession();
      if (stored && api.getToken()) {
        const withImp = { ...stored, impersonation: stored.impersonation || readStoredImpersonation() };
        setUser(withImp);
      }
      const refreshed = await refreshSession();
      if (refreshed && !refreshed.impersonation) {
        const storedImp = readStoredImpersonation();
        if (storedImp) {
          setUser({ ...refreshed, impersonation: storedImp });
        }
      }
      setIsLoading(false);
    };
    run();
  }, [refreshSession]);

  // Cross-tab logout / access adoption + proactive refresh on tab focus.
  useEffect(() => {
    initAuthSessionSync();
    const onSync = (ev) => {
      const detail = ev?.detail;
      if (!detail) return;
      if (detail.type === 'logout') {
        api.clearToken();
        authService.clearSession();
        writeStoredImpersonation(null);
        setUser(null);
        return;
      }
      if (detail.type === 'access' && detail.accessToken) {
        api.adoptPeerAccessToken(detail.accessToken);
      }
      if (detail.type === 'activity') {
        // Real human input happened in a sibling tab.
        idleRef.current?.syncFromPeer(detail.at);
        setIdleWarning(null);
        return;
      }
      if (detail.type === 'idle-warning') {
        setIdleWarning((prev) => prev ?? { remainingMs: 120000 });
      }
    };
    const onVis = () => {
      if (document.visibilityState !== 'visible') return;
      if (!api.getToken()) return;
      api.ensureFreshAccessToken().catch(() => {});
    };
    window.addEventListener('voxly:auth-sync', onSync);
    document.addEventListener('visibilitychange', onVis);
    return () => {
      window.removeEventListener('voxly:auth-sync', onSync);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, []);

  // Learn the server's session bounds from any auth response.
  useEffect(() => subscribeSessionPolicy(adoptSessionPolicy), [adoptSessionPolicy]);

  // Inactivity timeout. Runs only while signed in; the server refuses a stale refresh
  // regardless, so this exists to warn first and to release the session cleanly.
  useEffect(() => {
    if (!user || !api.getToken()) {
      idleRef.current?.dispose();
      idleRef.current = null;
      setIdleWarning(null);
      return undefined;
    }
    const monitor = createIdleSessionMonitor({
      idleTimeoutMinutes: sessionPolicy?.idleTimeoutMinutes || DEFAULT_IDLE_TIMEOUT_MS / 60000,
      absoluteMaxHours: sessionPolicy?.absoluteMaxHours || 24,
      onState: (state) => {
        if (state.state === 'warning') {
          setIdleWarning({ remainingMs: state.remainingMs });
        } else if (state.state === 'active') {
          setIdleWarning(null);
        }
      },
      onExpire: (reason) => {
        const key = reason === 'session_absolute_max' ? 'absolute_max' : 'idle';
        // Best-effort server logout; the local session is cleared either way because
        // the refresh cookie is dead server-side too.
        authService.signOut().catch(() => {});
        writeStoredImpersonation(null);
        setSignOutReason(SIGN_OUT_REASONS[key] || SIGN_OUT_REASONS.idle);
        setUser(null);
        setIdleWarning(null);
      },
    });
    idleRef.current = monitor;
    monitor.start();
    // Exposed so an end-to-end test can shorten the window (a 30-minute policy is
    // otherwise untestable) and so support can inspect the live countdown.
    if (typeof window !== 'undefined') window.__voxlyIdle = monitor;
    return () => {
      monitor.dispose();
      if (typeof window !== 'undefined' && window.__voxlyIdle === monitor) {
        delete window.__voxlyIdle;
      }
      idleRef.current = null;
    };
  }, [user, sessionPolicy?.idleTimeoutMinutes, sessionPolicy?.absoluteMaxHours]);

  const staySignedIn = useCallback(() => {
    idleRef.current?.extend();
    setIdleWarning(null);
  }, []);

  const loginWithGoogle = async () => {
    let clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';
    try {
      const cfg = await api.auth.googleConfig();
      if (!cfg?.enabled) {
        throw new Error('Google sign-in is not available. Please try email sign-in or contact support.');
      }
      if (!clientId && cfg.clientId) clientId = cfg.clientId;
    } catch (e) {
      if (!clientId) throw e;
    }

    await loadGoogleIdentityScript();

    if (clientId && window.google?.accounts?.id) {
      return new Promise((resolve, reject) => {
        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: async (response) => {
            try {
              const data = await api.auth.googleLogin(response.credential);
              const normalized = normalizeUser(data);
              authService.saveSession(normalized);
              setUser(normalized);
              window.dispatchEvent(new Event('voxly:session'));
              resolve(normalized);
            } catch (err) {
              reject(err);
            }
          },
        });
        window.google.accounts.id.prompt((notification) => {
          if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
            api.auth.googleRedirectLogin();
            resolve(null);
          }
        });
      });
    }

    api.auth.googleRedirectLogin();
    return null;
  };

  const loginWithGithub = async () => {
    throw new Error('GitHub sign-in is not available.');
  };

  const loginWithEmail = async (email, password) => {
    const data = await authService.signInWithEmailPassword(email, password);
    const normalized = normalizeUser(data);
    setUser(normalized);
    setSignOutReason('');
    idleRef.current?.resetSession();
    window.dispatchEvent(new Event('voxly:session'));
    return normalized;
  };

  const signupWithEmail = async (name, email, password) => {
    const data = await authService.signUpWithEmailPassword(name, email, password);
    if (data?.requiresEmailVerification) {
      return data;
    }
    const normalized = normalizeUser(data);
    setUser(normalized);
    idleRef.current?.resetSession();
    window.dispatchEvent(new Event('voxly:session'));
    return normalized;
  };

  const loginWithMagicLink = async () => {
    throw new Error('Magic link is not enabled. Use email/password or Google.');
  };

  const loginWithSSO = async () => {
    throw new Error('SSO is not enabled.');
  };

  const logout = async () => {
    try {
      await authService.signOut();
    } finally {
      writeStoredImpersonation(null);
      setSignOutReason('');
      setIdleWarning(null);
      idleRef.current?.resetSession();
      setUser(null);
      window.dispatchEvent(new Event('voxly:logout'));
    }
  };

  /** Adopt a session handed over by password reset / OTP verification. */
  const adoptSession = useCallback(async () => {
    const normalized = await refreshSession();
    if (normalized) idleRef.current?.resetSession();
    return normalized;
  }, [refreshSession]);

  const signOutFromWarning = useCallback(() => logout(), [logout]);

  const value = useMemo(
    () => ({
      user,
      isAuthenticated: !!user && !!api.getToken(),
      isPlatformAdmin: Boolean(user?.isPlatformAdmin),
      isDevTester: Boolean(user?.isDevTester),
      isLoading,
      sessionPolicy,
      signOutReason,
      clearSignOutReason: () => setSignOutReason(''),
      staySignedIn,
      loginWithGoogle,
      loginWithGithub,
      loginWithEmail,
      signupWithEmail,
      loginWithMagicLink,
      loginWithSSO,
      logout,
      refreshSession,
      adoptSession,
    }),
    [
      user,
      isLoading,
      sessionPolicy,
      signOutReason,
      staySignedIn,
      loginWithGoogle,
      loginWithGithub,
      loginWithEmail,
      signupWithEmail,
      loginWithMagicLink,
      loginWithSSO,
      logout,
      refreshSession,
      adoptSession,
    ]
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
      <IdleWarningModal
        isOpen={Boolean(idleWarning)}
        remainingMs={idleWarning?.remainingMs ?? 0}
        email={user?.email || ''}
        onStay={staySignedIn}
        onSignOut={signOutFromWarning}
      />
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
