import React, { useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';

/**
 * Accessible Modal Wrapper
 * Clean high-craft white surface with subtle backdrop-blur and keyboard escape handling.
 */
export function Modal({
  isOpen,
  onClose,
  title,
  subtitle = null,
  children,
  maxWidth = 'max-w-2xl',
  className = '',
  headerless = false,
  panelClassName = '',
}) {
  const panel = useRef(null);
  const close = useRef(onClose);
  close.current = onClose;
  const titleId = useId();
  useEffect(() => {
    if (!isOpen) return;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const focusable = () => [...(panel.current?.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], summary, [tabindex="0"]') || [])].filter((node) => node.getClientRects().length);
    const frame = requestAnimationFrame(() => (focusable()[0] || panel.current)?.focus());
    function onKey(event) {
      if (event.key === 'Escape') { event.stopPropagation(); close.current?.(); }
      if (event.key === 'Tab') {
        const nodes = focusable();
        const first = nodes[0], last = nodes[nodes.length - 1];
        if (!first) { event.preventDefault(); panel.current?.focus(); }
        else if (event.shiftKey && (document.activeElement === first || !panel.current?.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || !panel.current?.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
      }
    }
    document.addEventListener('keydown', onKey);
    return () => {
      cancelAnimationFrame(frame);
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', onKey);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
      {/* Dark backdrop overlay */}
      <div
        onClick={onClose}
        className="fixed inset-0 bg-[#0F0E17]/60 backdrop-blur-sm transition-opacity"
        aria-hidden="true"
      />

      {/* Modal Dialog Card */}
      <div
        ref={panel}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={headerless ? undefined : titleId}
        className={`relative w-full ${maxWidth} bg-white border border-[#E4E2EB] rounded-2xl shadow-2xl z-10 overflow-hidden my-auto max-h-[calc(100dvh-2rem)] flex flex-col ${panelClassName} ${className}`}
      >
        {!headerless && (
          <div className="flex items-start justify-between gap-4 p-5 sm:p-6 border-b border-[#E4E2EB] shrink-0">
            <div>
              <h2 id={titleId} className="text-base sm:text-lg font-bold text-[#0F0E17] tracking-tight">
                {title}
              </h2>
              {subtitle && (
                <p className="text-xs text-[#524E5E] mt-1">{subtitle}</p>
              )}
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close dialog"
              className="min-w-[44px] min-h-[44px] flex items-center justify-center p-2.5 rounded-xl text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD] border border-transparent hover:border-[#E4E2EB] transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        <div className={`${headerless ? 'p-0' : 'p-5 sm:p-6'} flex-1 min-h-0 overflow-y-auto overscroll-contain`}>
          {children}
        </div>
      </div>
    </div>
  );
}
