import React, { useState, useEffect } from 'react';
import {
  Search,
  Bot,
  Phone,
  PhoneCall,
  Users,
  Megaphone,
  CreditCard,
  Calculator,
  Settings,
  Plus,
  ArrowRight,
  Mic,
  Shield,
  Home
} from 'lucide-react';
import { useWorkspace } from './context/WorkspaceContext';
import { useAuth } from '../context/AuthContext';

export function CommandPalette({ isOpen, onClose, onNavigate }) {
  const [query, setQuery] = useState('');
  const { agents, phoneNumbers, leads, isLoading } = useWorkspace();
  const { isPlatformAdmin } = useAuth();

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        onClose();
      }
      if (e.key === 'Escape') {
        onClose();
      }
    };
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const quickActions = [
    { label: 'Go to home', category: 'Navigation', icon: Home, action: () => onNavigate('overview') },
    { label: 'Create an AI employee', category: 'Actions', icon: Plus, action: () => onNavigate('employees', { openCreate: true }) },
    { label: 'Buy a phone number', category: 'Actions', icon: Phone, action: () => onNavigate('phone-numbers', { openBuy: true }) },
    {
      label: 'Test an agent',
      category: 'Actions',
      icon: Mic,
      action: () => onNavigate('employees', { step: 'test' }),
    },
    { label: 'Start a campaign', category: 'Actions', icon: Megaphone, action: () => onNavigate('campaigns', { openCreate: true }) },
    { label: 'Open calls and transcripts', category: 'Navigation', icon: PhoneCall, action: () => onNavigate('calls') },
    { label: 'Open leads', category: 'Navigation', icon: Users, action: () => onNavigate('leads') },
    {
      label: 'Review callbacks and follow-ups',
      category: 'Navigation',
      icon: PhoneCall,
      action: () => {
        try { sessionStorage.setItem('dialtact_leads_area', 'followups'); } catch { /* storage unavailable */ }
        onNavigate('leads');
      },
    },
    { label: 'Add funds and see invoices', category: 'Billing', icon: CreditCard, action: () => onNavigate('billing') },
    { label: 'Estimate monthly cost', category: 'Billing', icon: Calculator, action: () => onNavigate('calculator') },
    { label: 'Workspace settings and API keys', category: 'Settings', icon: Settings, action: () => onNavigate('settings') },
    ...(isPlatformAdmin
      ? [{ label: 'Platform admin', category: 'Admin', icon: Shield, action: () => onNavigate('admin') }]
      : []),
  ];

  const filteredAgents = agents
    .filter((a) => a.name.toLowerCase().includes(query.toLowerCase()) || a.role.toLowerCase().includes(query.toLowerCase()))
    .map((a) => ({
      label: `${a.name} — ${a.role}`,
      category: 'AI employees',
      icon: Bot,
      action: () => onNavigate('employees', { agentId: a.id, step: 'script' }),
    }));

  const filteredNumbers = phoneNumbers
    .filter(
      (n) =>
        (n.number || '').includes(query) ||
        (n.assignedAgentName || '').toLowerCase().includes(query.toLowerCase())
    )
    .map((n) => ({
      label: `${n.number} (${n.assignedAgentName})`,
      category: 'Phone numbers',
      icon: Phone,
      action: () => onNavigate('phone-numbers')
    }));

  const filteredLeads = leads
    .filter(
      (l) =>
        (l.name || '').toLowerCase().includes(query.toLowerCase()) ||
        (l.company || '').toLowerCase().includes(query.toLowerCase())
    )
    .map((l) => ({
      // Only show a stage we actually have. The API does not return a BANT score,
      // so rendering one produced "BANT undefined" for every lead.
      label: `${l.name} — ${l.company} · ${l.stage || 'New'}`,
      category: 'Leads',
      icon: Users,
      action: () => onNavigate('leads', { leadId: l.id })
    }));

  const allResults = query
    ? [...filteredAgents, ...filteredNumbers, ...filteredLeads, ...quickActions.filter((a) => a.label.toLowerCase().includes(query.toLowerCase()))]
    : quickActions;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-6 sm:pt-20 p-3 sm:p-6 overflow-y-auto">
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="fixed inset-0 bg-ink/60 backdrop-blur-sm"
        aria-hidden="true"
      />

      {/* Palette Container */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="relative w-full max-w-xl bg-white border border-line rounded-card shadow-2xl overflow-hidden z-10 animate-in fade-in zoom-in-95 duration-150 my-auto sm:my-0"
      >
        {/* Search Input Bar */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-line">
          <Search className="w-4 h-4 text-fg-body shrink-0" />
          <input
            autoFocus
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search agents, numbers, leads or actions"
            className="flex-1 bg-transparent text-base sm:text-sm min-h-[38px] text-ink placeholder-fg-muted focus:outline-none"
          />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close command palette"
            className="px-2 py-1 rounded text-xs sm:text-meta font-mono bg-canvas text-fg-body border border-line shadow-2xs hover:bg-surface-subtle"
          >
            ESC
          </button>
        </div>

        {/* Results List */}
        <div className="max-h-80 overflow-y-auto p-2 space-y-1">
          {isLoading && query.trim() && allResults.length === 0 ? (
            <div className="p-3 space-y-2 animate-pulse" aria-busy="true" aria-label="Searching workspace">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="flex items-center gap-3 p-2.5 rounded-control bg-canvas">
                  <div className="w-8 h-8 rounded-lg bg-line" />
                  <div className="flex-1 space-y-1.5 min-w-0">
                    <div className="h-3 w-36 bg-line rounded" />
                    <div className="h-2 w-20 bg-line/60 rounded" />
                  </div>
                  <div className="h-4 w-12 bg-line rounded-md" />
                </div>
              ))}
            </div>
          ) : allResults.length === 0 ? (
            <div className="p-8 text-center text-xs text-fg-body">
              Nothing matches “{query}”
            </div>
          ) : (
            allResults.map((item, idx) => {
              const Icon = item.icon;
              return (
                <button
                  key={`${item.label}-${idx}`}
                  onClick={() => {
                    item.action();
                    onClose();
                  }}
                  className="w-full flex items-center justify-between p-2.5 min-h-[44px] rounded-control hover:bg-canvas active:bg-surface-subtle text-left transition-colors group"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded-lg bg-surface-subtle border border-line flex items-center justify-center text-fg-body group-hover:text-ink group-hover:border-line-strong transition-all">
                      <Icon className="w-4 h-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-ink truncate group-hover:text-accent-fg transition-colors">
                        {item.label}
                      </div>
                      <div className="text-meta text-fg-body">{item.category}</div>
                    </div>
                  </div>
                  <ArrowRight className="w-3.5 h-3.5 text-fg-muted group-hover:text-ink opacity-0 group-hover:opacity-100 transition-opacity" />
                </button>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2 bg-canvas border-t border-line flex items-center justify-between text-meta text-fg-body">
          <span>Tab moves between results</span>
          <span>Press Esc to close</span>
        </div>
      </div>
    </div>
  );
}
