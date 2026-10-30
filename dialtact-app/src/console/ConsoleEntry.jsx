import React from 'react';
import { AppShell } from './AppShell';
import { ConsoleGate } from '../components/ConsoleGate';

export default function ConsoleEntry({ onSignIn, onBackToLanding, onSignOut }) {
  return (
    <ConsoleGate onSignIn={onSignIn} onBackToMarketing={onBackToLanding}>
      <AppShell onBackToLanding={onBackToLanding} onSignOut={onSignOut} />
    </ConsoleGate>
  );
}
