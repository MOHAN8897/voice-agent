import React, { useState, useEffect, useRef } from 'react';
import {
  Search,
  Plus,
  Phone,
  Radio,
  Menu,
  ChevronDown,
  Settings,
  CreditCard,
  LogOut,
  ExternalLink,
  Compass,
} from 'lucide-react';
import { TactileButton } from './ui/TactileButton';
import { TopbarBalanceSkeleton } from './ui/Skeleton';
import { useWorkspace } from './context/WorkspaceContext';
import { walletAmounts } from '../lib/money';

const EMPLOYEE_STEP_LABELS = {
  overview: 'Overview',
  script: 'Script',
  calls: 'Calls',
  voice: 'Voice',
  settings: 'Settings',
};

export function Topbar({
  activeTab,
  employeeFlowStep,
  onOpenCommandPalette,
  onOpenCreateAgent,
  onOpenBuyNumber,
  user,
  onToggleMobileSidebar,
  onBackToLanding,
  onSignOut,
  onNavigate,
}) {
  const { campaigns, wallet, openAddFunds, isLoading } = useWorkspace();
  const runningCampaign = campaigns.find((c) => c.status === 'running');
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef(null);
  // India-first: rupees are the primary figure; dollars only in the tooltip.
  const money = walletAmounts(wallet);
  const walletLabel = money.primary;

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target)) {
        setUserMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const tabLabels = {
    overview: 'Home',
    employees: 'AI employees',
    'phone-numbers': 'Phone numbers',
    calls: 'Calls',
    leads: 'Leads',
    campaigns: 'Campaigns',
    billing: 'Billing & usage',
    calculator: 'Usage calculator',
    integrations: 'Integrations',
    settings: 'Settings',
    analytics: 'Analytics',
    admin: 'Platform admin',
  };

  const go = (tab) => {
    setUserMenuOpen(false);
    onNavigate?.(tab);
  };

  return (
    <header className="h-14 bg-white/95 backdrop-blur-md border-b border-line px-3 sm:px-6 flex items-center justify-between gap-3 sticky top-0 z-30 shadow-2xs">
      <div className="flex items-center gap-2 min-w-0">
        <button
          type="button"
          onClick={onToggleMobileSidebar}
          className="md:hidden min-w-[44px] min-h-[44px] -ml-1 p-2.5 rounded-control text-ink hover:bg-canvas border border-transparent hover:border-line flex items-center justify-center transition-colors active:scale-95"
          aria-label="Open navigation menu"
        >
          <Menu className="w-5 h-5 text-ink" />
        </button>

        <p className="text-sm font-bold text-ink truncate">
          {tabLabels[activeTab] || 'Page not found'}
          {activeTab === 'employees' && employeeFlowStep && EMPLOYEE_STEP_LABELS[employeeFlowStep] && (
            <span className="text-fg-body font-semibold">
              {' '}
              · {EMPLOYEE_STEP_LABELS[employeeFlowStep]}
            </span>
          )}
        </p>

        {runningCampaign && (
          <div className="hidden lg:flex items-center gap-1.5 ml-2 px-2.5 py-0.5 rounded-full bg-success-soft border border-success-line text-meta text-success-fg">
            <Radio className="w-3 h-3 animate-pulse motion-reduce:animate-none text-success" />
            <span>Calling: {runningCampaign.name}</span>
          </div>
        )}
      </div>

      {/* Workspace Quick Search Trigger */}
      <div className="flex-1 max-w-md hidden md:block mx-3 lg:mx-4">
        <button
          type="button"
          onClick={onOpenCommandPalette}
          className="w-full flex items-center justify-between px-3.5 py-1.5 rounded-control bg-canvas border border-line hover:border-line-strong hover:bg-white text-ink transition-all text-xs group shadow-2xs"
          aria-label="Search workspace"
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <Search className="w-4 h-4 text-accent shrink-0 transition-transform group-hover:scale-110" />
            <span className="font-medium text-fg-body group-hover:text-ink truncate">
              Search workspace…
            </span>
          </div>
        </button>
      </div>

      <div className="flex items-center gap-1.5 sm:gap-2">
        {/* Mobile Search Button */}
        <button
          type="button"
          onClick={onOpenCommandPalette}
          className="md:hidden p-2 rounded-control text-ink hover:bg-canvas border border-transparent hover:border-line flex items-center justify-center transition-colors"
          aria-label="Search workspace"
          title="Search workspace"
        >
          <Search className="w-4 h-4 text-accent" />
        </button>
        <button
          type="button"
          data-testid="topbar-wallet"
          data-tour="topbar-wallet"
          onClick={() => openAddFunds?.(null)}
          className="inline-flex items-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-1.5 rounded-control text-xs font-semibold bg-white hover:bg-canvas text-ink border border-line shadow-2xs transition-all active:scale-[0.98]"
          title={`Wallet balance ${money.primary} (${money.secondary}). Click to add funds`}
          aria-label={`Wallet balance ${money.primary}. Add funds`}
        >
          <CreditCard className="w-3.5 h-3.5 text-accent shrink-0" />
          {isLoading && !wallet ? (
            <TopbarBalanceSkeleton />
          ) : (
            <span className="font-mono tabular-nums text-meta sm:text-ui">{walletLabel}</span>
          )}
        </button>

        <button
          type="button"
          onClick={onOpenBuyNumber}
          data-testid="topbar-buy-number"
          className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-control text-xs font-semibold bg-white hover:bg-canvas text-ink border border-line shadow-2xs transition-all active:scale-[0.98]"
        >
          <Phone className="w-3.5 h-3.5 text-accent" />
          <span>Buy number</span>
        </button>

        <TactileButton onClick={onOpenCreateAgent} size="sm" variant="primary" icon={Plus}>
          <span className="hidden sm:inline">New agent</span>
          <span className="sm:hidden">New</span>
        </TactileButton>

        <div className="relative" ref={userMenuRef}>
          <button
            type="button"
            onClick={() => setUserMenuOpen((o) => !o)}
            className="flex items-center gap-1.5 pl-1 pr-2 py-1 min-h-[40px] rounded-control border border-line bg-white hover:bg-canvas transition-all"
            aria-expanded={userMenuOpen}
            aria-haspopup="menu"
          >
            <div
              className="w-8 h-8 rounded-lg bg-ink text-white flex items-center justify-center text-xs font-mono font-bold"
              title={user?.email || user?.name || 'Account'}
            >
              {user?.name ? user.name.charAt(0).toUpperCase() : 'U'}
            </div>
            <ChevronDown className={`w-3.5 h-3.5 text-fg-body transition-transform ${userMenuOpen ? 'rotate-180' : ''}`} />
          </button>

          {userMenuOpen && (
            <div className="absolute right-0 top-full mt-2 w-56 bg-white rounded-control border border-line shadow-xl p-2 z-50 text-xs">
              {(user?.name || user?.email) && (
                <div className="px-2 py-2 mb-1 border-b border-line">
                  <div className="font-bold text-ink truncate">{user?.name}</div>
                  <div className="text-meta text-fg-body truncate">{user?.email}</div>
                </div>
              )}

              {/* Mobile Wallet Quick Top-up Card */}
              <div className="sm:hidden p-2.5 mb-1.5 rounded-control bg-canvas border border-line">
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <span className="text-meta text-fg-body flex items-center gap-1">
                    <CreditCard className="w-3 h-3 text-accent" />
                    Balance:
                  </span>
                  <span className="font-mono font-bold text-xs text-ink">{walletLabel}</span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setUserMenuOpen(false);
                    openAddFunds?.(null);
                  }}
                  className="w-full py-1.5 px-2 rounded-lg bg-accent text-white text-xs font-bold text-center hover:bg-accent-hover transition-colors shadow-2xs active:scale-[0.98]"
                >
                  Add funds
                </button>
              </div>
              <button
                type="button"
                onClick={() => go('settings')}
                className="w-full flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-canvas text-left font-medium text-ink"
              >
                <Settings className="w-3.5 h-3.5 text-fg-body" />
                Settings
              </button>
              <button
                type="button"
                onClick={() => go('billing')}
                className="w-full flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-canvas text-left font-medium text-ink"
              >
                <CreditCard className="w-3.5 h-3.5 text-fg-body" />
                Billing &amp; usage
              </button>
              <button
                type="button"
                onClick={() => {
                  setUserMenuOpen(false);
                  window.dispatchEvent(
                    new CustomEvent('dialtact:open-tour', { detail: { force: true } })
                  );
                  window.dispatchEvent(
                    new CustomEvent('dialtact:open-tour', { detail: { force: true } })
                  );
                }}
                className="w-full flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-canvas text-left font-medium text-ink"
              >
                <Compass className="w-3.5 h-3.5 text-accent" />
                Guided tour
              </button>
              {onBackToLanding && (
                <button
                  type="button"
                  onClick={() => {
                    setUserMenuOpen(false);
                    onBackToLanding();
                  }}
                  className="w-full flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-canvas text-left font-medium text-fg-body"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Marketing site
                </button>
              )}
              {onSignOut && (
                <>
                  <div className="my-1 border-t border-line" />
                  <button
                    type="button"
                    onClick={() => {
                      setUserMenuOpen(false);
                      onSignOut();
                    }}
                    className="w-full flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-red-50 text-left font-semibold text-red-600"
                  >
                    <LogOut className="w-3.5 h-3.5" />
                    Sign out
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
