import React, { useEffect, useState } from 'react';
import { AudioLines } from 'lucide-react';
import { api } from '../services/api';
import '../styles/landing.css';

const GROUPS = [
  ['Product', [['How it works', '#how-it-works'], ['Use cases', '#industries'], ['Pricing', '#pricing'], ['Your workspace', '#dashboard/overview']]],
  ['Company', [['About Dialtact', '/company'], ['Contact & support', '/support']]],
  ['Resources', [['Common questions', '#faq'], ['Security', '/security'], ['Privacy', '/privacy'], ['Terms', '/terms']]],
];
const SOCIAL_LABELS = { twitter: 'X', linkedin: 'LinkedIn', youtube: 'YouTube', github: 'GitHub', discord: 'Discord' };

export function Footer({ onNavigatePage }) {
  const [socialLinks, setSocialLinks] = useState({});
  useEffect(() => {
    let active = true;
    api.support.getConfig().then(config => { if (active) setSocialLinks(config?.socialLinks || {}); }).catch(() => {});
    return () => { active = false; };
  }, []);
  const navigate = target => event => {
    if (!onNavigatePage) return;
    event.preventDefault();
    onNavigatePage(target.replace(/^[/#]/, ''));
  };

  return <footer className="marketing-footer">
    <div className="marketing-footer-inner">
      <div className="marketing-footer-main">
        <div><a className="marketing-footer-brand" href="/" onClick={navigate('')}><AudioLines aria-hidden="true" />Dialtact</a><p>Useful conversations.<br />Clear next steps.<br />An AI voice agent for your business.</p>
          <div className="marketing-footer-socials" data-testid="footer-social-links">{Object.entries(SOCIAL_LABELS).filter(([key]) => /^https?:\/\//i.test(socialLinks[key] || '')).map(([key, label]) => <a key={key} href={socialLinks[key]} target="_blank" rel="noopener noreferrer" aria-label={`Dialtact on ${label}`}>{label}</a>)}</div>
        </div>
        {GROUPS.map(([title, links]) => <div key={title}><h2>{title}</h2><ul>{links.map(([label, href]) => <li key={href}><a href={href} onClick={navigate(href)}>{label}</a></li>)}</ul></div>)}
      </div>
      <div className="marketing-footer-bottom"><span>© {new Date().getFullYear()} Dialtact. All rights reserved.</span><span>Built for the way your business talks.</span></div>
    </div>
  </footer>;
}

export default Footer;
