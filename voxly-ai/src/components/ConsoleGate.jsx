import React from 'react';
import { useAuth } from '../context/AuthContext';
import { ConsoleSignInRequired } from './ConsoleSignInRequired';
import { OnboardingSurveyModal } from './OnboardingSurveyModal';
import { isTourCompleted, setTourCompleted } from '../services/tourGuide';

export function ConsoleGate({ children, onSignIn, onBackToMarketing }) {
  const { isAuthenticated, isLoading, user, updateUser, refreshSession } = useAuth();

  // Auto-launch guided tour for new users entering the console for the first time
  React.useEffect(() => {
    if (isAuthenticated && user && user.hasCompletedOnboarding === true && !isTourCompleted(user)) {
      const timer = setTimeout(() => {
        if (!isTourCompleted(user)) {
          window.dispatchEvent(
            new CustomEvent('dialtact:open-tour', { detail: { source: 'first_time_entry' } })
          );
          window.dispatchEvent(
            new CustomEvent('voxly:open-tour', { detail: { source: 'first_time_entry' } })
          );
        }
      }, 750);
      return () => clearTimeout(timer);
    }
  }, [isAuthenticated, user]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#FAF9FD] text-sm text-[#524E5E]">
        Checking session…
      </div>
    );
  }

  if (!isAuthenticated) {
    return <ConsoleSignInRequired onSignIn={onSignIn} onBackToMarketing={onBackToMarketing} />;
  }

  // Intercept user if onboarding survey is pending
  if (user && user.hasCompletedOnboarding === false) {
    return (
      <OnboardingSurveyModal
        user={user}
        onComplete={(surveyData) => {
          updateUser?.({
            hasCompletedOnboarding: true,
            name: surveyData?.fullName || user.name,
            tenantName: surveyData?.companyName || user.tenantName,
          });
          refreshSession?.().catch(() => {});
        }}
        onStartTour={() => {
          window.dispatchEvent(
            new CustomEvent('dialtact:open-tour', { detail: { source: 'onboarding', force: true } })
          );
          window.dispatchEvent(
            new CustomEvent('voxly:open-tour', { detail: { source: 'onboarding', force: true } })
          );
        }}
      />
    );
  }

  return children;
}
