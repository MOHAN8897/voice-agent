import React from 'react';
import { Blocks } from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';

export function IntegrationsModule() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">Integrations & Webhooks</h2>
        <p className="text-xs text-[#524E5E] mt-0.5">
          CRM, calendar, and outbound webhooks will connect here in a future release.
        </p>
      </div>
      <SolidCard className="p-8 text-center space-y-3">
        <Blocks className="w-10 h-10 text-[#6344E7] mx-auto opacity-80" />
        <p className="text-sm font-semibold text-[#0F0E17]">Integrations coming soon</p>
        <p className="text-xs text-[#524E5E] max-w-md mx-auto">
          Your calls, leads, and wallet already sync with the voice-agent API. HubSpot, Salesforce, and
          signed webhooks will be added when the subscriber integrations API ships.
        </p>
      </SolidCard>
    </div>
  );
}
