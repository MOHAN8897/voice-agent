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
} from 'lucide-react';
import { TactileButton } from './ui/TactileButton';
import { TopbarBalanceSkeleton } from './ui/Skeleton';
import { useWorkspace } from './context/WorkspaceContext';

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
  const balanceInr = Number(wallet?.balanceInr) || 0;
  const balanceUsd = Number(wallet?.balanceUsd) || 0;
  const fx = Number(wallet?.fxRateInr) || 95.64;
  const displayUsd = balanceUsd > 0 ? balanceUsd : balanceInr > 0 ? balanceInr / fx : 0;
  const walletLabel = `$${displayUsd.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

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
    overview: 'Overview',
    employees: 'AI Employees',
    'phone-numbers': 'Phone numbers',
    calls: 'Call history & outbound',
    leads: 'Leads',
    campaigns: 'Outbound campaigns',
    billing: 'Billing & usage',
    integrations: 'Integrations',
    settings: 'Settings',
    admin: 'Platform admin',
  };

  const go = (tab) => {
    setUserMenuOpen(false);
    onNavigate?.(tab);
  };

  return (
    <header className="h-14 bg-white/95 backdrop-blur-md border-b border-[#E4E2EB] px-3 sm:px-6 flex items-center justify-between gap-3 sticky top-0 z-30 shadow-2xs">
      <div className="flex items-center gap-2 min-w-0">
        <button
          type="button"
          onClick={onToggleMobileSidebar}
          className="md:hidden min-w-[44px] min-h-[44px] -ml-1 p-2.5 rounded-xl text-[#0F0E17] hover:bg-[#FAF9FD] border border-transparent hover:border-[#E4E2EB] flex items-center justify-center transition-colors active:scale-95"
          aria-label="Open navigation menu"
        >
          <Menu className="w-5 h-5 text-[#0F0E17]" />
        </button>

        <h1 className="text-sm font-bold text-[#0F0E17] truncate">
          {tabLabels[activeTab] || 'Console'}
          {activeTab === 'employees' && employeeFlowStep && EMPLOYEE_STEP_LABELS[employeeFlowStep] && (
            <span className="text-[#524E5E] font-semibold">
              {' '}
              · {EMPLOYEE_STEP_LABELS[employeeFlowStep]}
            </span>
          )}
        </h1>

        {runningCampaign && (
          <div className="hidden lg:flex items-center gap-1.5 ml-2 px-2.5 py-0.5 rounded-full bg-[#ECFDF5] border border-[#A7F3D0] text-[11px] font-mono text-[#047857]">
            <Radio className="w-3 h-3 animate-pulse text-[#10B981]" />
            <span>Dialing: {runningCampaign.name}</span>
          </div>
        )}
      </div>

      <div className="flex-1 max-w-md hidden md:block mx-4">
        <button
          type="button"
          onClick={onOpenCommandPalette}
          className="w-full flex items-center justify-between px-3 py-1.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] hover:border-[#D1CFDB] text-[#524E5E] transition-all text-xs group"
        >
          <div className="flex items-center gap-2">
            <Search className="w-3.5 h-3.5 text-[#524E5E] group-hover:text-[#0F0E17]" />
            <span>Search workspace…</span>
          </div>
          <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-white text-[#524E5E] border border-[#E4E2EB] shadow-2xs">
            ⌘K
          </kbd>
        </button>
      </div>

      <div className="flex items-center gap-1.5 sm:gap-2">
        <button
          type="button"
          data-testid="topbar-wallet"
          data-tour="topbar-wallet"
          onClick={() => openAddFunds?.(null)}
          className="inline-flex items-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-1.5 rounded-xl text-xs font-semibold bg-white hover:bg-[#FAF9FD] text-[#0F0E17] border border-[#E4E2EB] shadow-2xs transition-all active:scale-[0.98]"
          title="Wallet balance — click to add funds"
        >
          <CreditCard className="w-3.5 h-3.5 text-[#6344E7] shrink-0" />
          {isLoading && !wallet ? (
            <TopbarBalanceSkeleton />
          ) : (
            <span className="font-mono text-[11px] sm:text-xs">{walletLabel}</span>
          )}
        </button>

        <button
          type="button"
          onClick={onOpenBuyNumber}
          className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-white hover:bg-[#FAF9FD] text-[#0F0E17] border border-[#E4E2EB] shadow-2xs transition-all active:scale-[0.98]"
        >
          <Phone className="w-3.5 h-3.5 text-[#6344E7]" />
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
            className="flex items-center gap-1.5 pl-1 pr-2 py-1 min-h-[40px] rounded-xl border border-[#E4E2EB] bg-white hover:bg-[#FAF9FD] transition-all"
            aria-expanded={userMenuOpen}
            aria-haspopup="menu"
          >
            <div
              className="w-8 h-8 rounded-lg bg-[#0F0E17] text-white flex items-center justify-center text-xs font-mono font-bold"
              title={user?.email || user?.name || 'Account'}
            >
              {user?.name ? user.name.charAt(0).toUpperCase() : 'U'}
            </div>
            <ChevronDown className={`w-3.5 h-3.5 text-[#524E5E] transition-transform ${userMenuOpen ? 'rotate-180' : ''}`} />
          </button>

          {userMenuOpen && (
            <div className="absolute right-0 top-full mt-2 w-56 bg-white rounded-xl border border-[#E4E2EB] shadow-xl p-2 z-50 text-xs">
              {(user?.name || user?.email) && (
                <div className="px-2 py-2 mb-1 border-b border-[#E4E2EB]">
                  <div className="font-bold text-[#0F0E17] truncate">{user?.name}</div>
                  <div className="text-[11px] text-[#524E5E] truncate">{user?.email}</div>
                </div>
              )}

              {/* Mobile Wallet Quick Top-up Card */}
              <div className="sm:hidden p-2.5 mb-1.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <span className="text-[11px] text-[#524E5E] flex items-center gap-1">
                    <CreditCard className="w-3 h-3 text-[#6344E7]" />
                    Balance:
                  </span>
                  <span className="font-mono font-bold text-xs text-[#0F0E17]">{walletLabel}</span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setUserMenuOpen(false);
                    openAddFunds?.(null);
                  }}
                  className="w-full py-1.5 px-2 rounded-lg bg-[#6344E7] text-white text-xs font-bold text-center hover:bg-[#5235D9] transition-colors shadow-2xs active:scale-[0.98]"
                >
                  + Add funds
                </button>
              </div>
              <button
                type="button"
                onClick={() => go('settings')}
                className="w-full flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-[#FAF9FD] text-left font-medium text-[#0F0E17]"
              >
                <Settings className="w-3.5 h-3.5 text-[#524E5E]" />
                Settings
              </button>
              <button
                type="button"
                onClick={() => go('billing')}
                className="w-full flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-[#FAF9FD] text-left font-medium text-[#0F0E17]"
              >
                <CreditCard className="w-3.5 h-3.5 text-[#524E5E]" />
                Billing & usage
              </button>
              {onBackToLanding && (
                <button
                  type="button"
                  onClick={() => {
                    setUserMenuOpen(false);
                    onBackToLanding();
                  }}
                  className="w-full flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-[#FAF9FD] text-left font-medium text-[#524E5E]"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Marketing site
                </button>
              )}
              {onSignOut && (
                <>
                  <div className="my-1 border-t border-[#E4E2EB]" />
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
