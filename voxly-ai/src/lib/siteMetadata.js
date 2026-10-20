export const SITE_URL = 'https://www.dialtact.com/';

export const PUBLIC_PAGES = {
  landing: {
    title: 'Dialtact — AI Voice Agents for Customer Calls',
    description: 'Create AI voice agents that answer customer calls, handle common requests, and guide callers to the next step for your business.',
  },
  support: {
    title: 'Customer Support & Contact — Dialtact',
    description: 'Contact Dialtact for help with your account, AI voice agents, phone setup, billing, or a support request.',
  },
  company: {
    title: 'About Dialtact — AI Voice Agent Platform',
    description: 'Learn about Dialtact and its voice AI platform for customer support, sales qualification, and other phone workflows.',
  },
  privacy: {
    title: 'Privacy Policy — Dialtact',
    description: 'Read how Dialtact handles account information, call recordings, transcripts, and other personal data.',
  },
  terms: {
    title: 'Terms of Service — Dialtact',
    description: 'Review the terms that govern access to and use of the Dialtact voice AI platform.',
  },
  security: {
    title: 'Security — Dialtact',
    description: 'Learn about Dialtact security practices for accounts, voice traffic, customer data, and call records.',
  },
};

export const PUBLIC_PATHS = { landing: '/', support: '/support', company: '/company', privacy: '/privacy', terms: '/terms', security: '/security' };
const ALIASES = { contact: 'support', about: 'company' };
export function viewFromLocation(location) {
  const hash = (location.hash || '').slice(1);
  if (hash.startsWith('dashboard')) return 'dashboard';
  const aliased = ALIASES[hash] || hash;
  if (PUBLIC_PATHS[aliased]) return aliased;
  const path = (location.pathname || '/').replace(/\/$/, '') || '/';
  return Object.keys(PUBLIC_PATHS).find((view) => PUBLIC_PATHS[view] === path) || 'landing';
}

const CONSOLE_TITLES = {
  overview: 'Workspace Overview — Dialtact Console',
  employees: 'AI Employees — Dialtact Console',
  calls: 'Call Activity — Dialtact Console',
  integrations: 'Integrations — Dialtact Console',
  telephony: 'Phone Numbers — Dialtact Console',
  billing: 'Billing — Dialtact Console',
  campaigns: 'Calling Campaigns — Dialtact Console',
  compliance: 'Compliance — Dialtact Console',
};

function setMeta(attribute, name, content) {
  if (typeof document === 'undefined' || !document.head) return;
  let element = document.head.querySelector(`meta[${attribute}="${name}"]`);
  if (!element) {
    element = document.createElement('meta');
    element.setAttribute(attribute, name);
    document.head.appendChild(element);
  }
  element.setAttribute('content', content);
}

/** Keep the browser title and share metadata in sync with the current app view. */
export function applyPageMetadata(view = 'landing', tab = '') {
  if (typeof document === 'undefined' || !document.head) return;

  const isConsole = view === 'dashboard';
  const page = PUBLIC_PAGES[view] || PUBLIC_PAGES.landing;
  const title = isConsole ? (CONSOLE_TITLES[tab] || 'Workspace — Dialtact Console') : page.title;
  const description = isConsole
    ? 'Sign in to manage your Dialtact workspace.'
    : page.description;

  const canonicalUrl = new URL(PUBLIC_PATHS[view] || "/", SITE_URL).href;
  document.title = title;
  setMeta('name', 'description', description);
  setMeta('property', 'og:title', title);
  setMeta('property', 'og:description', description);
  setMeta('property', 'og:url', canonicalUrl);
  setMeta('name', 'twitter:title', title);
  setMeta('name', 'twitter:description', description);
  setMeta('name', 'twitter:url', canonicalUrl);

  let canonical = document.head.querySelector('link[rel="canonical"]');
  if (!canonical) {
    canonical = document.createElement('link');
    canonical.setAttribute('rel', 'canonical');
    document.head.appendChild(canonical);
  }
  canonical.setAttribute('href', canonicalUrl);

  setMeta('name', 'robots', isConsole ? 'noindex, nofollow' : 'index, follow, max-image-preview:large');
}
