/**
 * Voxly AI Authentication Service
 * 
 * Powered by the unified API Gateway (`api.auth.*`).
 * Supports both Live Backend authentication (FastAPI / Express / Supabase)
 * and Local Simulator Engine with active JWT tokens and audit logs.
 */

import { api } from './api';

const STORAGE_KEY = 'voxly_auth_session';

export const authService = {
  /**
   * Get current stored session from localStorage or API
   */
  getSession() {
    try {
      const data = localStorage.getItem(STORAGE_KEY);
      return data ? JSON.parse(data) : null;
    } catch (e) {
      console.warn('Error reading auth session:', e);
      return null;
    }
  },

  /**
   * Save session to localStorage
   */
  saveSession(user) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
    } catch (e) {
      console.warn('Error saving auth session:', e);
    }
  },

  /**
   * Clear session from localStorage
   */
  clearSession() {
    try {
      localStorage.removeItem(STORAGE_KEY);
      api.clearToken();
    } catch (e) {
      console.warn('Error clearing auth session:', e);
    }
  },

  /**
   * Sign in with Google
   */
  async signInWithGoogle() {
    const res = await api.auth.googleLogin();
    const user = res.user
      ? {
          id: res.user.userId,
          name: res.user.fullName || res.user.email,
          email: res.user.email,
          tenantId: res.tenant?.tenantId,
        }
      : null;
    if (user) this.saveSession(user);
    return user;
  },

  /**
   * Sign in with GitHub
   */
  async signInWithGithub() {
    const res = await api.auth.githubLogin();
    const user = res.user;
    this.saveSession(user);
    return user;
  },

  /**
   * Sign in with Email & Password
   */
  async signInWithEmailPassword(email, password) {
    if (!email || !password) {
      throw new Error('Please enter both your work email and password.');
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email.trim())) {
      throw new Error('Please enter a valid work email address.');
    }

    if (password.length < 6) {
      throw new Error('Password must be at least 6 characters long.');
    }

    const res = await api.auth.login(email.trim(), password);
    const user = {
      id: res.user?.userId,
      name: res.user?.fullName || res.user?.email,
      email: res.user?.email,
      tenantId: res.tenant?.tenantId,
    };
    this.saveSession(user);
    return { ...res, user };
  },

  /**
   * Sign up with Name, Email & Password
   */
  async signUpWithEmailPassword(name, email, password) {
    if (!name || name.trim().length < 2) {
      throw new Error('Please enter your full name.');
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!email || !emailRegex.test(email.trim())) {
      throw new Error('Please enter a valid work email address.');
    }

    if (!password || password.length < 8) {
      throw new Error('Password must be at least 8 characters long for security.');
    }

    const res = await api.auth.signup(name.trim(), email.trim(), password);
    if (res.requiresEmailVerification) {
      return res;
    }
    const user = {
      id: res.user?.userId,
      name: res.user?.fullName || name,
      email: res.user?.email,
      tenantId: res.tenant?.tenantId,
    };
    this.saveSession(user);
    return { ...res, user };
  },

  /**
   * Sign in with Magic Link
   */
  async sendMagicLink(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!email || !emailRegex.test(email.trim())) {
      throw new Error('Please provide a valid work email address.');
    }
    return await api.auth.magicLink(email.trim());
  },

  /**
   * Sign in with Enterprise SAML / SSO
   */
  async signInWithSSO(domain) {
    if (!domain || !domain.includes('.')) {
      throw new Error('Please enter a valid company domain (e.g., company.com).');
    }
    const res = await api.auth.ssoLogin(domain.trim());
    const user = res.user;
    this.saveSession(user);
    return user;
  },

  /**
   * Sign out current user
   */
  async signOut() {
    await api.auth.logout();
    this.clearSession();
    return true;
  },
};
