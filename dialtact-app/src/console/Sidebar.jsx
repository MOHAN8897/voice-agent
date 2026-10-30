import React, { useState, useRef, useEffect } from 'react';
import {
  LayoutDashboard,
  Bot,
  Phone,
  PhoneCall,
  Megaphone,
  Users,
  CreditCard,
  Calculator,
  Blocks,
  Settings,
  ExternalLink,
  ChevronDown,
  Zap,
  Check,
  Plus,
  Building2,
  X,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';
import { useWorkspace } from './context/WorkspaceContext';
import { walletAmounts } from '../lib/money';

export function Sidebar({
  activeTab,
  onSelectTab,
  onOpenCreateAgent,
  onOpenBuyNumber,
  onOpenAddFunds,
  onBackToLanding,
  isMobileOpen = false,
  inAgentWorkspace = false,
  onCloseMobile
}) {
  const {
    wallet,
    agents,
    phoneNumbers,
    workspaces,
    currentWorkspace,
    switchWorkspace,
    createWorkspace,
    isLoading
  } = useWorkspace();
  // Drives the payment-wall styling on the wallet pill.
  const walletIsEmpty =
    (Number(wallet?.balanceInr) || 0) <= 0 && (Number(wallet?.balanceUsd) || 0) <= 0;

  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(() => {
    try { return localStorage.getItem('dialtact:sidebar-collapsed:v1') === 'true'; } catch { return false; }
  });
  useEffect(() => {
    if (inAgentWorkspace) setIsCollapsed(true);
    else {
      try { setIsCollapsed(localStorage.getItem('dialtact:sidebar-collapsed:v1') === 'true'); } catch { /* Use current preference. */ }
    }
  }, [inAgentWorkspace]);
  const toggleCollapsed = () => {
    setIsCollapsed((previous) => {
      try { localStorage.setItem('dialtact:sidebar-collapsed:v1', String(!previous)); } catch { /* Storage may be unavailable. */ }
      return !previous;
    });
    setIsDropdownOpen(false);
  };
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [newWorkspaceName, setNewWorkspaceName] = useState('');
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
    createWorkspace(newWorkspaceName.trim());
    setNewWorkspaceName('');
    setIsCreateModalOpen(false);
    setIsDropdownOpen(false);
    if (onCloseMobile) onCloseMobile();
  };

  const navigationGroups = [
    {
      group: 'Home',
      items: [
        { id: 'overview', label: 'Home', icon: LayoutDashboard }
      ]
    },
    {
      group: 'Team',
      items: [{ id: 'employees', label: 'AI employees', icon: Bot, badge: agents.length }],
    },
    {
      group: 'Phone',
      items: [
        { id: 'phone-numbers', label: 'Phone lines', icon: Phone, badge: phoneNumbers.length },
        { id: 'calls', label: 'Calls', icon: PhoneCall },
        { id: 'campaigns', label: 'Campaigns', icon: Megaphone }
      ]
    },
    {
      group: 'Customers',
      items: [
        { id: 'leads', label: 'Leads', icon: Users }
      ]
    },
    {
      group: 'Workspace',
      items: [
        { id: 'billing', label: 'Billing & usage', icon: CreditCard },
        { id: 'calculator', label: 'Usage calculator', icon: Calculator },
        { id: 'integrations', label: 'Integrations', icon: Blocks },
        { id: 'settings', label: 'Settings', icon: Settings },
      ]
    },
  ];

  return (
    <>
      {/* Mobile Backdrop Overlay */}
      {isMobileOpen && (
        <div
          onClick={onCloseMobile}
          className="md:hidden fixed inset-0 bg-ink/60 backdrop-blur-xs z-40 transition-opacity animate-in fade-in duration-150"
          aria-hidden="true"
        />
      )}

      <aside
        data-testid="console-sidebar"
        data-collapsed={isCollapsed}
        className={`
          fixed md:sticky top-0 bottom-0 left-0 z-50 md:z-20
          console-sidebar w-64 bg-white border-r border-line flex flex-col shrink-0 select-none h-screen shadow-2xs
          transition-transform duration-200 ease-in-out
          ${isMobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
        `}
      >
        {/* Workspace Branding & Interactive Selector */}
        <div className="p-4 border-b border-line relative" ref={dropdownRef}>
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-label="Switch workspace"
              title={currentWorkspace?.name || 'Switch workspace'}
              onClick={() => setIsDropdownOpen((prev) => !prev)}
              className={`flex-1 min-w-0 flex items-center justify-between gap-2 p-2 rounded-control border transition-all text-left group ${
                isDropdownOpen
                  ? 'bg-white border-accent shadow-xs ring-2 ring-accent/10'
                  : 'bg-canvas border-line hover:border-line-strong'
              }`}
            >
          {/* chisel: show subtle skeleton placeholder if workspace is loading */}
          {isLoading && !currentWorkspace ? (
            <div className="flex items-center gap-2.5 min-w-0 animate-pulse">
              <div className="w-7 h-7 rounded-lg bg-line shrink-0" />
              <div className="min-w-0 space-y-1">
                <div className="h-3 w-24 bg-line rounded" />
                <div className="h-2 w-16 bg-line/60 rounded" />
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-7 h-7 rounded-lg bg-ink flex items-center justify-center text-white font-bold text-xs shadow-xs shrink-0">
                {currentWorkspace?.avatar || 'D'}
              </div>
              <div className="sidebar-label min-w-0">
                <div className="text-xs font-bold text-ink truncate">
                  {currentWorkspace?.name || 'Acme Health Corp'}
                </div>
                <div className="text-meta text-fg-body truncate">
                  Workspace
                </div>
              </div>
            </div>
          )}
          <ChevronDown
            className={`sidebar-label w-3.5 h-3.5 text-fg-body shrink-0 transition-transform duration-200 ${
              isDropdownOpen ? 'rotate-180 text-accent' : 'group-hover:text-ink'
            }`}
          />
        </button>
          {onCloseMobile && (
            <button
              type="button"
              onClick={onCloseMobile}
              className="md:hidden p-2 rounded-control text-fg-body hover:text-ink hover:bg-canvas border border-line"
              aria-label="Close navigation drawer"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Dropdown Menu */}
        {isDropdownOpen && (
          <div className="absolute left-3 top-16 w-60 bg-white border border-line rounded-2xl shadow-craft-lg z-50 p-2 text-xs space-y-1 animate-in fade-in zoom-in-95 duration-100">
            {/* Current Organization Info Card */}
            <div className="p-2.5 rounded-control bg-canvas border border-line">
              <div className="flex items-center justify-between gap-1 mb-1">
                <span className="text-meta font-medium text-fg-muted">
                  Current workspace
                </span>
                <span className="text-meta font-mono font-bold text-accent bg-surface-subtle px-1.5 py-0.5 rounded">
                  {currentWorkspace?.tier}
                </span>
              </div>
              <div className="text-xs font-bold text-ink truncate">
                {currentWorkspace?.name}
              </div>
              <div className="text-meta text-fg-body font-mono mt-0.5">
                Role: {currentWorkspace?.role} • {currentWorkspace?.activeAgents || agents.length} Agents
              </div>
            </div>

            {/* Switch Organization List */}
            <div className="pt-2 px-2 pb-1 text-meta font-medium text-fg-muted">
              Switch workspace
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
                    className={`w-full flex items-center justify-between p-2 rounded-control text-left transition-all ${
                      isCurrent
                        ? 'bg-surface-subtle font-bold text-ink'
                        : 'hover:bg-canvas text-fg-body hover:text-ink'
                    }`}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="w-6 h-6 rounded-lg bg-ink text-white flex items-center justify-center font-bold text-meta shrink-0">
                        {ws.avatar}
                      </div>
                      <div className="min-w-0">
                        <div className="text-xs truncate">{ws.name}</div>
                        <div className="text-meta text-fg-muted font-mono truncate">{ws.tier}</div>
                      </div>
                    </div>
                    {isCurrent && <Check className="w-3.5 h-3.5 text-accent shrink-0 ml-2" />}
                  </button>
                );
              })}
            </div>

            <div className="my-1 border-t border-line" />

            {/* Create New Workspace */}
            <button
              type="button"
              onClick={() => {
                setIsDropdownOpen(false);
                setIsCreateModalOpen(true);
              }}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-control text-accent hover:bg-surface-subtle font-semibold transition-all text-xs"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Create workspace</span>
            </button>
          </div>
        )}
      </div>

      <button type="button" onClick={toggleCollapsed}
        aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-expanded={!isCollapsed}
        title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        data-testid="sidebar-collapse-toggle"
        className={`hidden md:flex items-center ${isCollapsed ? 'flex-col gap-1' : 'gap-2'} mx-3 mt-3 px-3 py-2 rounded-lg text-xs text-fg-body hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-accent`}>
        {isCollapsed ? <PanelLeftOpen className="w-4 h-4 shrink-0" /> : <PanelLeftClose className="w-4 h-4 shrink-0" />}
        <span className={isCollapsed ? 'sr-only' : 'sidebar-label'}>{isCollapsed ? 'Expand navigation' : 'Collapse navigation'}</span>
        {isCollapsed && <span className="text-meta leading-none" aria-hidden="true">Expand</span>}
      </button>

      {/* Navigation Links Scrollable Area */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
        {navigationGroups.map((navGroup) => (
          <div key={navGroup.group}>
            <div className="sidebar-group-label px-3 mb-1.5 text-meta font-medium text-fg-muted">
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
                    data-tour={`nav-${item.id}`}
                    data-testid={`nav-${item.id}`}
                    aria-label={item.label}
                    aria-current={isActive ? 'page' : undefined}
                    title={item.label}
                    className={`w-full flex items-center justify-between px-3 py-2 rounded-control text-xs font-semibold transition-all group ${
                      isActive
                        ? 'bg-ink text-white shadow-xs font-bold'
                        : 'text-fg-body hover:text-ink hover:bg-canvas'
                    }`}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <Icon
                        className={`w-4 h-4 shrink-0 transition-colors ${
                          isActive ? 'text-white' : 'text-fg-body group-hover:text-ink'
                        }`}
                      />
                      <span className="sidebar-label truncate">{item.label}</span>
                    </div>

                    {/* chisel: subtle badge pulse skeleton while workspace data loads */}
                    {item.badge !== undefined && (!isCollapsed || isMobileOpen) && (
                      isLoading && item.badge === 0 ? (
                        <span
                          className={`inline-block h-4 w-5 rounded-md animate-pulse ${
                            isActive ? 'bg-white/20' : 'bg-line/80'
                          }`}
                          aria-hidden="true"
                        />
                      ) : (
                        <span
                          className={`text-meta font-mono px-1.5 py-0.5 rounded-md ${
                            isActive
                              ? 'bg-white/20 text-white font-bold'
                              : 'bg-surface-subtle text-fg-body border border-line'
                          }`}
                        >
                          {item.badge}
                        </span>
                      )
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Footer Area: Credit Wallet & User Switcher */}
      <div className="p-3 border-t border-line space-y-2 bg-white">
        {/* Live Wallet Pill — the whole pill opens the payment wall. */}
        <button
          type="button"
          onClick={onOpenAddFunds}
          data-testid="sidebar-wallet-pill"
          aria-label="Wallet and add funds"
          title="Wallet and add funds"
          className={`w-full text-left p-3 rounded-control border transition-colors ${
            walletIsEmpty
              ? 'bg-warning-soft border-warning-line hover:bg-[#FEF3C7]'
              : 'bg-canvas border-line hover:border-accent/40'
          }`}
        >
          <Zap className="sidebar-collapsed-icon hidden w-4 h-4 mx-auto text-warning" />
          <div className="sidebar-label flex items-center justify-between mb-1.5">
            <span className="text-meta font-medium text-fg-body flex items-center gap-1">
              <Zap className="w-3 h-3 text-warning" />
              {walletIsEmpty ? 'Add credit to call' : 'Talk time'}
            </span>
            <span
              className={`text-xs font-bold font-mono ${
                walletIsEmpty ? 'text-warning-fg' : 'text-ink'
              }`}
            >
              {walletIsEmpty
                ? 'Empty'
                : `${Number(wallet?.remainingMinutes || 0).toLocaleString()} min`}
            </span>
          </div>
          <div className="sidebar-label flex items-center justify-between gap-2">
            <span className="text-meta text-fg-body font-mono tabular-nums" title={walletAmounts(wallet).secondary}>
              {walletAmounts(wallet).primary}
            </span>
            <span className="text-meta font-semibold text-accent-fg">
              Add funds
            </span>
          </div>
        </button>

        <button
          type="button"
          onClick={onBackToLanding}
          aria-label="Marketing site"
          title="Stay in this tab — returns to the marketing landing"
          className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-control text-xs font-semibold text-fg-body hover:text-ink hover:bg-canvas border border-line active:scale-[0.98] transition-all"
        >
          <ExternalLink className="w-3.5 h-3.5" aria-hidden />
          <span className="sidebar-label">Marketing site</span>
        </button>
      </div>

      {/* Modal: Create New Workspace */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-line shadow-craft-lg max-w-md w-full p-6 space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-control bg-ink text-white flex items-center justify-center">
                  <Building2 className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-ink">Create a workspace</h3>
                  <p className="text-xs text-fg-body">A separate workspace for another business.</p>
                </div>
              </div>
              <button
                onClick={() => setIsCreateModalOpen(false)}
                className="p-1 rounded-lg text-fg-body hover:text-ink"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateWorkspaceSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-ink mb-1">
                  Company name
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Sterling Dental Group"
                  value={newWorkspaceName}
                  onChange={(e) => setNewWorkspaceName(e.target.value)}
                  className="w-full bg-canvas border border-line rounded-control px-3 py-2 text-xs text-ink focus:outline-none focus:border-accent"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-line">
                <button
                  type="button"
                  onClick={() => setIsCreateModalOpen(false)}
                  className="px-3 py-2 rounded-control text-xs font-semibold text-fg-body hover:bg-canvas"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-control text-xs font-semibold text-white bg-ink hover:bg-[#232130] transition-all active:scale-[0.98]"
                >
                  Create workspace
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
