import React, { useState, useEffect, useRef } from 'react';
import {
  X,
  Lock,
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
  Sparkles,
  PhoneCall,
  Database,
  Receipt,
  ShieldCheck,
  AlertCircle,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { analytics } from '../services/analytics';
import { api } from '../services/api';

function BrandGlyph({ className = 'w-4 h-4' }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  );
}

const AUTH_INPUT =
  'h-12 w-full rounded-xl border border-[#E4E2EB] bg-[#FBFAFE] px-3.5 text-base text-[#0F0E17] shadow-[inset_0_1px_2px_rgba(15,14,23,0.03)] transition-[border-color,box-shadow,background-color] duration-200 placeholder:text-[#6F6A7D] focus:border-[#6344E7] focus:bg-white focus:outline-none focus:ring-4 focus:ring-[#6344E7]/10 sm:text-[13.5px]';

const AUTH_PRIMARY =
  'group inline-flex min-h-[48px] w-full items-center justify-center gap-2 rounded-xl bg-[#0F0E17] px-4 text-[13px] font-semibold text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.14),0_12px_28px_-16px_rgba(15,14,23,0.65)] transition-all duration-200 hover:bg-[#1C1A27] hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.18),0_16px_32px_-16px_rgba(15,14,23,0.7)] active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-60';

const MODE_COPY = {
  signin: {
    eyebrow: 'Welcome back',
    title: 'Sign in to your console',
    subtitle: 'Use your work email or Google account to continue.',
  },
  signup: {
    eyebrow: 'New workspace',
    title: 'Create your account',
    subtitle: 'Email, Google, and your console share one Dialtact account.',
  },
  'verify-otp': {
    eyebrow: 'Email verification',
    title: 'Verify your email',
    subtitle: 'Use the same email for password sign-in and Google — one account per email.',
  },
  reset: {
    eyebrow: 'Password reset',
    title: 'Choose a new password',
    subtitle: 'This link signs you in once it is used. Pick a password you have not used before.',
  },
  forgot: {
    eyebrow: 'Password reset',
    title: 'Reset your password',
    subtitle: 'Enter the email on your account and we will send a single-use reset link.',
  },
};

export function AuthModal({ isOpen, onClose, initialMode = 'signin', onAuthSuccess, notice = '' }) {
  const { loginWithGoogle, loginWithEmail, signupWithEmail, refreshSession } = useAuth();

  const [mode, setMode] = useState(initialMode);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [loadingMethod, setLoadingMethod] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const [googleSignInEnabled, setGoogleSignInEnabled] = useState(true);
  const [googleConfigHint, setGoogleConfigHint] = useState('');
  const [showResendVerification, setShowResendVerification] = useState(false);
  const [resendStatus, setResendStatus] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [pendingVerifyEmail, setPendingVerifyEmail] = useState('');
  const [resetDebugUrl, setResetDebugUrl] = useState('');
  const [debugOtp, setDebugOtp] = useState('');
  const dialogRef = useRef(null);

  /**
   * The single-use reset token lives in the URL fragment.
   *
   * Read it when the form is submitted rather than once at mount: the modal is mounted
   * for the life of the app, so a value captured on mount is the hash the visitor
   * arrived with — empty if they opened the reset link later in the same tab, which
   * then failed with "invalid or expired" for a perfectly good link.
   */
  const readResetToken = () =>
    new URLSearchParams((window.location.hash.split('?')[1]) || '').get('token') || '';

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
          setGoogleConfigHint('Google sign-in is not configured for this environment.');
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
    setConfirmPassword('');
    // Opt-in security choice: a fresh open always starts unchecked.
    setRememberMe(false);
  }, [initialMode, isOpen]);

  useEffect(() => {
    if (notice) setErrorMessage(notice);
  }, [notice]);

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

  useEffect(() => {
    if (!isOpen) return;
    const node = dialogRef.current;
    if (!node) return;
    (node.querySelector('[data-autofocus]') || node).focus({ preventScroll: true });

    const handleTab = (e) => {
      if (e.key !== 'Tab') return;
      const items = Array.from(
        node.querySelectorAll(
          'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])'
        )
      ).filter((el) => el.offsetParent !== null);
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    node.addEventListener('keydown', handleTab);
    return () => node.removeEventListener('keydown', handleTab);
  }, [isOpen, mode]);

  if (!isOpen) return null;

  const copy = MODE_COPY[mode] || MODE_COPY.signin;

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
    // Duplicate-submit guard (double-click / Enter while in-flight).
    if (loadingMethod !== null) return;
    setErrorMessage('');

    try {
      let authedUser = null;
      if (mode === 'signup') {
        setLoadingMethod('email');
        const signupRes = await signupWithEmail(name, email, password);
        if (signupRes?.requiresEmailVerification) {
          setPendingVerifyEmail(signupRes.email || email.trim());
          setOtpCode('');
          // Dev deployment with no mail provider: the code comes back in the response,
          // otherwise this step is a dead end with no way forward.
          if (signupRes.debugOtp) {
            setDebugOtp(String(signupRes.debugOtp));
            setOtpCode(String(signupRes.debugOtp));
          }
          setSuccessMessage(signupRes.message || 'Enter the 6-digit code we sent to your email.');
          setMode('verify-otp');
          return;
        }
        authedUser = signupRes;
        analytics.track('auth_signup_success', { userId: authedUser.id });
        setSuccessMessage(`Account created! Welcome to Dialtact, ${authedUser.name}.`);
      } else if (mode === 'forgot') {
        setLoadingMethod('email');
        const res = await api.auth.forgotPassword(email);
        setSuccessMessage(res?.message || 'If an account exists, reset instructions were sent to your email.');
        if (res?.debugResetUrl) {
          // Dev deployment (AUTH_DEBUG_EXPOSE_RESET_TOKEN): no working mail provider,
          // so surface the link instead of leaving the flow unfinishable.
          setResetDebugUrl(res.debugResetUrl);
        }
        setMode('signin');
        return;
      } else if (mode === 'reset') {
        setLoadingMethod('email');
        const token = readResetToken();
        if (!token) throw new Error('Reset link is invalid or expired.');
        if (password !== confirmPassword) {
          throw new Error('The two passwords do not match.');
        }
        // The server signs the user in here — a valid single-use reset token is proof
        // that the mailbox owner asked for this. Retyping the new password on the
        // sign-in form right afterwards was pure friction.
        const data = await api.auth.resetPassword(token, password);
        window.location.hash = '';
        authedUser = await refreshSession();
        analytics.track('auth_password_reset', { userId: authedUser?.id });
        setSuccessMessage(`Password updated. Welcome back, ${authedUser?.name || 'there'}!`);
      } else if (mode === 'signin') {
        setLoadingMethod('email');
        authedUser = await loginWithEmail(email, password, { rememberMe });
        analytics.track('auth_signin_success', {
          userId: authedUser.id,
          rememberMe: Boolean(authedUser.rememberMe),
        });
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

  const handleOtpSubmit = async (e) => {
    e.preventDefault();
    if (loadingMethod !== null) return;
    setErrorMessage('');
    const targetEmail = pendingVerifyEmail || email.trim();
    if (!targetEmail || otpCode.length !== 6) {
      setErrorMessage('Enter the 6-digit code from your email.');
      return;
    }
    try {
      setLoadingMethod('otp');
      await api.auth.verifyEmailOtp(targetEmail, otpCode);
      const authedUser = await refreshSession();
      analytics.track('auth_signup_verified', { userId: authedUser?.id });
      setSuccessMessage(`Welcome to Dialtact, ${authedUser?.name || 'there'}!`);
      setTimeout(() => {
        onClose();
        if (onAuthSuccess) onAuthSuccess(authedUser);
      }, 500);
    } catch (err) {
      setErrorMessage(err.message || 'Invalid or expired code.');
    } finally {
      setLoadingMethod(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto p-3 sm:p-6">
      {/* Backdrop */}
      <div
        className="auth-backdrop fixed inset-0 bg-[#0B0A12]/70 backdrop-blur-[6px]"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal Dialog */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-modal-title"
        aria-describedby="auth-modal-description"
        data-testid="auth-modal"
        tabIndex={-1}
        className="auth-modal auth-dialog relative z-10 my-auto flex max-h-[calc(100dvh-1.5rem)] w-full max-w-[64rem] flex-col overflow-hidden rounded-[22px] border border-white/70 bg-white text-left shadow-[0_48px_120px_-28px_rgba(11,10,18,0.55),0_16px_40px_-24px_rgba(11,10,18,0.35)] outline-none sm:max-h-[calc(100dvh-3rem)] lg:flex-row"
      >
        {/* Brand rail — the same identity as the public website */}
        <aside
          className="relative hidden w-[22rem] shrink-0 flex-col justify-between overflow-hidden bg-[#0B0A12] p-8 text-white lg:flex xl:w-[24rem]"
          aria-label="Dialtact"
        >
          <div
            className="absolute inset-0 opacity-[0.07]"
            style={{
              backgroundImage:
                'linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)',
              backgroundSize: '32px 32px',
              maskImage: 'radial-gradient(120% 90% at 20% 0%, #000 30%, transparent 78%)',
              WebkitMaskImage: 'radial-gradient(120% 90% at 20% 0%, #000 30%, transparent 78%)',
            }}
            aria-hidden
          />
          <div
            className="auth-aurora absolute -right-24 -top-24 h-72 w-72 rounded-full bg-[#6344E7]/30 blur-[90px]"
            aria-hidden
          />
          <div
            className="auth-aurora absolute -bottom-28 -left-20 h-64 w-64 rounded-full bg-[#3B2A8C]/25 blur-[90px] [animation-delay:-6s]"
            aria-hidden
          />

          <div className="auth-stagger relative">
            <div className="flex items-center gap-2.5">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/15 bg-white/[0.07] shadow-[inset_0_1px_0_rgba(255,255,255,0.15)]">
                <BrandGlyph className="h-4 w-4 text-white" />
              </div>
              <div>
                <div className="text-[15px] font-bold tracking-tight">Dialtact</div>
                <div className="font-mono text-[9.5px] uppercase tracking-[0.22em] text-white/50">
                  AI voice employees
                </div>
              </div>
            </div>

            <h2 className="mt-10 text-[2rem] font-semibold leading-[1.12] tracking-[-0.04em] text-white">
              Every call answered.
              <span className="auth-serif mt-1 block text-[2.15rem] font-normal italic leading-[1.05] text-[#C9B8FF]">
                Every lead followed up.
              </span>
            </h2>
            <p className="mt-4 max-w-[18rem] text-[13px] leading-relaxed text-white/55">
              Build agents, run live test calls, and manage usage billing from one console — the same
              place your AI employees are configured.
            </p>

            <ul className="mt-8 space-y-3.5 text-[12.5px] text-white/75">
              {[
                { icon: PhoneCall, label: 'Live voice on real phone lines' },
                { icon: Database, label: 'Business brain trained on your data' },
                { icon: Receipt, label: 'Pay-as-you-go wallet with GST invoices' },
              ].map(({ icon: Icon, label }) => (
                <li key={label} className="flex items-center gap-3">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/[0.08] bg-white/[0.05] text-[#C4B5FD]">
                    <Icon className="h-3.5 w-3.5" />
                  </span>
                  <span>{label}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="relative mt-10 space-y-4">
            <div className="flex items-center justify-between rounded-xl border border-white/[0.08] bg-white/[0.04] px-3.5 py-3">
              <div className="flex items-center gap-2">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#A78BFA] opacity-60" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[#C4B5FD]" />
                </span>
                <span className="font-mono text-[9.5px] uppercase tracking-[0.2em] text-white/60">
                  Live voice engine
                </span>
              </div>
              <div className="flex h-4 items-end gap-[3px]" aria-hidden>
                {[3, 7, 5, 12, 8, 14, 6, 10].map((height, index) => (
                  <span
                    key={index}
                    className="auth-wave w-[3px] rounded-full bg-[#A78BFA]/70"
                    style={{ height: `${height}px`, animationDelay: `${index * 120}ms` }}
                  />
                ))}
              </div>
            </div>
            <p className="flex items-start gap-2 text-[11px] leading-relaxed text-white/50">
              <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-white/55" />
              <span>
                Encrypted sessions that expire automatically. One account for email, Google and the
                console.
              </span>
            </p>
          </div>
        </aside>

        {/* Form column */}
        <div className="relative flex min-h-0 flex-1 flex-col bg-white">
          <div className="flex shrink-0 items-center justify-between px-5 pt-4 sm:px-8 sm:pt-5">
            <div className="flex items-center gap-2 lg:hidden">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#0F0E17] text-white shadow-craft-xs">
                <BrandGlyph />
              </div>
              <span className="text-[15px] font-bold tracking-tight text-[#0F0E17]">Dialtact</span>
            </div>
            <div className="hidden items-center gap-2 font-mono text-[9.5px] uppercase tracking-[0.2em] text-[#8C879A] lg:flex">
              <Lock className="h-3.5 w-3.5 text-[#6344E7]" />
              <span>Secure sign-in</span>
            </div>
            <button
              onClick={onClose}
              className="flex h-11 w-11 items-center justify-center rounded-full border border-transparent text-[#6B6678] transition-all duration-200 hover:border-[#E4E2EB] hover:bg-[#F7F5FC] hover:text-[#0F0E17] active:scale-95 sm:h-9 sm:w-9"
              aria-label="Close dialog"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-6 sm:px-8 sm:pb-8">
            <div key={mode} className="auth-panel-in mx-auto w-full max-w-[23.5rem] pt-4 sm:pt-6">
            <div className="pb-6">
              <p className="flex items-center gap-1.5 font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-[#6344E7]">
                <Sparkles className="h-3 w-3" />
                {copy.eyebrow}
              </p>
              <h3
                id="auth-modal-title"
                className="mt-2.5 text-[27px] font-semibold leading-[1.15] tracking-[-0.035em] text-[#0F0E17]"
              >
                {copy.title}
              </h3>
              <p id="auth-modal-description" className="mt-2 text-[13px] leading-relaxed text-[#5B5768]">
                {copy.subtitle}
              </p>
            </div>

            {/* Alerts: Error & Success */}
            {errorMessage && (
              <div
                role="alert"
                className="mb-4 flex items-start gap-2.5 rounded-xl border border-red-200/80 bg-red-50/80 px-3.5 py-3 text-[12.5px] leading-relaxed text-red-700"
              >
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
                <span>{errorMessage}</span>
              </div>
            )}

            {successMessage && (
              <div
                role="status"
                className="mb-4 flex items-center gap-2.5 rounded-xl border border-emerald-200/80 bg-emerald-50/80 px-3.5 py-3 text-[12.5px] font-medium text-emerald-800"
              >
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
                <span>{successMessage}</span>
              </div>
            )}

            {resetDebugUrl && (
              <div className="mb-4 space-y-2 rounded-xl border border-amber-200/80 bg-amber-50/70 px-3.5 py-3 text-[12px] text-amber-900">
                <p className="font-semibold">Development mode: email delivery is not configured.</p>
                <p className="text-[11px] leading-relaxed text-amber-800">
                  The server returned the reset link directly instead of mailing it.
                </p>
                <a
                  href={resetDebugUrl}
                  data-testid="auth-debug-reset-link"
                  className="block break-all font-mono text-[11px] underline"
                >
                  {resetDebugUrl}
                </a>
              </div>
            )}

            {showResendVerification && email && (
              <div className="mb-4 space-y-2 rounded-xl border border-amber-200/80 bg-amber-50/70 px-3.5 py-3 text-[12px] text-amber-900">
                <p>Your account is not verified yet.</p>
                <button
                  type="button"
                  disabled={loadingMethod !== null}
                  onClick={async () => {
                    setResendStatus('');
                    try {
                      await api.auth.resendVerification(email.trim());
                      setResendStatus('If this email is registered, we sent a new verification code.');
                    } catch (e) {
                      setResendStatus(e.message || 'Could not resend.');
                    }
                  }}
                  className="font-semibold text-[#6344E7] underline-offset-2 hover:underline"
                >
                  Resend verification email
                </button>
                {resendStatus && <p className="text-[#524E5E]">{resendStatus}</p>}
              </div>
            )}

          {/* Social Sign-in Buttons (shown in standard signin/signup modes) */}
          {mode === 'verify-otp' && (
            <form onSubmit={handleOtpSubmit} className="space-y-4">
              <p className="text-[12.5px] leading-relaxed text-[#5B5768]">
                Code sent to{' '}
                <strong className="font-semibold text-[#0F0E17]">{pendingVerifyEmail || email}</strong>
              </p>
              <div>
                <label htmlFor="voxly-auth-otp" className="mb-1.5 block text-[12px] font-semibold text-[#3F3B4D]">
                  6-digit code
                </label>
                <input
                  id="voxly-auth-otp"
                  data-autofocus
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  pattern="[0-9]{6}"
                  required
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  className={`${AUTH_INPUT} h-14 text-center font-mono text-xl tracking-[0.45em]`}
                />
              </div>
              {debugOtp && (
                <div
                  data-testid="auth-debug-otp"
                  className="space-y-1 rounded-xl border border-amber-200/80 bg-amber-50/70 px-3.5 py-3 text-[12px] text-amber-900"
                >
                  <p className="font-semibold">Development mode: email delivery is not configured.</p>
                  <p className="text-[11px] leading-relaxed text-amber-800">
                    The server returned the code directly instead of mailing it.
                  </p>
                  <p className="font-mono text-sm tracking-[0.3em]">{debugOtp}</p>
                </div>
              )}
              <button
                type="submit"
                disabled={loadingMethod !== null || otpCode.length !== 6}
                className={AUTH_PRIMARY}
              >
                {loadingMethod === 'otp' ? (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                ) : (
                  <>
                    <span>Verify & continue</span>
                    <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
                  </>
                )}
              </button>
              <div className="flex items-center justify-between text-[12px]">
                <button
                  type="button"
                  className="font-semibold text-[#6344E7] underline-offset-2 hover:underline"
                  onClick={async () => {
                    try {
                      const res = await api.auth.resendVerification(pendingVerifyEmail || email);
                      if (res?.debugOtp) {
                        setDebugOtp(String(res.debugOtp));
                        setOtpCode(String(res.debugOtp));
                      }
                      setResendStatus('New code sent if the account exists.');
                    } catch (err) {
                      setResendStatus(err.message);
                    }
                  }}
                >
                  Resend code
                </button>
                <button
                  type="button"
                  onClick={() => setMode('signin')}
                  className="text-[#5B5768] transition-colors hover:text-[#0F0E17]"
                >
                  Back to sign in
                </button>
              </div>
              {resendStatus && <p className="text-[11px] text-[#5B5768]">{resendStatus}</p>}
            </form>
          )}

          {(mode === 'signin' || mode === 'signup') && (
            <div className="space-y-3">
              {/* Google OAuth Button */}
              {googleConfigHint && (
                <p className="rounded-lg border border-amber-200/70 bg-amber-50/70 px-3 py-2 text-[11px] leading-relaxed text-amber-800">
                  {googleConfigHint}
                </p>
              )}
              <button
                type="button"
                onClick={handleGoogleSignIn}
                disabled={loadingMethod !== null || !googleSignInEnabled}
                title={!googleSignInEnabled ? googleConfigHint : undefined}
                className="flex min-h-[48px] w-full items-center justify-center gap-3 rounded-xl border border-[#E4E2EB] bg-white px-4 text-[13px] font-semibold text-[#0F0E17] shadow-craft-xs transition-all duration-200 hover:-translate-y-px hover:border-[#D6D0E4] hover:bg-[#FBFAFE] hover:shadow-craft-sm active:translate-y-0 active:scale-[0.99] disabled:pointer-events-none disabled:opacity-60"
              >
                {loadingMethod === 'google' ? (
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-[#E4E2EB] border-t-[#0F0E17]" />
                ) : (
                  <svg className="h-[18px] w-[18px]" viewBox="0 0 24 24" aria-hidden="true">
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
              <div className="flex items-center gap-3 py-1.5" aria-hidden="true">
                <span className="h-px flex-1 bg-[#EFEDF4]" />
                <span className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-[#6F6A7D]">
                  or continue with work email
                </span>
                <span className="h-px flex-1 bg-[#EFEDF4]" />
              </div>
            </div>
          )}

          {/* Email / Password Form */}
          {(mode === 'signin' || mode === 'signup' || mode === 'forgot' || mode === 'reset') && (
            <form onSubmit={handleEmailSubmit} className="space-y-4">
              {mode === 'signup' && (
                <div>
                  <label htmlFor="voxly-auth-name" className="mb-1.5 block text-[12px] font-semibold text-[#3F3B4D]">
                    Full name
                  </label>
                  <input
                    id="voxly-auth-name"
                    data-autofocus
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Sarah Connor"
                    autoComplete="name"
                    className={AUTH_INPUT}
                  />
                </div>
              )}

              {mode !== 'reset' && (
                <div>
                  <label htmlFor="voxly-auth-email" className="mb-1.5 block text-[12px] font-semibold text-[#3F3B4D]">
                    Work email
                  </label>
                  <input
                    id="voxly-auth-email"
                    data-autofocus={mode === 'signin' || mode === 'forgot' ? true : undefined}
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="alex@company.com"
                    autoComplete="username"
                    className={AUTH_INPUT}
                  />
                </div>
              )}

              {mode !== 'forgot' && (
                <div>
                  <div className="mb-1.5 flex items-center justify-between">
                    <label htmlFor="voxly-auth-password" className="block text-[12px] font-semibold text-[#3F3B4D]">
                      {mode === 'reset' ? 'New password' : 'Password'}
                    </label>
                    {mode === 'signin' && (
                      <button
                        type="button"
                        onClick={() => setMode('forgot')}
                        className="text-[11.5px] font-medium text-[#6344E7] underline-offset-2 transition-colors hover:text-[#5234D4] hover:underline"
                      >
                        Forgot password?
                      </button>
                    )}
                  </div>
                  <div className="relative">
                    <input
                      id="voxly-auth-password"
                      data-autofocus={mode === 'reset' ? true : undefined}
                      type={showPassword ? 'text' : 'password'}
                      required
                      minLength={mode === 'reset' ? 8 : undefined}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Enter your password"
                      autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                      className={`${AUTH_INPUT} pr-12`}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                      className="absolute right-1.5 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-lg text-[#6B6678] transition-colors hover:bg-[#F0EEF6] hover:text-[#0F0E17] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6344E7]/30"
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                  {mode === 'reset' && (
                    <p className="mt-1.5 text-[11px] text-[#6B6678]">At least 8 characters.</p>
                  )}
                </div>
              )}

              {mode === 'signin' && (
                <label
                  htmlFor="voxly-auth-remember"
                  className="flex w-fit cursor-pointer items-center gap-2 text-[12px] text-[#3F3B4D]"
                >
                  <input
                    id="voxly-auth-remember"
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                    data-testid="auth-remember-me"
                    className="h-4 w-4 shrink-0 cursor-pointer rounded border-[#C9C5D4] accent-[#6344E7] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6344E7]/30 focus-visible:ring-offset-1"
                  />
                  <span>Keep me signed in</span>
                </label>
              )}

              {mode === 'reset' && (
                <div>
                  <label htmlFor="voxly-auth-confirm" className="mb-1.5 block text-[12px] font-semibold text-[#3F3B4D]">
                    Confirm new password
                  </label>
                  <input
                    id="voxly-auth-confirm"
                    type={showPassword ? 'text' : 'password'}
                    required
                    minLength={8}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Repeat your new password"
                    autoComplete="new-password"
                    data-testid="auth-reset-confirm"
                    className={AUTH_INPUT}
                  />
                </div>
              )}

              <button
                type="submit"
                disabled={loadingMethod !== null}
                className={`${AUTH_PRIMARY} mt-1.5`}
              >
                {loadingMethod === 'email' ? (
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                ) : (
                  <>
                    <span>
                      {mode === 'signup'
                        ? 'Create account'
                        : mode === 'forgot'
                          ? 'Send reset email'
                          : mode === 'reset'
                            ? 'Update password'
                            : 'Sign in'}
                    </span>
                    <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
                  </>
                )}
              </button>
            </form>
          )}

          {/* Bottom Switchers */}
          {(mode === 'signin' || mode === 'signup' || mode === 'forgot' || mode === 'reset') && (
            <div className="mt-5 flex items-center justify-between gap-3 border-t border-[#EFEDF4] pt-4 text-[12.5px] text-[#5B5768]">
              {mode === 'signin' && (
                <>
                  <span>New to Dialtact?</span>
                  <button
                    type="button"
                    onClick={() => {
                      setMode('signup');
                      setErrorMessage('');
                    }}
                    className="font-semibold text-[#6344E7] underline-offset-2 transition-colors hover:text-[#5234D4] hover:underline"
                  >
                    Create an account
                  </button>
                </>
              )}

              {mode === 'signup' && (
                <>
                  <span>Already have an account?</span>
                  <button
                    type="button"
                    onClick={() => {
                      setMode('signin');
                      setErrorMessage('');
                    }}
                    className="font-semibold text-[#6344E7] underline-offset-2 transition-colors hover:text-[#5234D4] hover:underline"
                  >
                    Sign in
                  </button>
                </>
              )}

              {(mode === 'forgot' || mode === 'reset') && (
                <>
                  <span>Remembered your password?</span>
                  <button
                    type="button"
                    onClick={() => {
                      setMode('signin');
                      setErrorMessage('');
                    }}
                    className="font-semibold text-[#6344E7] underline-offset-2 transition-colors hover:text-[#5234D4] hover:underline"
                  >
                    Back to sign in
                  </button>
                </>
              )}
            </div>
          )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
