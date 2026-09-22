import React, { useState, useEffect, useRef } from 'react';
import { NAV_LINKS } from '../data/siteContent';
import { ChevronDown, Menu, X, ArrowRight, LogOut, Settings, LayoutDashboard, ShieldCheck } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { DEFAULT_CONSOLE_TAB } from '../lib/consoleEntry';

export function Navbar({ onEnterConsole, onWatchDemo }) {
  const { user, isAuthenticated, logout } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [activeDropdown, setActiveDropdown] = useState(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef(null);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target)) {
        setUserMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const buildAgent = () => onEnterConsole?.(DEFAULT_CONSOLE_TAB);

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

        <nav className="hidden md:flex items-center gap-7">
          {NAV_LINKS.map((link) => (
            <div
              key={link.name}
              className="relative"
              onMouseEnter={() => link.dropdown && setActiveDropdown(link.name)}
              onMouseLeave={() => setActiveDropdown(null)}
            >
              <a
                href={link.href}
                className="flex items-center gap-1.5 text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17] transition-colors py-2"
              >
                {link.name}
                {link.dropdown && (
                  <ChevronDown
                    className={`w-3.5 h-3.5 transition-transform duration-200 ${
                      activeDropdown === link.name ? 'rotate-180 text-[#0F0E17]' : 'text-[#524E5E]'
                    }`}
                  />
                )}
              </a>
              {link.dropdown && activeDropdown === link.name && (
                <div className="absolute top-full left-1/2 -translate-x-1/2 pt-2 w-72 z-50">
                  <div className="bg-white rounded-xl p-2.5 shadow-xl border border-[#E4E2EB] space-y-1">
                    {link.dropdown.map((subItem) => (
                      <a
                        key={subItem.title}
                        href={subItem.href}
                        className="block p-2.5 rounded-lg hover:bg-[#FAF9FD] transition-colors group"
                      >
                        <div className="text-xs font-semibold text-[#0F0E17] group-hover:text-[#6344E7] transition-colors">
                          {subItem.title}
                        </div>
                        <div className="text-[11px] text-[#524E5E] mt-0.5">{subItem.desc}</div>
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </nav>

        <div className="hidden md:flex items-center gap-3">
          {isAuthenticated && user ? (
            <div className="relative" ref={userMenuRef}>
              <button
                type="button"
                onClick={() => setUserMenuOpen(!userMenuOpen)}
                className="flex items-center gap-2 py-1.5 pl-2 pr-3 rounded-xl bg-white hover:bg-[#FAF9FD] border border-[#E4E2EB] shadow-xs active:scale-[0.98] transition-all"
              >
                <div className="w-6 h-6 rounded-lg bg-[#0F0E17] text-white flex items-center justify-center text-[10px] font-mono font-bold">
                  {user.name.charAt(0).toUpperCase()}
                </div>
                <span className="text-xs font-semibold text-[#0F0E17] max-w-[120px] truncate">{user.name}</span>
                <ChevronDown className={`w-3 h-3 text-[#524E5E] transition-transform ${userMenuOpen ? 'rotate-180' : ''}`} />
              </button>
              {userMenuOpen && (
                <div className="absolute right-0 top-full mt-2 w-64 bg-white rounded-2xl border border-[#E4E2EB] shadow-xl p-3 z-50">
                  <div className="pb-3 border-b border-[#E4E2EB] mb-2 px-1">
                    <div className="text-xs font-bold text-[#0F0E17] truncate">{user.name}</div>
                    <div className="text-[11px] text-[#524E5E] truncate">{user.email}</div>
                  </div>
                  <div className="space-y-1 text-xs font-medium">
                    <button
                      type="button"
                      onClick={() => {
                        setUserMenuOpen(false);
                        onEnterConsole?.('employees');
                      }}
                      className="w-full flex items-center gap-2.5 p-2 rounded-lg hover:bg-[#FAF9FD] text-left"
                    >
                      <LayoutDashboard className="w-3.5 h-3.5 text-[#524E5E]" />
                      Agent builder
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setUserMenuOpen(false);
                        onEnterConsole?.('billing');
                      }}
                      className="w-full flex items-center gap-2.5 p-2 rounded-lg hover:bg-[#FAF9FD] text-left"
                    >
                      <ShieldCheck className="w-3.5 h-3.5 text-[#524E5E]" />
                      Billing
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setUserMenuOpen(false);
                        onEnterConsole?.('settings');
                      }}
                      className="w-full flex items-center gap-2.5 p-2 rounded-lg hover:bg-[#FAF9FD] text-left"
                    >
                      <Settings className="w-3.5 h-3.5 text-[#524E5E]" />
                      Settings
                    </button>
                  </div>
                  <div className="pt-2 mt-2 border-t border-[#E4E2EB]">
                    <button
                      type="button"
                      onClick={() => {
                        setUserMenuOpen(false);
                        logout();
                      }}
                      className="w-full flex items-center gap-2.5 p-2 rounded-lg hover:bg-red-50 text-red-600 text-xs font-semibold"
                    >
                      <LogOut className="w-3.5 h-3.5" />
                      Sign out
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : null}

          <button
            type="button"
            onClick={buildAgent}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold text-white bg-[#0F0E17] hover:bg-[#232130] active:scale-[0.98] transition-all shadow-xs"
          >
            <span>{isAuthenticated ? 'Open console' : 'Build your agent'}</span>
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
              <div key={link.name}>
                <a
                  href={link.href}
                  onClick={() => setMobileMenuOpen(false)}
                  className="block py-2 text-sm font-semibold text-[#0F0E17]"
                >
                  {link.name}
                </a>
              </div>
            ))}
          </div>
          <div className="pt-3 border-t border-[#E4E2EB] flex flex-col gap-2.5">
            {isAuthenticated && user ? (
              <button
                type="button"
                onClick={() => {
                  setMobileMenuOpen(false);
                  logout();
                }}
                className="w-full py-2.5 text-xs font-semibold text-red-600 rounded-xl border border-red-200"
              >
                Sign out ({user.name})
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => {
                setMobileMenuOpen(false);
                buildAgent();
              }}
              className="w-full py-3 rounded-xl text-xs font-semibold text-white bg-[#0F0E17] text-center"
            >
              {isAuthenticated ? 'Open console' : 'Build your agent — sign in'}
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
