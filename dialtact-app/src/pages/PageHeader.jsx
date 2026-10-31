import React from 'react';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { DEFAULT_CONSOLE_TAB } from '../lib/consoleEntry';

export function PageHeader({ title, subtitle, onBackToLanding, onEnterConsole, onSignIn }) {
  const { isAuthenticated } = useAuth();

  const handleAuthClick = () => {
    if (isAuthenticated) {
      onEnterConsole?.(DEFAULT_CONSOLE_TAB);
    } else if (onSignIn) {
      onSignIn();
    } else {
      onBackToLanding?.();
      onEnterConsole?.(DEFAULT_CONSOLE_TAB);
    }
  };

  return (
    <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-[#E4E2EB] py-3.5 px-6 sm:px-8">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <div className="flex items-center gap-4">
          <a
            href="/"
            onClick={(e) => {
              e.preventDefault();
              onBackToLanding?.();
            }}
            className="flex items-center gap-2.5 group"
          >
            <div className="w-8 h-8 rounded-lg bg-[#0F0E17] flex items-center justify-center shadow-xs group-hover:scale-105 transition-transform">
              <svg
                className="w-4 h-4 text-white"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <line x1="18" y1="20" x2="18" y2="10" />
                <line x1="12" y1="20" x2="12" y2="4" />
                <line x1="6" y1="20" x2="6" y2="14" />
              </svg>
            </div>
            <span className="text-xl font-bold tracking-tight text-[#0F0E17]">
              Dialtact
            </span>
          </a>

          <div className="hidden sm:flex items-center gap-2 pl-4 border-l border-[#E4E2EB]">
            <button
              type="button"
              onClick={onBackToLanding}
              className="text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17] flex items-center gap-1.5 transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Platform</span>
            </button>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onBackToLanding}
            className="text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17] px-3 py-1.5 rounded-lg hover:bg-[#FAF9FD] transition-colors"
          >
            Platform Home
          </button>
          <button
            type="button"
            onClick={handleAuthClick}
            className="px-3.5 py-1.5 rounded-xl bg-[#0F0E17] text-white text-xs font-semibold hover:bg-[#27253D] transition-all flex items-center gap-1.5 shadow-xs"
          >
            <span>{isAuthenticated ? 'Open Console' : 'Sign In'}</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </header>
  );
}

export default PageHeader;
