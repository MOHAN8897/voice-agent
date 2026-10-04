import React, { useState, useEffect } from 'react';
import { NAV_LINKS } from '../data/siteContent';
import { Menu, X, ArrowRight } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { DEFAULT_CONSOLE_TAB } from '../lib/consoleEntry';

export function Navbar({ onEnterConsole, onWatchDemo, onOpenTour }) {
  const { isAuthenticated } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const openConsole = () => onEnterConsole?.(DEFAULT_CONSOLE_TAB);

  return (
    <header
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-200 ${
        scrolled
          ? 'py-3 bg-white/95 backdrop-blur-md shadow-[0_1px_3px_rgba(0,0,0,0.05)] border-b border-[#E4E2EB]'
          : 'py-5 bg-transparent'
      }`}
    >
      <div className="max-w-7xl mx-auto px-6 sm:px-8 flex items-center justify-between">
        <a
          href="#"
          onClick={(e) => {
            e.preventDefault();
            window.location.hash = '';
            window.scrollTo({ top: 0, behavior: 'smooth' });
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
          <span className="text-xl font-bold tracking-tight text-[#0F0E17]">Voxly</span>
        </a>

        <nav className="hidden md:flex items-center gap-8">
          {NAV_LINKS.map((link) => (
            <a
              key={link.name}
              href={link.href}
              className="text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17] transition-colors"
            >
              {link.name}
            </a>
          ))}
        </nav>

        <div className="hidden md:flex items-center gap-2.5">

          <button
            type="button"
            onClick={openConsole}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-[#0F0E17] hover:bg-[#232130] active:scale-[0.98] transition-all shadow-xs"
          >
            <span>{isAuthenticated ? 'Open console' : 'Sign in to console'}</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <button
          type="button"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="md:hidden min-w-[44px] min-h-[44px] p-2.5 rounded-xl text-[#0F0E17] hover:bg-[#FAF9FD] border border-[#E4E2EB] flex items-center justify-center"
          aria-label="Toggle navigation"
        >
          {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {mobileMenuOpen && (
        <div className="md:hidden bg-white border-b border-[#E4E2EB] px-6 py-5 space-y-4 shadow-xl">
          <div className="space-y-1">
            {NAV_LINKS.map((link) => (
              <a
                key={link.name}
                href={link.href}
                onClick={() => setMobileMenuOpen(false)}
                className="block py-2 text-sm font-semibold text-[#0F0E17]"
              >
                {link.name}
              </a>
            ))}
          </div>
          <div className="pt-3 border-t border-[#E4E2EB] flex flex-col gap-2.5">
            <button
              type="button"
              onClick={() => {
                setMobileMenuOpen(false);
                openConsole();
              }}
              className="w-full py-3 rounded-xl text-xs font-semibold text-white bg-[#0F0E17] text-center"
            >
              {isAuthenticated ? 'Open console' : 'Sign in to console'}
            </button>
            <button
              type="button"
              onClick={() => {
                setMobileMenuOpen(false);
                onWatchDemo?.();
              }}
              className="w-full py-2.5 text-xs font-semibold text-[#524E5E] rounded-xl border border-[#E4E2EB]"
            >
              Watch demo
            </button>
          </div>
        </div>
      )}
    </header>
  );
}
