import React from 'react';
import { useAuth } from '../context/AuthContext';
import { ConsoleSignInRequired } from './ConsoleSignInRequired';
import { OnboardingSurveyModal } from './OnboardingSurveyModal';
import { isTourCompleted, setTourCompleted } from '../services/tourGuide';

export function ConsoleGate({ children, onSignIn, onBackToMarketing }) {
  const { isAuthenticated, isLoading, user, updateUser, refreshSession } = useAuth();

  React.useEffect(() => {
    // If the authenticated user has completed onboarding, ensure tour is marked completed
    if (user && user.hasCompletedOnboarding === true) {
      setTourCompleted(user);
    }
  }, [user]);

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
          if (isTourCompleted(user)) return;
          window.dispatchEvent(new CustomEvent('voxly:open-tour', { detail: { source: 'onboarding' } }));
        }}
      />
    );
  }

  return children;
}
