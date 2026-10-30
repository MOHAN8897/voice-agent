import React, { useState, useEffect } from 'react';
import { ShieldCheck, AlertCircle } from 'lucide-react';
import { Modal } from './Modal';
import { TactileButton } from './TactileButton';

/**
 * CampaignComplianceModal
 * Required consent confirmation before launching any bulk calling campaign.
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
      title="Confirm calling consent for India"
      subtitle={campaignName ? `Check the legal requirements for “${campaignName}”` : 'Confirm you are allowed to call these contacts'}
      maxWidth="max-w-xl"
    >
      <div className="space-y-5">
        <div className="flex items-center gap-3 rounded-control border border-line bg-canvas p-3.5">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-control bg-accent-soft text-accent-fg" aria-hidden="true">
            <ShieldCheck className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <h3 className="text-ui font-semibold text-ink">Check consent and calling preferences</h3>
            <p className="text-meta text-fg-body">
              {contactCount > 0 ? (
                <>
                  <span className="font-mono tabular-nums">{contactCount.toLocaleString('en-IN')}</span> contact{contactCount === 1 ? '' : 's'} ready to call
                </>
              ) : 'Campaign calls'}
            </p>
          </div>
        </div>

        <div className="space-y-3.5 rounded-control border border-line bg-canvas p-4 text-ui leading-relaxed text-ink sm:text-copy">
          <p>
            &ldquo;I confirm that I have valid consent or another permitted basis for these commercial calls, have checked recipient preferences through the authorised DND/consent process, and will honour opt-outs under TRAI's TCCCPR framework.&rdquo;
          </p>
          <p>
            &ldquo;My business has completed applicable sender registration and calling route requirements. I am responsible for the contact list, purpose, caller identity, recording notice and lawful handling of caller data.&rdquo;
          </p>
        </div>

        <div className="flex items-start gap-2.5 rounded-control border border-warning-line bg-warning-soft p-3 text-meta text-warning-fg">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>
            <strong className="font-semibold">Before launch:</strong> your own do-not-call list does not check national DND or consent records. This confirmation records that you have checked; it does not certify your campaign. Calls outside India also need checking against that country's rules.
          </p>
        </div>

        <label className="flex cursor-pointer select-none items-start gap-3 rounded-control border border-line p-3.5 transition-colors hover:bg-canvas">
          <input
            id="compliance-attestation-checkbox"
            data-testid="compliance-attestation-checkbox"
            type="checkbox"
            checked={accepted}
            onChange={(e) => setAccepted(e.target.checked)}
            disabled={isSubmitting}
            className="mt-0.5 h-4 w-4 accent-accent"
          />
          <span className="text-ui font-medium text-ink sm:text-copy">
            I have reviewed these requirements and confirm
          </span>
        </label>

        <div className="flex flex-wrap items-center justify-end gap-3 pt-2">
          <TactileButton type="button" variant="ghost" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </TactileButton>
          <TactileButton
            type="button"
            id="confirm-launch-campaign-btn"
            data-testid="confirm-launch-campaign-btn"
            onClick={handleConfirm}
            disabled={!accepted || isSubmitting}
          >
            {isSubmitting ? 'Launching…' : 'Confirm and launch campaign'}
          </TactileButton>
        </div>
      </div>
    </Modal>
  );
}
