import React, { useState, useEffect } from 'react';
import { X, Lock, Mail, ArrowRight, CheckCircle2, Eye, EyeOff, Sparkles } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { analytics } from '../services/analytics';
import { api } from '../services/api';

export function AuthModal({ isOpen, onClose, initialMode = 'signin', onAuthSuccess }) {
  const { loginWithGoogle, loginWithEmail, signupWithEmail } = useAuth();

  const [mode, setMode] = useState(initialMode);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loadingMethod, setLoadingMethod] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const [googleSignInEnabled, setGoogleSignInEnabled] = useState(true);
  const [googleConfigHint, setGoogleConfigHint] = useState('');
  const [showResendVerification, setShowResendVerification] = useState(false);
  const [resendStatus, setResendStatus] = useState('');

  useEffect(() => {
    const onAuthErr = (e) => {
      setErrorMessage(e.detail?.message || 'Sign-in failed.');
      setMode('signin');
    };
    window.addEventListener('voxly:auth-error', onAuthErr);
    return () => window.removeEventListener('voxly:auth-error', onAuthErr);
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    (async () => {
      try {
        const cfg = await api.auth.googleConfig();
        if (cancelled) return;
        setGoogleSignInEnabled(Boolean(cfg?.enabled));
        if (!cfg?.enabled) {
          setGoogleConfigHint('Google sign-in requires GOOGLE_OAUTH_* on the API server.');
        } else {
          setGoogleConfigHint('');
        }
      } catch {
        if (!cancelled) {
          setGoogleSignInEnabled(true);
          setGoogleConfigHint('');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  useEffect(() => {
    setMode(initialMode);
    setErrorMessage('');
    setSuccessMessage('');
  }, [initialMode, isOpen]);

  useEffect(() => {
    if (!isOpen && window.location.hash?.includes('reset-password')) {
      setMode('reset');
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleGoogleSignIn = async () => {
    try {
      setErrorMessage('');
      setLoadingMethod('google');
      const user = await loginWithGoogle();
      if (!user) return;
      analytics.track('auth_google_success', { userId: user.id });
      setSuccessMessage(`Welcome back, ${user.name}!`);
      setTimeout(() => {
        onClose();
        if (onAuthSuccess) onAuthSuccess(user);
      }, 600);
    } catch (err) {
      setErrorMessage(err.message || 'Failed to sign in with Google.');
    } finally {
      setLoadingMethod(null);
    }
  };

  const handleEmailSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');

    try {
      let authedUser = null;
      if (mode === 'signup') {
        setLoadingMethod('email');
        const signupRes = await signupWithEmail(name, email, password);
        if (signupRes?.requiresEmailVerification) {
          setSuccessMessage(signupRes.message || 'Check your email to verify your account, then sign in.');
          setMode('signin');
          return;
        }
        authedUser = signupRes;
        analytics.track('auth_signup_success', { userId: authedUser.id });
        setSuccessMessage(`Account created! Welcome to Voxly, ${authedUser.name}.`);
      } else if (mode === 'forgot') {
        setLoadingMethod('email');
        await api.auth.forgotPassword(email);
        setSuccessMessage('If an account exists, reset instructions were sent to your email.');
        setMode('signin');
        return;
      } else if (mode === 'reset') {
        setLoadingMethod('email');
        const token = new URLSearchParams((window.location.hash.split('?')[1]) || '').get('token');
        if (!token) throw new Error('Reset link is invalid or expired.');
        await api.auth.resetPassword(token, password);
        setSuccessMessage('Password updated. Sign in with your new password.');
        window.location.hash = '';
        setMode('signin');
        return;
      } else if (mode === 'signin') {
        setLoadingMethod('email');
        authedUser = await loginWithEmail(email, password);
        analytics.track('auth_signin_success', { userId: authedUser.id });
        setSuccessMessage(`Welcome back, ${authedUser.name}!`);
      }
      setTimeout(() => {
        onClose();
        if (onAuthSuccess) onAuthSuccess(authedUser);
      }, 700);
    } catch (err) {
      setErrorMessage(err.message || 'Authentication error.');
      setShowResendVerification(err.code === 'email_unverified');
    } finally {
      setLoadingMethod(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-[#0F0E17]/60 backdrop-blur-sm transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal Dialog */}
      <div className="relative bg-white rounded-2xl border border-[#E4E2EB] shadow-2xl w-full max-w-md overflow-hidden z-10 animate-in fade-in zoom-in-95 duration-200 text-left">
        
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 pt-6 pb-2">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-[#0F0E17] flex items-center justify-center text-white shadow-xs">
              <Lock className="w-4 h-4" />
            </div>
            <span className="text-xs font-mono font-semibold text-[#524E5E] uppercase tracking-wider">
              Voxly Fleet Identity
            </span>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg bg-[#FAF9FD] hover:bg-[#F0EEF6] border border-[#E4E2EB] flex items-center justify-center text-[#524E5E] hover:text-[#0F0E17] transition-colors"
            aria-label="Close dialog"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Title */}
        <div className="px-6 pt-3 pb-4 border-b border-[#E4E2EB]">
          <h3 className="text-xl font-extrabold text-[#0F0E17] tracking-tight">
            {mode === 'signup' ? 'Create your account' : 'Sign in to build your agent'}
          </h3>
          <p className="text-xs text-[#524E5E] mt-1">
            {mode === 'signup'
              ? 'One account for the marketing site and your private agent console.'
              : 'Same sign-in as “Build your agent” — opens your subscriber console.'}
          </p>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-4">
          
          {/* Alerts: Error & Success */}
          {errorMessage && (
            <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs font-medium flex items-start gap-2">
              <span className="font-bold">Error:</span>
              <span>{errorMessage}</span>
            </div>
          )}

          {successMessage && (
            <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-medium flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <span>{successMessage}</span>
            </div>
          )}

          {showResendVerification && email && (
            <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs space-y-2">
              <p>Your account is not verified yet.</p>
              <button
                type="button"
                disabled={loadingMethod !== null}
                onClick={async () => {
                  setResendStatus('');
                  try {
                    await api.auth.resendVerification(email.trim());
                    setResendStatus('If this email is registered, we sent a new verification link.');
                  } catch (e) {
                    setResendStatus(e.message || 'Could not resend.');
                  }
                }}
                className="font-semibold text-[#6344E7] hover:underline"
              >
                Resend verification email
              </button>
              {resendStatus && <p className="text-[#524E5E]">{resendStatus}</p>}
            </div>
          )}

          {/* Social Sign-in Buttons (shown in standard signin/signup modes) */}
          {(mode === 'signin' || mode === 'signup') && (
            <div className="space-y-2.5">
              {/* Google OAuth Button */}
              {googleConfigHint && (
                <p className="text-[10px] text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-2.5 py-1.5">
                  {googleConfigHint}
                </p>
              )}
              <button
                type="button"
                onClick={handleGoogleSignIn}
                disabled={loadingMethod !== null || !googleSignInEnabled}
                title={!googleSignInEnabled ? googleConfigHint : undefined}
                className="w-full flex items-center justify-center gap-3 py-2.5 px-4 rounded-xl bg-white hover:bg-[#FAF9FD] text-[#0F0E17] font-semibold text-xs border border-[#E4E2EB] shadow-xs active:scale-[0.98] transition-all disabled:opacity-60"
              >
                {loadingMethod === 'google' ? (
                  <div className="w-4 h-4 border-2 border-[#E4E2EB] border-t-[#0F0E17] rounded-full animate-spin" />
                ) : (
                  <svg className="w-4 h-4" viewBox="0 0 24 24">
                    <path
                      fill="#4285F4"
                      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                    />
                    <path
                      fill="#34A853"
                      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                    />
                    <path
                      fill="#FBBC05"
                      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                    />
                    <path
                      fill="#EA4335"
                      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                    />
                  </svg>
                )}
                <span>Continue with Google</span>
              </button>

              {/* Hairline Divider */}
              <div className="relative py-2">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-[#E4E2EB]" />
                </div>
                <div className="relative flex justify-center text-[10px] uppercase font-mono font-bold tracking-wider text-[#524E5E]">
                  <span className="bg-white px-3">or continue with work email</span>
                </div>
              </div>
            </div>
          )}

          {/* Email / Password Form */}
          {(mode === 'signin' || mode === 'signup' || mode === 'forgot' || mode === 'reset') && (
            <form onSubmit={handleEmailSubmit} className="space-y-3">
              {mode === 'signup' && (
                <div>
                  <label className="block text-xs font-semibold text-[#0F0E17] mb-1">
                    Full Name
                  </label>
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Sarah Connor"
                    className="w-full text-xs px-3.5 py-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] focus:outline-none focus:border-[#0F0E17] text-[#0F0E17] placeholder:text-[#635F70]"
                  />
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-[#0F0E17] mb-1">
                  Work Email
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="alex@company.com"
                  className="w-full text-xs px-3.5 py-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] focus:outline-none focus:border-[#0F0E17] text-[#0F0E17] placeholder:text-[#635F70]"
                />
              </div>

              {mode !== 'forgot' && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-xs font-semibold text-[#0F0E17]">
                    Password
                  </label>
                  {mode === 'signin' && (
                    <button
                      type="button"
                      onClick={() => setMode('forgot')}
                      className="text-[11px] text-[#6344E7] hover:underline font-medium"
                    >
                      Forgot password?
                    </button>
                  )}
                </div>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full text-xs px-3.5 py-2.5 pr-10 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] focus:outline-none focus:border-[#0F0E17] text-[#0F0E17] placeholder:text-[#635F70]"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#524E5E] hover:text-[#0F0E17]"
                    tabIndex="-1"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
              )}

              <button
                type="submit"
                disabled={loadingMethod !== null}
                className="w-full mt-2 inline-flex items-center justify-center gap-2 py-3 px-4 rounded-xl text-xs font-semibold text-white bg-[#0F0E17] hover:bg-[#232130] active:scale-[0.98] transition-all shadow-xs disabled:opacity-60"
              >
                {loadingMethod === 'email' ? (
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <>
                    <span>
                      {mode === 'signup'
                        ? 'Create Account'
                        : mode === 'forgot'
                        ? 'Send reset email'
                        : mode === 'reset'
                        ? 'Update password'
                        : 'Sign In'}
                    </span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </>
                )}
              </button>
            </form>
          )}

          {/* Bottom Switchers */}
          <div className="pt-3 border-t border-[#E4E2EB] flex flex-col gap-2 text-center text-xs text-[#524E5E]">
            {mode === 'signin' && (
              <p>
                Don&apos;t have an account?{' '}
                <button
                  type="button"
                  onClick={() => {
                    setMode('signup');
                    setErrorMessage('');
                  }}
                  className="font-bold text-[#6344E7] hover:underline"
                >
                  Create an account
                </button>
              </p>
            )}

            {mode === 'signup' && (
              <p>
                Already have an account?{' '}
                <button
                  type="button"
                  onClick={() => {
                    setMode('signin');
                    setErrorMessage('');
                  }}
                  className="font-bold text-[#6344E7] hover:underline"
                >
                  Sign in
                </button>
              </p>
            )}
          </div>

        </div>

      </div>
    </div>
  );
}
