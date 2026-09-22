import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authService } from '../services/authService';
import { api } from '../services/api';
import { loadGoogleIdentityScript } from '../utils/loadGoogleIdentity';

const AuthContext = createContext(null);

function normalizeUser(meOrAuth) {
  const user = meOrAuth?.user || meOrAuth;
  const tenant = meOrAuth?.tenant;
  if (!user) return null;
  return {
    id: user.userId || user.id,
    name: user.fullName || user.name || user.email,
    email: user.email,
    tenantId: tenant?.tenantId,
    tenantName: tenant?.name,
    role: meOrAuth?.role,
  };
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshSession = useCallback(async () => {
    if (!api.getToken()) {
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
    } catch {
      api.clearToken();
      authService.clearSession();
      setUser(null);
      return null;
    }
  }, []);

  useEffect(() => {
    const run = async () => {
      const hash = window.location.hash || '';
      if (hash.includes('auth/callback')) {
        const qs = hash.split('?')[1] || '';
        const params = new URLSearchParams(qs);
        const access = params.get('accessToken');
        if (access) api.setToken(access);
        window.location.hash = '#dashboard/employees';
      }

      const stored = authService.getSession();
      if (stored && api.getToken()) {
        setUser(stored);
      }
      await refreshSession();
      setIsLoading(false);
    };
    run();
  }, [refreshSession]);

  const loginWithGoogle = async () => {
    let clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';
    try {
      const cfg = await api.auth.googleConfig();
      if (!cfg?.enabled) {
        throw new Error('Google sign-in is not configured on this server. Add GOOGLE_OAUTH_CLIENT_ID and secret to the API .env.');
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
    return normalized;
  };

  const signupWithEmail = async (name, email, password) => {
    const data = await authService.signUpWithEmailPassword(name, email, password);
    const normalized = normalizeUser(data);
    setUser(normalized);
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
      setUser(null);
      window.dispatchEvent(new Event('voxly:logout'));
    }
  };

  const value = {
    user,
    isAuthenticated: !!user && !!api.getToken(),
    isLoading,
    loginWithGoogle,
    loginWithGithub,
    loginWithEmail,
    signupWithEmail,
    loginWithMagicLink,
    loginWithSSO,
    logout,
    refreshSession,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
