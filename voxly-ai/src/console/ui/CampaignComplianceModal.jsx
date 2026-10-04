import React, { useState, useEffect } from 'react';
import { ShieldCheck, AlertCircle } from 'lucide-react';
import { Modal } from './Modal';
import { TactileButton } from './TactileButton';

/**
 * CampaignComplianceModal
 * Required compliance attestation dialog before launching any bulk voice campaign.
 * Mandates explicit affirmative consent representation per regulatory standards.
 */
export function CampaignComplianceModal({
  isOpen,
  onClose,
  onConfirm,
  campaignName = '',
  contactCount = 0,
  isSubmitting = false,
}) {
  const [accepted, setAccepted] = useState(false);

  // Reset checkbox state whenever modal is opened
  useEffect(() => {
    if (isOpen) {
      setAccepted(false);
    }
  }, [isOpen]);

  const handleConfirm = () => {
    if (!accepted || isSubmitting) return;
    onConfirm();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Campaign Compliance Confirmation"
      subtitle={campaignName ? `Review legal requirements for "${campaignName}"` : 'Attestation of legal calling consent'}
      maxWidth="max-w-xl"
    >
      <div className="space-y-5">
        {/* Shield Icon Header Badge */}
        <div className="flex items-center gap-3 p-3.5 bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl">
          <div className="w-10 h-10 rounded-lg bg-[#FF5C35]/10 text-[#FF5C35] flex items-center justify-center shrink-0">
            <ShieldCheck className="w-5 h-5 text-[#FF5C35]" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-[#0F0E17]">
              Regulatory Attestation Required
            </h3>
            <p className="text-xs text-[#524E5E]">
              {contactCount > 0 ? `${contactCount} contact${contactCount === 1 ? '' : 's'} queued for outbound dialing` : 'Outbound campaign dispatch'}
            </p>
          </div>
        </div>

        {/* Attestation Body */}
        <div className="space-y-3.5 text-xs sm:text-sm text-[#2D2A38] bg-[#F7F6FA] p-4 rounded-xl border border-[#E9E7F0] leading-relaxed">
          <p>
            &ldquo;I confirm that I have the necessary authorization/consent to contact the phone numbers used in this campaign and that my campaign complies with applicable laws and regulations.&rdquo;
          </p>
          <p>
            &ldquo;I understand that I am responsible for the contacts, purpose, content, and legality of the calls made through Voxly.&rdquo;
          </p>
        </div>

        {/* Clarifying Disclaimer Note */}
        <div className="flex items-start gap-2.5 text-xs text-[#645D73] bg-amber-500/5 p-3 rounded-xl border border-amber-500/20">
          <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <p>
            <strong className="text-[#0F0E17]">Notice:</strong> Voxly provides automated telephony infrastructure and does not verify or guarantee the legal validity of your contact lists. You are making this representation as the operating tenant.
          </p>
        </div>

        {/* Mandatory Affirmative Consent Checkbox */}
        <label className="flex items-start gap-3 p-3.5 rounded-xl border border-[#E4E2EB] hover:bg-[#FAF9FD] transition-colors cursor-pointer select-none">
          <input
            id="compliance-attestation-checkbox"
            data-testid="compliance-attestation-checkbox"
            type="checkbox"
            checked={accepted}
            onChange={(e) => setAccepted(e.target.checked)}
            disabled={isSubmitting}
            className="mt-0.5 w-4 h-4 rounded text-[#FF5C35] focus:ring-[#FF5C35] border-[#D1CFDB]"
          />
          <span className="text-xs sm:text-sm font-medium text-[#0F0E17]">
            I confirm and accept
          </span>
        </label>

        {/* Action Buttons */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="px-4 py-2 text-xs sm:text-sm font-medium text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD] rounded-xl transition-colors border border-transparent hover:border-[#E4E2EB]"
          >
            Cancel
          </button>
          <TactileButton
            type="button"
            id="confirm-launch-campaign-btn"
            data-testid="confirm-launch-campaign-btn"
            onClick={handleConfirm}
            disabled={!accepted || isSubmitting}
            className="!px-5 !py-2.5 text-xs sm:text-sm"
          >
            {isSubmitting ? 'Launching...' : 'Confirm & Launch Campaign'}
          </TactileButton>
        </div>
      </div>
    </Modal>
  );
}
