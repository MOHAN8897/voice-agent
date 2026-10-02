import React, { useState, useEffect } from 'react';
import { useWorkspace } from './context/WorkspaceContext';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { CommandPalette } from './CommandPalette';

// Submodules
import { OverviewModule } from './modules/OverviewModule';
import { EmployeesModule } from './modules/EmployeesModule';
import {
  parseDashboardHash,
  buildEmployeesHash,
  legacyEmployeeStep,
  resolveConsoleTab,
} from './employeeFlowHash';
import { CreateAgentWizard } from './modules/CreateAgentWizard';
import { PhoneNumbersModule } from './modules/PhoneNumbersModule';
import { CallsModule } from './modules/CallsModule';
import { LeadsModule } from './modules/LeadsModule';
import { CampaignsModule } from './modules/CampaignsModule';
import { BillingModule } from './modules/BillingModule';
import { IntegrationsModule } from './modules/IntegrationsModule';
import { SettingsModule } from './modules/SettingsModule';
import { AdminModule } from './modules/AdminModule';
import { useAuth } from '../context/AuthContext';
import { ConsoleSyncBanner } from './ui/ConsoleSyncBanner';
import { ImpersonationBanner } from './ui/ImpersonationBanner';
import { PurchaseProvisioningBanner } from './ui/PurchaseProvisioningBanner';
import { ToastHost } from './ui/ToastHost';
import { AddFundsModal } from './ui/AddFundsModal';

export function AppShell({ onBackToLanding, onSignOut }) {
  const { user } = useAuth();
  const {
    isCreateAgentOpen,
    setIsCreateAgentOpen,
    isBuyNumberOpen,
    setIsBuyNumberOpen,
    isCommandPaletteOpen,
    setIsCommandPaletteOpen,
    isAddFundsOpen,
    addFundsReason,
    closeAddFunds,
    openAddFunds,
    requireFunds,
    loadWorkspaceData,
    setSelectedAgentId,
  } = useWorkspace();

  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  const [employeeFlowStep, setEmployeeFlowStep] = useState(null);

  const [activeTab, setActiveTab] = useState(() => {
    if (typeof window !== 'undefined' && window.location.hash.startsWith('#dashboard/')) {
      const { tab } = parseDashboardHash(window.location.hash);
      return resolveConsoleTab(tab) || 'overview';
    }
    return 'overview';
  });

  const applyHash = (hash) => {
    if (!hash.startsWith('#dashboard/')) return;
    const { tab, step, agentId } = parseDashboardHash(hash);
    const legacyStep = legacyEmployeeStep(tab);
    const resolvedTab = resolveConsoleTab(tab);
    if (resolvedTab) setActiveTab(resolvedTab);
    const flowStep = legacyStep || (resolvedTab === 'employees' ? step : null);
    setEmployeeFlowStep(flowStep);
    if (agentId) setSelectedAgentId(agentId);
    if (legacyStep && resolvedTab === 'employees') {
      window.history.replaceState(null, '', buildEmployeesHash({ step: legacyStep, agentId }));
    }
  };

  useEffect(() => {
    applyHash(window.location.hash);
    const handleHash = () => applyHash(window.location.hash);
    window.addEventListener('hashchange', handleHash);
    return () => window.removeEventListener('hashchange', handleHash);
  }, [setSelectedAgentId]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('success') === '1' || params.get('topup') === '1') {
      loadWorkspaceData?.();
    }
  }, [loadWorkspaceData]);

  const handleSelectTab = (tabId) => {
    setActiveTab(tabId);
    window.location.hash = `#dashboard/${tabId}`;
    setIsMobileSidebarOpen(false);
  };

  const handleNavigate = (tabId, options = {}) => {
    setIsMobileSidebarOpen(false);
    const legacyStep = legacyEmployeeStep(tabId);
    const tab = legacyStep ? 'employees' : tabId;
    setActiveTab(tab);

    if (tab === 'employees' && (legacyStep || options.step)) {
      const step = options.step || legacyStep;
      if (options.agentId) setSelectedAgentId(options.agentId);
      setEmployeeFlowStep(step || null);
      window.location.hash = buildEmployeesHash({ step, agentId: options.agentId });
    } else if (tab === 'employees' && !options.step && !legacyStep) {
      setEmployeeFlowStep(null);
      window.location.hash = '#dashboard/employees';
    } else {
      setEmployeeFlowStep(null);
      window.location.hash = `#dashboard/${tab}`;
      if (options.agentId) {
        setSelectedAgentId(options.agentId);
        if (tab === 'calls' && typeof window !== 'undefined') {
          sessionStorage.setItem('voxly_calls_agent', options.agentId);
        }
      }
    }

    if (options.openCreate) setIsCreateAgentOpen(true);
    if (options.openBuy) setIsBuyNumberOpen(true);
  };

  const handleEmployeeFlowStepChange = (step, agentId) => {
    setEmployeeFlowStep(step);
    if (agentId) setSelectedAgentId(agentId);
    window.location.hash = buildEmployeesHash({ step, agentId });
  };

  const handleBackToFleet = () => {
    setEmployeeFlowStep(null);
    window.location.hash = '#dashboard/employees';
  };

  return (
    <div className="flex h-screen bg-[#FAF9FD] text-[#0F0E17] overflow-hidden select-none font-sans antialiased">
      {/* Primary Vertical Navigation (Responsive Desktop & Mobile Drawer) */}
      <Sidebar
        activeTab={activeTab}
        onSelectTab={handleSelectTab}
        onOpenCreateAgent={() => setIsCreateAgentOpen(true)}
        onOpenBuyNumber={() => {
          handleSelectTab('phone-numbers');
          setIsBuyNumberOpen(true);
        }}
        onOpenAddFunds={() => openAddFunds(null)}
        onBackToLanding={onBackToLanding}
        isMobileOpen={isMobileSidebarOpen}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-[#FAF9FD]">
        <ImpersonationBanner />
        <Topbar
          activeTab={activeTab}
          employeeFlowStep={employeeFlowStep}
          onOpenCommandPalette={() => setIsCommandPaletteOpen(true)}
          onOpenCreateAgent={() => setIsCreateAgentOpen(true)}
          onOpenBuyNumber={() => {
            handleSelectTab('phone-numbers');
            setIsBuyNumberOpen(true);
          }}
          onNavigate={handleSelectTab}
          user={user}
          onBackToLanding={onBackToLanding}
          onSignOut={onSignOut}
          onToggleMobileSidebar={() => setIsMobileSidebarOpen((prev) => !prev)}
        />

        {/* Dynamic Viewport */}
        <main className="flex-1 overflow-y-auto p-3 sm:p-6 lg:p-8 bg-[#FAF9FD]">
          <div className="max-w-7xl mx-auto pb-12">
            <ConsoleSyncBanner />
            <PurchaseProvisioningBanner />
            {activeTab === 'overview' && (
              <OverviewModule
                onNavigate={handleNavigate}
                onOpenCreateAgent={() => setIsCreateAgentOpen(true)}
                onOpenBuyNumber={() => {
                  handleSelectTab('phone-numbers');
                  setIsBuyNumberOpen(true);
                }}
              />
            )}

            {activeTab === 'employees' && (
              <EmployeesModule
                onNavigate={handleNavigate}
                employeeFlowStep={employeeFlowStep}
                onEmployeeFlowStepChange={handleEmployeeFlowStepChange}
                onBackToFleet={handleBackToFleet}
                onOpenCreateAgent={() => setIsCreateAgentOpen(true)}
                onOpenBuyNumber={() => {
                  handleSelectTab('phone-numbers');
                  setIsBuyNumberOpen(true);
                }}
              />
            )}

            {activeTab === 'phone-numbers' && (
              <PhoneNumbersModule
                isBuyModalOpen={isBuyNumberOpen}
                onCloseBuyModal={() => setIsBuyNumberOpen(false)}
                onOpenBuyModal={() => {
                  // Payment wall: buying a number charges the wallet immediately.
                  if (requireFunds('A phone number costs $4 per month, charged to your wallet.')) {
                    return;
                  }
                  setIsBuyNumberOpen(true);
                }}
                onNavigate={handleNavigate}
              />
            )}

            {activeTab === 'calls' && <CallsModule onRequireFunds={() => openAddFunds('Add credit to your wallet to place a call.')} />}

            {activeTab === 'leads' && <LeadsModule />}

            {activeTab === 'campaigns' && <CampaignsModule />}

            {activeTab === 'billing' && <BillingModule />}

            {activeTab === 'integrations' && <IntegrationsModule />}

            {activeTab === 'settings' && <SettingsModule />}
            {activeTab === 'admin' && <AdminModule />}
          </div>
        </main>
      </div>

      {/* Global Modals */}
      <CreateAgentWizard
        isOpen={isCreateAgentOpen}
        onClose={() => setIsCreateAgentOpen(false)}
        onNavigate={handleNavigate}
      />

      <ToastHost />
      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        onNavigate={handleNavigate}
      />
      <AddFundsModal isOpen={isAddFundsOpen} onClose={closeAddFunds} reason={addFundsReason} />
    </div>
  );
}
