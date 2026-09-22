import React from 'react';
import { Shield, Users } from 'lucide-react';
import { SolidCard } from '../ui/SolidCard';
import { useAuth } from '../../context/AuthContext';

export function SettingsModule() {
  const { user } = useAuth();

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-[#0F0E17] tracking-tight">Workspace Settings</h2>
        <p className="text-xs text-[#524E5E] mt-0.5">
          Account and organization settings are managed through your signed-in session.
        </p>
      </div>

      <SolidCard className="space-y-3">
        <h3 className="text-xs font-bold text-[#0F0E17] flex items-center gap-2">
          <Users className="w-3.5 h-3.5 text-[#6344E7]" />
          Signed-in user
        </h3>
        <p className="text-sm text-[#0F0E17] font-medium">{user?.name || user?.email || '—'}</p>
        <p className="text-xs text-[#524E5E]">{user?.email}</p>
        {user?.tenantName && (
          <p className="text-xs text-[#524E5E]">Organization: {user.tenantName}</p>
        )}
      </SolidCard>

      <SolidCard className="space-y-2">
        <h3 className="text-xs font-bold text-[#0F0E17] flex items-center gap-2">
          <Shield className="w-3.5 h-3.5 text-[#15803D]" />
          API access
        </h3>
        <p className="text-xs text-[#524E5E] leading-relaxed">
          Programmatic API keys and team invites are not enabled in this console build yet. Use the
          subscriber JWT from sign-in for authenticated API calls during development, or contact support
          for service accounts.
        </p>
      </SolidCard>
    </div>
  );
}
