import React, { useEffect } from 'react';
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
  className = ''
}) {
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.body.style.overflow = 'unset';
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

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
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        className={`relative w-full ${maxWidth} bg-white border border-[#E4E2EB] rounded-2xl shadow-2xl z-10 overflow-hidden my-auto ${className}`}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-4 p-5 sm:p-6 border-b border-[#E4E2EB]">
          <div>
            <h2 id="modal-title" className="text-base sm:text-lg font-bold text-[#0F0E17] tracking-tight">
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
            className="min-w-[40px] min-h-[40px] flex items-center justify-center p-2 rounded-xl text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD] border border-transparent hover:border-[#E4E2EB] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body Content */}
        <div className="p-5 sm:p-6 max-h-[calc(85vh-120px)] overflow-y-auto">
          {children}
        </div>
      </div>
    </div>
  );
}
