import React, { useState, useEffect } from 'react';
import { useWorkspace } from './context/WorkspaceContext';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { CommandPalette } from './CommandPalette';

// Submodules
import { OverviewModule } from './modules/OverviewModule';
import { EmployeesModule } from './modules/EmployeesModule';
import { AgentStudioModule } from './modules/AgentStudioModule';
import { CreateAgentWizard } from './modules/CreateAgentWizard';
import { PhoneNumbersModule } from './modules/PhoneNumbersModule';
import { CallsModule } from './modules/CallsModule';
import { LeadsModule } from './modules/LeadsModule';
import { CampaignsModule } from './modules/CampaignsModule';
import { BillingModule } from './modules/BillingModule';
import { IntegrationsModule } from './modules/IntegrationsModule';
import { SettingsModule } from './modules/SettingsModule';
import { TalkToAiConsole } from './modules/TalkToAiConsole';
import { useAuth } from '../context/AuthContext';
import { ConsoleSyncBanner } from './ui/ConsoleSyncBanner';
import { PurchaseProvisioningBanner } from './ui/PurchaseProvisioningBanner';

export function AppShell({ onBackToLanding, onSignOut }) {
  const { user } = useAuth();
  const {
    isCreateAgentOpen,
    setIsCreateAgentOpen,
    isBuyNumberOpen,
    setIsBuyNumberOpen,
    isCommandPaletteOpen,
    setIsCommandPaletteOpen,
    loadWorkspaceData,
  } = useWorkspace();

  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  const [activeTab, setActiveTab] = useState(() => {
    if (typeof window !== 'undefined' && window.location.hash.startsWith('#dashboard/')) {
      const tab = window.location.hash.replace('#dashboard/', '').split('?')[0];
      return tab || 'overview';
    }
    return 'overview';
  });

  // Handle hash changes if hash points to a specific tab
  useEffect(() => {
    const handleHash = () => {
      const hash = window.location.hash;
      if (hash.startsWith('#dashboard/')) {
        const tab = hash.replace('#dashboard/', '').split('?')[0];
        if (tab) setActiveTab(tab);
      }
    };
    handleHash();
    window.addEventListener('hashchange', handleHash);
    return () => window.removeEventListener('hashchange', handleHash);
  }, []);

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
    setActiveTab(tabId);
    window.location.hash = `#dashboard/${tabId}`;
    setIsMobileSidebarOpen(false);
    if (options.openCreate) {
      setIsCreateAgentOpen(true);
    }
    if (options.openBuy) {
      setIsBuyNumberOpen(true);
    }
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
        onOpenAddFunds={() => handleSelectTab('billing')}
        onBackToLanding={onBackToLanding}
        onSignOut={onSignOut}
        isMobileOpen={isMobileSidebarOpen}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-[#FAF9FD]">
        <Topbar
          activeTab={activeTab}
          onOpenCommandPalette={() => setIsCommandPaletteOpen(true)}
          onOpenCreateAgent={() => setIsCreateAgentOpen(true)}
          onOpenBuyNumber={() => {
            handleSelectTab('phone-numbers');
            setIsBuyNumberOpen(true);
          }}
          user={user}
          onBackToLanding={onBackToLanding}
          onSignOut={onSignOut}
          isMobileSidebarOpen={isMobileSidebarOpen}
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
                onOpenCreateAgent={() => setIsCreateAgentOpen(true)}
                onOpenBuyNumber={() => {
                  handleSelectTab('phone-numbers');
                  setIsBuyNumberOpen(true);
                }}
              />
            )}

            {activeTab === 'agent-studio' && (
              <AgentStudioModule
                onNavigate={handleNavigate}
                onOpenBuyNumber={() => {
                  handleSelectTab('phone-numbers');
                  setIsBuyNumberOpen(true);
                }}
              />
            )}

            {activeTab === 'talk-to-ai' && <TalkToAiConsole />}

            {activeTab === 'phone-numbers' && (
              <PhoneNumbersModule
                isBuyModalOpen={isBuyNumberOpen}
                onCloseBuyModal={() => setIsBuyNumberOpen(false)}
                onOpenBuyModal={() => setIsBuyNumberOpen(true)}
              />
            )}

            {activeTab === 'calls' && <CallsModule />}

            {activeTab === 'leads' && <LeadsModule />}

            {activeTab === 'campaigns' && <CampaignsModule />}

            {activeTab === 'billing' && <BillingModule />}

            {activeTab === 'integrations' && <IntegrationsModule />}

            {activeTab === 'settings' && <SettingsModule />}
          </div>
        </main>
      </div>

      {/* Global Modals */}
      <CreateAgentWizard
        isOpen={isCreateAgentOpen}
        onClose={() => setIsCreateAgentOpen(false)}
        onNavigate={handleNavigate}
      />

      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        onNavigate={handleNavigate}
      />
    </div>
  );
}
