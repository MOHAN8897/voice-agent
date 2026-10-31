import React, { useEffect, useState } from 'react';
import { Mail, CheckCircle2, Loader2 } from 'lucide-react';
import { api } from '../services/api';

export function VerifyEmailBanner({ onVerified, onSignIn }) {
  const [status, setStatus] = useState('idle');
  const [message, setMessage] = useState('');

  useEffect(() => {
    const hash = window.location.hash || '';
    if (!hash.includes('verify-email')) return;
    const token = new URLSearchParams(hash.split('?')[1] || '').get('token');
    if (!token) {
      setMessage('This verification link is invalid.');
      setStatus('error');
      return;
    }
    setStatus('working');
    (async () => {
      try {
        await api.auth.verifyEmail(token);
        setStatus('done');
        setMessage('Email verified. You can sign in and open your agent console.');
        window.history.replaceState({}, '', `${window.location.pathname}#`);
        onVerified?.();
      } catch (e) {
        setStatus('error');
        setMessage(e.message || 'Verification failed. Request a new link from sign-in.');
      }
    })();
  }, [onVerified]);

  if (status === 'idle') return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[60] max-w-md w-[calc(100%-2rem)]">
      <div
        className={`rounded-2xl border px-4 py-3 shadow-xl text-sm flex items-start gap-3 ${
          status === 'error'
            ? 'bg-red-50 border-red-200 text-red-800'
            : status === 'done'
            ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
            : 'bg-white border-[#E4E2EB] text-[#0F0E17]'
        }`}
      >
        {status === 'working' ? (
          <Loader2 className="w-5 h-5 animate-spin shrink-0 mt-0.5" />
        ) : status === 'done' ? (
          <CheckCircle2 className="w-5 h-5 shrink-0 mt-0.5" />
        ) : (
          <Mail className="w-5 h-5 shrink-0 mt-0.5" />
        )}
        <div className="flex-1 min-w-0">
          <p>{message || 'Verifying your email…'}</p>
          {status === 'done' && onSignIn && (
            <button
              type="button"
              onClick={onSignIn}
              className="mt-2 text-xs font-bold text-[#6344E7] hover:underline"
            >
              Sign in now
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
