import React, { useEffect, useRef, useState } from 'react';
import { Clock, LogOut } from 'lucide-react';

/**
 * Countdown shown before an inactivity sign-out.
 *
 * Industry practice is a 2-minute warning with an explicit "stay signed in": the
 * person walking away is not a threat to detect, they are someone about to be
 * logged out, and telling them first is the difference between a prompt and a
 * surprise. Focus is trapped here so the countdown is not dismissed by accident,
 * and Escape is deliberately ignored — there is always a visible button.
 */
export function IdleWarningModal({ isOpen, remainingMs = 0, onStay, onSignOut, email = '' }) {
  const [seconds, setSeconds] = useState(() => Math.max(0, Math.ceil(remainingMs / 1000)));
  const stayRef = useRef(null);

  useEffect(() => {
    if (!isOpen) return undefined;
    setSeconds(Math.max(0, Math.ceil(remainingMs / 1000)));
    stayRef.current?.focus();
  }, [isOpen, remainingMs]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const timer = setInterval(() => {
      setSeconds((s) => (s > 0 ? s - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const onKeyDown = (e) => {
      if (e.key === 'Tab') {
        // Two focusable controls — keep the keyboard inside the dialog.
        const focusables = [stayRef.current, document.getElementById('voxly-idle-signout')].filter(
          Boolean
        );
        if (!focusables.length) return;
        const idx = focusables.indexOf(document.activeElement);
        const next = e.shiftKey ? (idx <= 0 ? focusables.length - 1 : idx - 1) : (idx + 1) % focusables.length;
        e.preventDefault();
        focusables[next]?.focus();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen]);

  if (!isOpen) return null;

  const total = 120;
  const pct = Math.max(0, Math.min(100, (seconds / total) * 100));

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="voxly-idle-title"
      aria-describedby="voxly-idle-desc"
      data-testid="idle-warning-modal"
    >
      <div className="absolute inset-0 bg-[#0F0E17]/70 backdrop-blur-sm" aria-hidden="true" />
      <div className="relative w-full max-w-sm bg-white rounded-2xl border border-[#E4E2EB] shadow-2xl overflow-hidden">
        <div className="px-6 pt-6 pb-4 flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-50 border border-amber-200 flex items-center justify-center shrink-0">
            <Clock className="w-5 h-5 text-amber-600" />
          </div>
          <div>
            <h3 id="voxly-idle-title" className="text-base font-extrabold text-[#0F0E17] tracking-tight">
              Still there?
            </h3>
            <p id="voxly-idle-desc" className="text-xs text-[#524E5E] mt-1 leading-relaxed">
              You have been idle. To protect customer call data and lead records, this session signs out
              automatically in
              <span className="font-semibold text-[#0F0E17]"> {seconds} second{seconds === 1 ? '' : 's'}</span>.
            </p>
          </div>
        </div>

        <div className="px-6">
          <div className="h-1.5 w-full rounded-full bg-[#F0EEF6] overflow-hidden">
            <div
              className="h-full rounded-full bg-amber-500 transition-[width] duration-1000 ease-linear"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>

        <div className="px-6 py-5 flex flex-col gap-2">
          <button
            ref={stayRef}
            type="button"
            data-testid="idle-stay-signed-in"
            onClick={onStay}
            className="w-full inline-flex items-center justify-center gap-2 py-3 px-4 rounded-xl text-xs font-semibold text-white bg-[#0F0E17] hover:bg-[#232130] active:scale-[0.98] transition-all"
          >
            Stay signed in
          </button>
          <button
            id="voxly-idle-signout"
            type="button"
            data-testid="idle-sign-out"
            onClick={onSignOut}
            className="w-full inline-flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD] transition-colors"
          >
            <LogOut className="w-3.5 h-3.5" />
            Sign out now{email ? ` (${email})` : ''}
          </button>
        </div>
      </div>
    </div>
  );
}

export default IdleWarningModal;