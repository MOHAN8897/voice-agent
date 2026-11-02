import React, { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowRight, AudioLines, Menu, X } from 'lucide-react';
import { MARKETING_NAV_LINKS as NAV_LINKS } from '../data/siteContent';
import { useAuth } from '../context/AuthContext';
import { DEFAULT_CONSOLE_TAB } from '../lib/consoleEntry';

const sectionId = (href) => href.replace(/^\/?#/, '');

export function MarketingNav({ onNavigatePage, onSignIn, onEnterConsole }) {
  const { isAuthenticated } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState('');
  const [hovered, setHovered] = useState('');

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  // Scroll-spy: mark the nav link whose section is under the middle of the viewport.
  useEffect(() => {
    const ids = NAV_LINKS.map((link) => sectionId(link.href));
    const observer = new IntersectionObserver(
      (entries) => entries.forEach((entry) => entry.isIntersecting && setCurrent(entry.target.id)),
      { rootMargin: '-50% 0px -50% 0px' }
    );
    ids.forEach((id) => { const el = document.getElementById(id); if (el) observer.observe(el); });
    return () => observer.disconnect();
  }, []);

  const go = (href) => (event) => {
    event.preventDefault();
    setOpen(false);
    onNavigatePage?.(sectionId(href));
  };

  // One account button: "Log in" signed out, "Open console" signed in. Either way the
  // console is where it ends up.
  const account = () => {
    setOpen(false);
    if (isAuthenticated) onEnterConsole?.(DEFAULT_CONSOLE_TAB);
    else onSignIn?.();
  };

  return (
    <header className={`mk-nav${scrolled ? ' is-scrolled' : ''}`}>
      <div className="mk-container mk-nav-inner">
        <a href="/" className="mk-brand" aria-label="Dialtact home" onClick={go('/')}>
          <span className="mk-brand-mark"><AudioLines size={17} aria-hidden="true" /></span>
          Dialtact
        </a>

        <nav className="mk-nav-links" aria-label="Primary" onMouseLeave={() => setHovered('')}>
          {NAV_LINKS.map((link) => {
            const id = sectionId(link.href);
            return (
              <a key={link.name} href={link.href} onClick={go(link.href)} onMouseEnter={() => setHovered(id)}
                aria-current={current === id ? 'true' : undefined}>
                {(hovered || current) === id && (
                  <motion.span layoutId="mk-nav-pill" className="mk-nav-pill" transition={{ type: 'spring', stiffness: 400, damping: 34 }} />
                )}
                {link.name}
              </a>
            );
          })}
        </nav>

        <div className="mk-nav-actions">
          <button type="button" className="mk-btn mk-btn-primary" onClick={account}>
            {isAuthenticated ? 'Open console' : 'Log in'} <ArrowRight size={15} aria-hidden="true" />
          </button>
        </div>

        <button type="button" className="mk-menu-btn" aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open}
          aria-controls="mk-mobile-menu" onClick={() => setOpen((value) => !value)}>
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div id="mk-mobile-menu" className="mk-mobile-menu" initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.25 }}>
            {NAV_LINKS.map((link) => <a key={link.name} href={link.href} onClick={go(link.href)} data-testid="mobile-nav-link">{link.name}</a>)}
            <button type="button" className="mk-btn mk-btn-primary" data-testid="mobile-console-btn" onClick={account}>
              {isAuthenticated ? 'Open console' : 'Log in'} <ArrowRight size={15} aria-hidden="true" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
