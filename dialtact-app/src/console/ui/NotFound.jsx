import React from 'react';
import { Compass } from 'lucide-react';
import { SolidCard } from './SolidCard';
import { EmptyState } from './EmptyState';
import { TactileButton } from './TactileButton';

/** Shown for an unknown `#dashboard/<page>` link instead of a blank screen. */
export function NotFound({ page = '', onHome }) {
  return (
    <SolidCard data-testid="console-not-found">
      <EmptyState
        icon={Compass}
        title="Page not found"
        description={
          page
            ? `There is no “${page}” page in the console. The link may be old or mistyped.`
            : 'This link does not match a page in the console.'
        }
        action={
          <TactileButton variant="primary" onClick={onHome}>
            Go to home
          </TactileButton>
        }
      />
    </SolidCard>
  );
}
