import React, { useEffect, useState } from 'react';
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react';

export function showToast(message, variant = 'info', duration = 5000) {
  if (typeof window === 'undefined' || !message) return;
  window.dispatchEvent(
    new CustomEvent('voxly:toast', { detail: { message, variant, duration } })
  );
}

export function ToastHost() {
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    const onToast = (event) => {
      const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const next = { id, ...(event.detail || {}) };
      setToasts((prev) => [...prev.slice(-4), next]);
      const ms = Math.max(2000, Number(next.duration) || 5000);
      window.setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, ms);
    };
    window.addEventListener('voxly:toast', onToast);
    return () => window.removeEventListener('voxly:toast', onToast);
  }, []);

  if (!toasts.length) return null;

  return (
    <div className="fixed z-[200] top-4 right-4 flex flex-col gap-2 max-w-sm w-[min(100%-2rem,24rem)] pointer-events-none">
      {toasts.map((toast) => {
        const Icon =
          toast.variant === 'success' ? CheckCircle2 : toast.variant === 'error' ? AlertCircle : Info;
        const styles =
          toast.variant === 'success'
            ? 'border-emerald-200 bg-white text-emerald-900'
            : toast.variant === 'error'
              ? 'border-red-200 bg-white text-red-900'
              : 'border-[#E4E2EB] bg-white text-[#0F0E17]';
        return (
          <div
            key={toast.id}
            role="status"
            className={`pointer-events-auto flex items-start gap-2 rounded-xl border px-3 py-2.5 shadow-craft-md text-xs ${styles}`}
          >
            <Icon className="w-4 h-4 shrink-0 mt-0.5" />
            <p className="flex-1 leading-relaxed">{toast.message}</p>
            <button
              type="button"
              className="min-w-[28px] min-h-[28px] flex items-center justify-center rounded-lg text-[#8C879A] hover:text-[#0F0E17] hover:bg-[#FAF9FD]"
              onClick={() => setToasts((prev) => prev.filter((t) => t.id !== toast.id))}
              aria-label="Dismiss"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
