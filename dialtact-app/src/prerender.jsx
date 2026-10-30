import React from 'react';
import { renderToString } from 'react-dom/server';
import App from './App';
import { AuthProvider } from './context/AuthContext';
import { SupportPage } from './pages/SupportPage';
import { CompanyPage } from './pages/CompanyPage';
import { PrivacyPage } from './pages/PrivacyPage';
import { TermsPage } from './pages/TermsPage';
import { SecurityPage } from './pages/SecurityPage';
export { PUBLIC_PAGES, PUBLIC_PATHS, SITE_URL } from './lib/siteMetadata';
const pages = { support: SupportPage, company: CompanyPage, privacy: PrivacyPage, terms: TermsPage, security: SecurityPage };
export function render(view) {
  if (view === 'landing') return renderToString(<App />);
  const Page = pages[view];
  return renderToString(<AuthProvider><Page /></AuthProvider>);
}
