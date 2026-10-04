import React, { useState } from 'react';
import {
  Sparkles,
  Building2,
  Target,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  ArrowLeft,
  Headphones,
  Rocket,
  Calendar,
  Filter,
  Layers,
  ShieldCheck,
  Compass,
  Check,
} from 'lucide-react';
import { api } from '../services/api';
import { showToast } from '../console/ui/ToastHost';

const ROLE_OPTIONS = [
  { value: 'founder', label: 'Founder / Executive' },
  { value: 'sales_leader', label: 'Sales / Growth Leader' },
  { value: 'support_lead', label: 'Support / Operations' },
  { value: 'engineering', label: 'Product / Engineer' },
  { value: 'other', label: 'Other' },
];

const REFERRAL_OPTIONS = [
  { value: 'search', label: 'Search Engine (Google)' },
  { value: 'social', label: 'LinkedIn / X (Twitter)' },
  { value: 'colleague', label: 'Referral / Colleague' },
  { value: 'podcast_video', label: 'YouTube / Podcast' },
  { value: 'other', label: 'Other' },
];

const USE_CASE_OPTIONS = [
  {
    value: 'inbound_support',
    label: 'Inbound Support',
    description: '24/7 autonomous call answering & patient / customer FAQ resolution',
    icon: Headphones,
  },
  {
    value: 'outbound_sales',
    label: 'Outbound Sales',
    description: 'High-volume lead follow-ups, warm outreach & instant meeting booking',
    icon: Rocket,
  },
  {
    value: 'reminders_scheduling',
    label: 'Appointment Reminders',
    description: 'Automated booking confirmations, calendar sync & reschedule flows',
    icon: Calendar,
  },
  {
    value: 'lead_qualification',
    label: 'Lead Qualification',
    description: 'Screening prospective inquiries and scoring buyer intent in real-time',
    icon: Filter,
  },
  {
    value: 'other',
    label: 'Other Custom Workflows',
    description: 'Tailored telephony routines, survey collection & alerts',
    icon: Layers,
  },
];

const VOLUME_OPTIONS = [
  { value: 'under_500', label: 'Under 500 min / mo', tier: 'Starter tier' },
  { value: '500_to_2500', label: '500 – 2,500 min / mo', tier: 'Growth tier' },
  { value: '2500_to_10000', label: '2,500 – 10,000 min / mo', tier: 'Scale tier' },
  { value: '10000_plus', label: '10,000+ min / mo', tier: 'Enterprise tier' },
];

/**
 * OnboardingSurveyModal
 * Multi-step onboarding questionnaire with visual tactile cards and guided tour kickoff.
 */
export function OnboardingSurveyModal({ user, onComplete, onStartTour }) {
  const [step, setStep] = useState(1);
  const [fullName, setFullName] = useState(user?.name || user?.fullName || '');
  const [companyName, setCompanyName] = useState(user?.tenantName || user?.companyName || '');
  const [role, setRole] = useState(ROLE_OPTIONS[0].value);
  const [referralSource, setReferralSource] = useState(REFERRAL_OPTIONS[0].value);
  const [primaryUseCase, setPrimaryUseCase] = useState(USE_CASE_OPTIONS[0].value);
  const [estimatedMonthlyMinutes, setEstimatedMonthlyMinutes] = useState(VOLUME_OPTIONS[0].value);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [completedData, setCompletedData] = useState(null);

  const canAdvanceStep1 = fullName.trim().length >= 2 && companyName.trim().length >= 2;
  const canAdvanceStep2 = Boolean(referralSource && primaryUseCase && estimatedMonthlyMinutes);
  const canSubmit = termsAccepted && !isSubmitting;

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!canSubmit) return;
    setIsSubmitting(true);
    setError(null);

    const payload = {
      fullName: fullName.trim(),
      companyName: companyName.trim(),
      role,
      referralSource,
      primaryUseCase,
      estimatedMonthlyMinutes,
      termsAccepted: true,
      termsVersion: '2026-10-v1',
      acceptableUseVersion: '2026-10-v1',
    };

    try {
      await api.auth.submitOnboardingSurvey(payload);
      showToast('Welcome to Voxly! Your workspace is ready.', 'success');
      onComplete?.(payload);
      onStartTour?.();
    } catch (err) {
      setError(err?.message || 'Could not save onboarding survey.');
      showToast(err?.message || 'Could not save onboarding survey.', 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleFinishToConsole = () => {
    onComplete?.(completedData);
  };

  const handleFinishWithTour = () => {
    onComplete?.(completedData);
    onStartTour?.();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="onboarding-survey-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 overflow-y-auto"
      data-testid="onboarding-survey-modal"
    >
      {/* Backdrop */}
      <div className="fixed inset-0 bg-[#0F0E17]/75 backdrop-blur-md transition-opacity" />

      {/* Card container */}
      <div className="relative w-full max-w-xl bg-white border border-[#E4E2EB] rounded-2xl sm:rounded-3xl shadow-2xl z-10 overflow-hidden my-auto p-5 sm:p-8 space-y-6">
        {/* Header with Step indicator */}
        <div className="flex items-center justify-between border-b border-[#E4E2EB] pb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#FF5C35]/10 flex items-center justify-center text-[#FF5C35]">
              <Sparkles className="w-5 h-5 text-[#FF5C35]" />
            </div>
            <div>
              <h2 id="onboarding-survey-title" className="text-base sm:text-lg font-bold text-[#0F0E17]">
                Welcome to Voxly
              </h2>
              <p className="text-xs text-[#524E5E]">Configure your autonomous voice workspace</p>
            </div>
          </div>
          {step <= 3 && (
            <div className="text-xs font-semibold px-2.5 py-1 rounded-full bg-[#FAF9FD] border border-[#E4E2EB] text-[#524E5E]">
              Step {step} of 3
            </div>
          )}
        </div>

        {/* Step Progress Tracker */}
        {step <= 3 && (
          <div className="grid grid-cols-3 gap-2">
            {[
              { num: 1, label: 'Profile' },
              { num: 2, label: 'Strategy' },
              { num: 3, label: 'Compliance' },
            ].map((s) => (
              <div key={s.num} className="space-y-1">
                <div
                  className={`h-1.5 rounded-full transition-all duration-300 ${
                    s.num === step
                      ? 'bg-[#FF5C35]'
                      : s.num < step
                      ? 'bg-[#0F0E17]'
                      : 'bg-[#E4E2EB]'
                  }`}
                />
                <span
                  className={`text-[10px] font-semibold uppercase tracking-wider block ${
                    s.num === step ? 'text-[#FF5C35]' : s.num < step ? 'text-[#0F0E17]' : 'text-[#8E8B99]'
                  }`}
                >
                  {s.label}
                </span>
              </div>
            ))}
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 p-3 text-xs bg-red-50 border border-red-200 text-red-800 rounded-xl">
            <AlertCircle className="w-4 h-4 shrink-0 text-red-600" />
            <span>{error}</span>
          </div>
        )}

        {/* Step 1: Your Role & Business */}
        {step === 1 && (
          <div className="space-y-4" data-testid="onboarding-step-1">
            <div className="flex items-center gap-2 text-xs font-bold text-[#0F0E17]">
              <Building2 className="w-4 h-4 text-[#FF5C35]" />
              <h3>Your Profile &amp; Organization</h3>
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#0F0E17] mb-1">
                Your full name
              </label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="e.g. John Doe"
                data-testid="onboarding-fullname-input"
                className="w-full text-xs sm:text-sm px-3.5 py-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] focus:outline-none focus:border-[#FF5C35] text-[#0F0E17]"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#0F0E17] mb-1">
                Company or workspace name
              </label>
              <input
                type="text"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder="e.g. Acme Health Inc"
                data-testid="onboarding-company-input"
                className="w-full text-xs sm:text-sm px-3.5 py-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] focus:outline-none focus:border-[#FF5C35] text-[#0F0E17]"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-[#0F0E17] mb-2">
                What is your primary role?
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {ROLE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setRole(opt.value)}
                    className={`p-2.5 rounded-xl text-left text-xs font-semibold border transition-all ${
                      role === opt.value
                        ? 'bg-[#0F0E17] text-white border-[#0F0E17] shadow-xs'
                        : 'bg-[#FAF9FD] text-[#524E5E] border-[#E4E2EB] hover:bg-white hover:border-[#D1CFDB]'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
              {/* Keep underlying select for backward compatibility & testids */}
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                data-testid="onboarding-role-select"
                className="sr-only"
                aria-hidden="true"
                tabIndex={-1}
              >
                {ROLE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        {/* Step 2: Platform Strategy with Rich Visual Cards */}
        {step === 2 && (
          <div className="space-y-4" data-testid="onboarding-step-2">
            <div className="flex items-center gap-2 text-xs font-bold text-[#0F0E17]">
              <Target className="w-4 h-4 text-[#FF5C35]" />
              <h3>Calling Objectives &amp; Scale</h3>
            </div>

            {/* Primary Use Case Visual Cards */}
            <div>
              <label className="block text-xs font-semibold text-[#0F0E17] mb-2">
                What will you build first?
              </label>
              <div className="space-y-2">
                {USE_CASE_OPTIONS.map((opt) => {
                  const Icon = opt.icon;
                  const isSelected = primaryUseCase === opt.value;
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => setPrimaryUseCase(opt.value)}
                      className={`w-full p-3 rounded-xl border text-left flex items-start gap-3 transition-all ${
                        isSelected
                          ? 'bg-[#FAF9FD] border-[#FF5C35] shadow-xs ring-1 ring-[#FF5C35]/20'
                          : 'bg-white border-[#E4E2EB] hover:bg-[#FAF9FD]'
                      }`}
                    >
                      <div
                        className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-colors ${
                          isSelected ? 'bg-[#FF5C35] text-white' : 'bg-[#FAF9FD] text-[#524E5E]'
                        }`}
                      >
                        <Icon className="w-4 h-4" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-[#0F0E17]">{opt.label}</span>
                          {isSelected && <Check className="w-3.5 h-3.5 text-[#FF5C35]" />}
                        </div>
                        <p className="text-[11px] text-[#524E5E] leading-snug mt-0.5">
                          {opt.description}
                        </p>
                      </div>
                    </button>
                  );
                })}
              </div>
              <select
                value={primaryUseCase}
                onChange={(e) => setPrimaryUseCase(e.target.value)}
                data-testid="onboarding-usecase-select"
                className="sr-only"
                aria-hidden="true"
                tabIndex={-1}
              >
                {USE_CASE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Monthly Minutes Volume */}
            <div>
              <label className="block text-xs font-semibold text-[#0F0E17] mb-2">
                Anticipated monthly call volume
              </label>
              <div className="grid grid-cols-2 gap-2">
                {VOLUME_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setEstimatedMonthlyMinutes(opt.value)}
                    className={`p-2.5 rounded-xl border text-left transition-all ${
                      estimatedMonthlyMinutes === opt.value
                        ? 'bg-[#0F0E17] text-white border-[#0F0E17]'
                        : 'bg-[#FAF9FD] border-[#E4E2EB] text-[#524E5E] hover:bg-white'
                    }`}
                  >
                    <div className="text-xs font-bold">{opt.label}</div>
                    <div
                      className={`text-[10px] ${
                        estimatedMonthlyMinutes === opt.value ? 'text-gray-300' : 'text-[#8E8B99]'
                      }`}
                    >
                      {opt.tier}
                    </div>
                  </button>
                ))}
              </div>
              <select
                value={estimatedMonthlyMinutes}
                onChange={(e) => setEstimatedMonthlyMinutes(e.target.value)}
                data-testid="onboarding-volume-select"
                className="sr-only"
                aria-hidden="true"
                tabIndex={-1}
              >
                {VOLUME_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* How did you hear about Voxly */}
            <div>
              <label className="block text-xs font-semibold text-[#0F0E17] mb-1">
                How did you hear about us?
              </label>
              <select
                value={referralSource}
                onChange={(e) => setReferralSource(e.target.value)}
                data-testid="onboarding-referral-select"
                className="w-full text-xs sm:text-sm px-3.5 py-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] focus:outline-none focus:border-[#FF5C35] text-[#0F0E17]"
              >
                {REFERRAL_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        {/* Step 3: Terms & Acceptable Use */}
        {step === 3 && (
          <div className="space-y-4" data-testid="onboarding-step-3">
            <div className="flex items-center gap-2 text-xs font-bold text-[#0F0E17]">
              <ShieldCheck className="w-4 h-4 text-[#FF5C35]" />
              <h3>Compliance &amp; Acceptable Telephony Use</h3>
            </div>

            <div className="space-y-2 text-xs text-[#524E5E] bg-[#FAF9FD] p-4 rounded-xl border border-[#E4E2EB] leading-relaxed">
              <div className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                <span>
                  <strong>National DND Compliance:</strong> Automated scrubbing against national Do-Not-Call registries protects operators from unsolicited dialing violations.
                </span>
              </div>
              <div className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                <span>
                  <strong>Calling Hours &amp; TCPA:</strong> Autonomous outbound calls are strictly constrained to 9:00 AM – 9:00 PM recipient local time.
                </span>
              </div>
              <div className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                <span>
                  <strong>Caller ID &amp; Anti-Spam:</strong> Unsolicited spam, robocalling without consent, and caller ID spoofing are strictly prohibited.
                </span>
              </div>
            </div>

            {/* Mandatory Checkbox (Unchecked by default) */}
            <label className="flex items-start gap-3 p-3.5 rounded-xl border border-[#E4E2EB] hover:bg-[#FAF9FD] transition-colors cursor-pointer select-none">
              <input
                id="onboarding-terms-checkbox"
                type="checkbox"
                checked={termsAccepted}
                onChange={(e) => setTermsAccepted(e.target.checked)}
                disabled={isSubmitting}
                data-testid="onboarding-terms-checkbox"
                className="mt-0.5 w-4 h-4 rounded text-[#FF5C35] focus:ring-[#FF5C35] border-[#D1CFDB]"
              />
              <span className="text-xs sm:text-sm font-medium text-[#0F0E17]">
                I agree to the Terms of Service, Privacy Policy, and Anti-Spam / Telephony Acceptable Use Policy.
              </span>
            </label>
          </div>
        )}

        {/* Step 4: Celebration & Guided Tour Choice */}
        {step === 4 && (
          <div className="text-center py-4 space-y-5" data-testid="onboarding-success-step">
            <div className="w-16 h-16 rounded-2xl bg-emerald-50 text-emerald-600 border border-emerald-200 flex items-center justify-center mx-auto shadow-sm">
              <Sparkles className="w-8 h-8 text-emerald-600 animate-bounce" />
            </div>

            <div className="space-y-1">
              <h3 className="text-xl font-extrabold text-[#0F0E17]">
                Workspace Created Successfully!
              </h3>
              <p className="text-xs text-[#524E5E] max-w-sm mx-auto">
                Welcome, <strong>{fullName}</strong>. Your dedicated voice telephony workspace for{' '}
                <strong>{companyName}</strong> is fully active.
              </p>
            </div>

            <div className="p-4 rounded-2xl bg-[#FAF9FD] border border-[#E4E2EB] text-left space-y-3">
              <div className="flex items-center gap-2.5">
                <Compass className="w-5 h-5 text-[#FF5C35]" />
                <div>
                  <h4 className="text-xs font-bold text-[#0F0E17]">
                    Take a 60-Second Guided Tour?
                  </h4>
                  <p className="text-[11px] text-[#524E5E]">
                    See how prompts, neural Telugu voices, phone channels, and DND campaigns work.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                <button
                  type="button"
                  onClick={handleFinishWithTour}
                  data-testid="onboarding-tour-accept-btn"
                  className="inline-flex items-center justify-center gap-2 py-3 px-4 rounded-xl text-xs font-semibold text-white bg-[#FF5C35] hover:bg-[#e04f2c] transition-colors shadow-sm"
                >
                  <Compass className="w-4 h-4" />
                  <span>Start Guided Tour</span>
                </button>
                <button
                  type="button"
                  onClick={handleFinishToConsole}
                  data-testid="onboarding-tour-skip-btn"
                  className="inline-flex items-center justify-center gap-2 py-3 px-4 rounded-xl text-xs font-semibold text-[#0F0E17] bg-white hover:bg-gray-50 border border-[#E4E2EB] transition-colors"
                >
                  <span>Go to Console</span>
                  <ArrowRight className="w-3.5 h-3.5 text-[#524E5E]" />
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Navigation Buttons for Steps 1-3 */}
        {step <= 3 && (
          <div className="flex items-center justify-between pt-3 border-t border-[#E4E2EB]">
            {step > 1 ? (
              <button
                type="button"
                onClick={() => { setStep((s) => s - 1); setError(null); }}
                disabled={isSubmitting}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD] rounded-xl transition-colors border border-transparent hover:border-[#E4E2EB]"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                Back
              </button>
            ) : (
              <div />
            )}

            {step < 3 ? (
              <button
                type="button"
                onClick={() => { setStep((s) => s + 1); setError(null); }}
                disabled={step === 1 ? !canAdvanceStep1 : !canAdvanceStep2}
                data-testid="onboarding-next-btn"
                className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-xs font-semibold text-white bg-[#0F0E17] hover:bg-[#232130] transition-colors disabled:opacity-50"
              >
                Next
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!canSubmit}
                data-testid="onboarding-submit-btn"
                className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-xs font-semibold text-white bg-[#FF5C35] hover:bg-[#e04f2c] transition-colors disabled:opacity-50"
              >
                {isSubmitting ? 'Finalizing Setup...' : 'Complete & Setup Workspace'}
                <CheckCircle2 className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
