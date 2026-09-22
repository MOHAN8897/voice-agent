import React, { useState, useRef, useEffect } from 'react';
import {
  LayoutDashboard,
  Bot,
  FileCode2,
  Mic,
  Phone,
  PhoneCall,
  Megaphone,
  Users,
  CreditCard,
  Blocks,
  Settings,
  ExternalLink,
  ChevronDown,
  Zap,
  Check,
  Plus,
  LogOut,
  Building2,
  Sparkles,
  X
} from 'lucide-react';
import { useWorkspace } from './context/WorkspaceContext';

export function Sidebar({
  activeTab,
  onSelectTab,
  onOpenCreateAgent,
  onOpenBuyNumber,
  onOpenAddFunds,
  onBackToLanding,
  onSignOut,
  isMobileOpen = false,
  onCloseMobile
}) {
  const {
    wallet,
    agents,
    phoneNumbers,
    workspaces,
    currentWorkspace,
    switchWorkspace,
    createWorkspace
  } = useWorkspace();

  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [newWorkspaceName, setNewWorkspaceName] = useState('');
  const [newWorkspaceTier, setNewWorkspaceTier] = useState('Professional Fleet');
  const dropdownRef = useRef(null);

  const handleSelectTab = (tabId) => {
    onSelectTab(tabId);
    if (onCloseMobile) onCloseMobile();
  };

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsDropdownOpen(false);
      }
    }
    if (isDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isDropdownOpen]);

  const handleCreateWorkspaceSubmit = (e) => {
    e.preventDefault();
    if (!newWorkspaceName.trim()) return;
    createWorkspace(newWorkspaceName.trim(), newWorkspaceTier);
    setNewWorkspaceName('');
    setIsCreateModalOpen(false);
    setIsDropdownOpen(false);
    if (onCloseMobile) onCloseMobile();
  };

  const navigationGroups = [
    {
      group: 'OVERVIEW',
      items: [
        { id: 'overview', label: 'Overview', icon: LayoutDashboard }
      ]
    },
    {
      group: 'AI WORKFORCE',
      items: [
        { id: 'employees', label: 'AI Employees', icon: Bot, badge: agents.length },
        { id: 'agent-studio', label: 'Script Studio', icon: FileCode2 },
        { id: 'talk-to-ai', label: 'Voice Testing', icon: Mic }
      ]
    },
    {
      group: 'TELEPHONY',
      items: [
        { id: 'phone-numbers', label: 'Virtual Numbers', icon: Phone, badge: phoneNumbers.length },
        { id: 'calls', label: 'Call History', icon: PhoneCall },
        { id: 'campaigns', label: 'Bulk Campaigns', icon: Megaphone }
      ]
    },
    {
      group: 'INSIGHTS',
      items: [
        { id: 'leads', label: 'Lead Engine', icon: Users }
      ]
    },
    {
      group: 'WORKSPACE',
      items: [
        { id: 'billing', label: 'Billing & Usage', icon: CreditCard },
        { id: 'integrations', label: 'Integrations', icon: Blocks },
        { id: 'settings', label: 'Settings', icon: Settings }
      ]
    }
  ];

  return (
    <>
      {/* Mobile Backdrop Overlay */}
      {isMobileOpen && (
        <div
          onClick={onCloseMobile}
          className="md:hidden fixed inset-0 bg-[#0F0E17]/60 backdrop-blur-xs z-40 transition-opacity animate-in fade-in duration-150"
          aria-hidden="true"
        />
      )}

      <aside
        className={`
          fixed md:sticky top-0 bottom-0 left-0 z-50 md:z-20
          w-64 bg-white border-r border-[#E4E2EB] flex flex-col shrink-0 select-none h-screen shadow-2xs
          transition-transform duration-200 ease-in-out
          ${isMobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
        `}
      >
        {/* Workspace Branding & Interactive Selector */}
        <div className="p-4 border-b border-[#E4E2EB] relative" ref={dropdownRef}>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsDropdownOpen((prev) => !prev)}
              className={`flex-1 flex items-center justify-between gap-2 p-2 rounded-xl border transition-all text-left group ${
                isDropdownOpen
                  ? 'bg-white border-[#6344E7] shadow-xs ring-2 ring-[#6344E7]/10'
                  : 'bg-[#FAF9FD] border-[#E4E2EB] hover:border-[#D1CFDB]'
              }`}
            >
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-7 h-7 rounded-lg bg-[#0F0E17] flex items-center justify-center text-white font-bold text-xs shadow-xs shrink-0">
              {currentWorkspace?.avatar || 'V'}
            </div>
            <div className="min-w-0">
              <div className="text-xs font-bold text-[#0F0E17] truncate">
                {currentWorkspace?.name || 'Acme Health Corp'}
              </div>
              <div className="text-[10px] text-[#524E5E] font-mono truncate">
                {currentWorkspace?.tier || 'Enterprise Fleet'}
              </div>
            </div>
          </div>
          <ChevronDown
            className={`w-3.5 h-3.5 text-[#524E5E] shrink-0 transition-transform duration-200 ${
              isDropdownOpen ? 'rotate-180 text-[#6344E7]' : 'group-hover:text-[#0F0E17]'
            }`}
          />
        </button>
          {onCloseMobile && (
            <button
              type="button"
              onClick={onCloseMobile}
              className="md:hidden p-2 rounded-xl text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD] border border-[#E4E2EB]"
              aria-label="Close navigation drawer"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Dropdown Menu */}
        {isDropdownOpen && (
          <div className="absolute left-3 right-3 top-16 bg-white border border-[#E4E2EB] rounded-2xl shadow-craft-lg z-50 p-2 text-xs space-y-1 animate-in fade-in zoom-in-95 duration-100">
            {/* Current Organization Info Card */}
            <div className="p-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
              <div className="flex items-center justify-between gap-1 mb-1">
                <span className="text-[10px] uppercase font-bold text-[#8C879A] tracking-wider">
                  Active Organization
                </span>
                <span className="text-[10px] font-mono font-bold text-[#6344E7] bg-[#F0EEF6] px-1.5 py-0.5 rounded">
                  {currentWorkspace?.tier}
                </span>
              </div>
              <div className="text-xs font-bold text-[#0F0E17] truncate">
                {currentWorkspace?.name}
              </div>
              <div className="text-[10px] text-[#524E5E] font-mono mt-0.5">
                Role: {currentWorkspace?.role} • {currentWorkspace?.activeAgents || agents.length} Agents
              </div>
            </div>

            {/* Switch Organization List */}
            <div className="pt-2 px-2 pb-1 text-[10px] font-bold text-[#8C879A] uppercase tracking-wider">
              Switch Organization
            </div>

            <div className="space-y-0.5 max-h-36 overflow-y-auto pr-1">
              {(workspaces || []).map((ws) => {
                const isCurrent = ws.id === currentWorkspace?.id;
                return (
                  <button
                    key={ws.id}
                    type="button"
                    onClick={() => {
                      switchWorkspace(ws.id);
                      setIsDropdownOpen(false);
                    }}
                    className={`w-full flex items-center justify-between p-2 rounded-xl text-left transition-all ${
                      isCurrent
                        ? 'bg-[#F0EEF6] font-bold text-[#0F0E17]'
                        : 'hover:bg-[#FAF9FD] text-[#524E5E] hover:text-[#0F0E17]'
                    }`}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="w-6 h-6 rounded-lg bg-[#0F0E17] text-white flex items-center justify-center font-bold text-[10px] shrink-0">
                        {ws.avatar}
                      </div>
                      <div className="min-w-0">
                        <div className="text-xs truncate">{ws.name}</div>
                        <div className="text-[10px] text-[#8C879A] font-mono truncate">{ws.tier}</div>
                      </div>
                    </div>
                    {isCurrent && <Check className="w-3.5 h-3.5 text-[#6344E7] shrink-0 ml-2" />}
                  </button>
                );
              })}
            </div>

            <div className="my-1 border-t border-[#E4E2EB]" />

            {/* Organization Options */}
            <div className="pt-1 px-2 pb-0.5 text-[10px] font-bold text-[#8C879A] uppercase tracking-wider">
              Organization Options
            </div>

            <button
              type="button"
              onClick={() => {
                setIsDropdownOpen(false);
                handleSelectTab('settings');
              }}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-xl text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD] transition-all font-medium text-xs"
            >
              <Settings className="w-3.5 h-3.5 text-[#6344E7]" />
              <span>Workspace Settings & RBAC</span>
            </button>

            <button
              type="button"
              onClick={() => {
                setIsDropdownOpen(false);
                handleSelectTab('billing');
              }}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-xl text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD] transition-all font-medium text-xs"
            >
              <CreditCard className="w-3.5 h-3.5 text-[#6344E7]" />
              <span>Plan & Usage Billing</span>
            </button>

            <div className="my-1 border-t border-[#E4E2EB]" />

            {/* Create New Workspace */}
            <button
              type="button"
              onClick={() => {
                setIsDropdownOpen(false);
                setIsCreateModalOpen(true);
              }}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-xl text-[#6344E7] hover:bg-[#F0EEF6] font-semibold transition-all text-xs"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>+ Create New Workspace</span>
            </button>

            {onSignOut && (
              <button
                type="button"
                onClick={() => {
                  setIsDropdownOpen(false);
                  onSignOut();
                }}
                className="w-full flex items-center gap-2 px-2 py-1.5 rounded-xl text-[#DC2626] hover:bg-[#FEF2F2] transition-all text-xs"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span>Sign out</span>
              </button>
            )}
          </div>
        )}
      </div>

      {/* Navigation Links Scrollable Area */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
        {navigationGroups.map((navGroup) => (
          <div key={navGroup.group}>
            <div className="px-3 mb-1.5 text-[10px] font-bold text-[#8C879A] tracking-wider uppercase">
              {navGroup.group}
            </div>
            <div className="space-y-0.5">
              {navGroup.items.map((item) => {
                const Icon = item.icon;
                const isActive = activeTab === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => handleSelectTab(item.id)}
                    className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-semibold transition-all group ${
                      isActive
                        ? 'bg-[#0F0E17] text-white shadow-xs font-bold'
                        : 'text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD]'
                    }`}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <Icon
                        className={`w-4 h-4 shrink-0 transition-colors ${
                          isActive ? 'text-white' : 'text-[#524E5E] group-hover:text-[#0F0E17]'
                        }`}
                      />
                      <span className="truncate">{item.label}</span>
                    </div>

                    {item.badge !== undefined && (
                      <span
                        className={`text-[10px] font-mono px-1.5 py-0.5 rounded-md ${
                          isActive
                            ? 'bg-white/20 text-white font-bold'
                            : 'bg-[#F0EEF6] text-[#524E5E] border border-[#E4E2EB]'
                        }`}
                      >
                        {item.badge}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Footer Area: Credit Wallet & User Switcher */}
      <div className="p-3 border-t border-[#E4E2EB] space-y-2 bg-white">
        {/* Live Wallet Pill */}
        <div className="p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-medium text-[#524E5E] flex items-center gap-1">
              <Zap className="w-3 h-3 text-[#D97706]" />
              Talk Time
            </span>
            <span className="text-xs font-bold font-mono text-[#0F0E17]">
              {wallet.remainingMinutes.toLocaleString()} min
            </span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] text-[#524E5E] font-mono">
              ${wallet.usdEquivalent.toFixed(2)} USD
            </span>
            <button
              onClick={onOpenAddFunds}
              className="text-[10px] font-semibold text-[#6344E7] hover:text-[#5034CE] hover:underline"
            >
              + Add Funds
            </button>
          </div>
        </div>

        {/* Public Landing Page Switcher */}
        <button
          type="button"
          onClick={onBackToLanding}
          className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD] border border-[#E4E2EB] active:scale-[0.98] transition-all"
        >
          <ExternalLink className="w-3.5 h-3.5" />
          <span>Back to voxly.ai</span>
        </button>
        {onSignOut && (
          <button
            type="button"
            onClick={onSignOut}
            className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl text-xs font-semibold text-[#DC2626] hover:bg-[#FEF2F2] border border-[#FECACA] active:scale-[0.98] transition-all"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>Sign out</span>
          </button>
        )}
      </div>

      {/* Modal: Create New Workspace */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-[#E4E2EB] shadow-craft-lg max-w-md w-full p-6 space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-xl bg-[#0F0E17] text-white flex items-center justify-center">
                  <Building2 className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-[#0F0E17]">Create New Organization</h3>
                  <p className="text-xs text-[#524E5E]">Set up a dedicated voice employee workspace.</p>
                </div>
              </div>
              <button
                onClick={() => setIsCreateModalOpen(false)}
                className="p-1 rounded-lg text-[#524E5E] hover:text-[#0F0E17]"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateWorkspaceSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-[#0F0E17] mb-1">
                  Organization / Company Name
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Sterling Dental Group"
                  value={newWorkspaceName}
                  onChange={(e) => setNewWorkspaceName(e.target.value)}
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-[#0F0E17] mb-1">
                  Fleet Plan Tier
                </label>
                <select
                  value={newWorkspaceTier}
                  onChange={(e) => setNewWorkspaceTier(e.target.value)}
                  className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-3 py-2 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7]"
                >
                  <option value="Starter Fleet">Starter Fleet (1 Agent, 500 min)</option>
                  <option value="Professional Fleet">Professional Fleet (5 Agents, 2,500 min)</option>
                  <option value="Enterprise Fleet">Enterprise Fleet (Unlimited Agents, Dedicated SLA)</option>
                </select>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-[#E4E2EB]">
                <button
                  type="button"
                  onClick={() => setIsCreateModalOpen(false)}
                  className="px-3 py-2 rounded-xl text-xs font-semibold text-[#524E5E] hover:bg-[#FAF9FD]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-white bg-[#0F0E17] hover:bg-[#232130] transition-all active:scale-[0.98]"
                >
                  Create Organization
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </aside>
    </>
  );
}
