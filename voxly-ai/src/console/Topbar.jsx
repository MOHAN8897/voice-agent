import React from 'react';
import {
  Search,
  Plus,
  Phone,
  Radio,
  Menu,
  ExternalLink,
  LogOut,
} from 'lucide-react';
import { TactileButton } from './ui/TactileButton';
import { useWorkspace } from './context/WorkspaceContext';

export function Topbar({
  activeTab,
  onOpenCommandPalette,
  onOpenCreateAgent,
  onOpenBuyNumber,
  user,
  onToggleMobileSidebar,
  isMobileSidebarOpen,
  onBackToLanding,
  onSignOut,
}) {
  const { campaigns } = useWorkspace();
  const runningCampaign = campaigns.find((c) => c.status === 'running');

  const tabLabels = {
    overview: 'Workspace Overview',
    employees: 'AI Employees Fleet',
    'agent-studio': 'Agent Studio & Script Flow',
    'phone-numbers': 'Virtual Numbers & Routing',
    calls: 'Call Logs & Audio Inspector',
    leads: 'Autonomous Lead Pipeline',
    campaigns: 'Bulk Outbound Campaigns',
    billing: 'Wallet, Usage & Billing',
    integrations: 'Integrations & Webhooks',
    settings: 'Settings & Security',
    'talk-to-ai': 'Realtime Voice Testing Console'
  };

  return (
    <header className="h-14 bg-white/95 backdrop-blur-md border-b border-[#E4E2EB] px-3 sm:px-6 flex items-center justify-between gap-3 sticky top-0 z-30 shadow-2xs">
      {/* Left Area: Mobile Hamburger + Breadcrumb / Title */}
      <div className="flex items-center gap-2 min-w-0">
        {/* Mobile Sidebar Hamburger Toggle */}
        <button
          type="button"
          onClick={onToggleMobileSidebar}
          className="md:hidden min-w-[44px] min-h-[44px] -ml-1 p-2.5 rounded-xl text-[#0F0E17] hover:bg-[#FAF9FD] border border-transparent hover:border-[#E4E2EB] flex items-center justify-center transition-colors active:scale-95"
          aria-label="Open navigation menu"
          title="Toggle navigation"
        >
          <Menu className="w-5 h-5 text-[#0F0E17]" />
        </button>

        <span className="text-xs text-[#524E5E] font-medium hidden sm:inline">Console</span>
        <span className="text-xs text-[#8C879A] hidden sm:inline">/</span>
        <h1 className="text-xs sm:text-sm font-bold text-[#0F0E17] truncate">
          {tabLabels[activeTab] || 'Dashboard'}
        </h1>

        {runningCampaign && (
          <div className="hidden lg:flex items-center gap-1.5 ml-3 px-2.5 py-0.5 rounded-full bg-[#ECFDF5] border border-[#A7F3D0] text-[11px] font-mono text-[#047857]">
            <Radio className="w-3 h-3 animate-pulse text-[#10B981]" />
            <span>Dialing: {runningCampaign.name}</span>
          </div>
        )}
      </div>

      {/* Center Search / Command Palette Bar */}
      <div className="flex-1 max-w-md hidden md:block">
        <button
          type="button"
          onClick={onOpenCommandPalette}
          className="w-full flex items-center justify-between px-3 py-1.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] hover:border-[#D1CFDB] text-[#524E5E] transition-all text-xs group"
        >
          <div className="flex items-center gap-2">
            <Search className="w-3.5 h-3.5 text-[#524E5E] group-hover:text-[#0F0E17]" />
            <span>Search agents, numbers, leads, calls...</span>
          </div>
          <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-white text-[#524E5E] border border-[#E4E2EB] shadow-2xs">
            ⌘K
          </kbd>
        </button>
      </div>

      {/* Right Quick Actions */}
      <div className="flex items-center gap-2.5">
        <button
          type="button"
          onClick={onOpenBuyNumber}
          className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-white hover:bg-[#FAF9FD] text-[#0F0E17] border border-[#E4E2EB] shadow-2xs transition-all active:scale-[0.98]"
        >
          <Phone className="w-3.5 h-3.5 text-[#6344E7]" />
          <span>Buy Number</span>
        </button>

        <TactileButton
          onClick={onOpenCreateAgent}
          size="sm"
          variant="primary"
          icon={Plus}
        >
          <span>Create Agent</span>
        </TactileButton>

        {onBackToLanding && (
          <button
            type="button"
            onClick={onBackToLanding}
            className="hidden lg:inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-xs font-semibold text-[#524E5E] hover:bg-[#FAF9FD] border border-[#E4E2EB]"
            title="Marketing site"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            Site
          </button>
        )}

        {onSignOut && (
          <button
            type="button"
            onClick={onSignOut}
            className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-xs font-semibold text-[#DC2626] hover:bg-[#FEF2F2] border border-[#FECACA]"
          >
            <LogOut className="w-3.5 h-3.5" />
            Sign out
          </button>
        )}

        <div
          className="w-8 h-8 rounded-xl bg-[#0F0E17] text-white flex items-center justify-center text-xs font-mono font-bold shadow-2xs"
          title={user?.email || user?.name || 'User'}
        >
          {user?.name ? user.name.charAt(0).toUpperCase() : 'U'}
        </div>
      </div>
    </header>
  );
}
