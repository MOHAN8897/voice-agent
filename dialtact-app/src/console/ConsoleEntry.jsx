import React from 'react';
import { AppShell } from './AppShell';
import { ConsoleGate } from '../components/ConsoleGate';
import { useAuth } from '../context/AuthContext';
import { WorkspaceRestoreScreen } from './ui/WorkspaceRestoreScreen';

/** A workspace pending deletion shows the restore screen, never the console. */
function ConsoleOrRestore({ onBackToLanding, onSignOut }) {
  const { user } = useAuth();
  if (user?.tenantStatus === 'quarantined') {
    return <WorkspaceRestoreScreen />;
  }
  return <AppShell onBackToLanding={onBackToLanding} onSignOut={onSignOut} />;
}

export default function ConsoleEntry({ onSignIn, onBackToLanding, onSignOut }) {
  return (
    <ConsoleGate onSignIn={onSignIn} onBackToMarketing={onBackToLanding}>
      <ConsoleOrRestore onBackToLanding={onBackToLanding} onSignOut={onSignOut} />
    </ConsoleGate>
  );
}
