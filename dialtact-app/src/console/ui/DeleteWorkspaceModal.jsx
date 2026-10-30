import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Clock,
  Download,
  FileJson,
  Archive,
  Loader2,
  ShieldAlert,
  Trash2,
  CheckCircle2,
} from 'lucide-react';
import { Modal } from './Modal';
import { api } from '../../services/api';
import { authService } from '../../services/authService';
import { walletAmounts } from '../../lib/money';

/**
 * Destructive workspace deletion modal ("Danger Zone").
 *
 * Step 1: 14-day Quarantine Grace Period, Impact Review & Multi-Method Backups (JSON/ZIP).
 * Step 2: Reason Survey & Confirmation (Type the word "delete" — no password/OTP required).
 */
export function DeleteWorkspaceModal({ isOpen, onClose, tenantName }) {
  const [step, setStep] = useState(1);
  const [loadingPreflight, setLoadingPreflight] = useState(false);
  const [preflight, setPreflight] = useState(null);
  const [preflightError, setPreflightError] = useState(null);

  // Form states
  const [forfeitConfirmed, setForfeitConfirmed] = useState(false);
  const [confirmationName, setConfirmationName] = useState('');
  const [reason, setReason] = useState('');
  const [feedback, setFeedback] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  // Export states
  const [exportingAgents, setExportingAgents] = useState(false);
  const [exportingArchive, setExportingArchive] = useState(false);
  const [exportNotice, setExportNotice] = useState('');

  // Fetch preflight check whenever modal is opened
  useEffect(() => {
    if (!isOpen) {
      setStep(1);
      setConfirmationName('');
      setReason('');
      setFeedback('');
      setSubmitError(null);
      setForfeitConfirmed(false);
      setExportNotice('');
      setExportingAgents(false);
      setExportingArchive(false);
      return;
    }

    let active = true;
    setLoadingPreflight(true);
    setPreflightError(null);

    api.tenant
      .getDeletePreflight()
      .then((data) => {
        if (active) {
          setPreflight(data);
        }
      })
      .catch((err) => {
        if (active) setPreflightError(err?.message || 'Could not load preflight checks.');
      })
      .finally(() => {
        if (active) setLoadingPreflight(false);
      });

    return () => {
      active = false;
    };
  }, [isOpen]);

  const hasBalance =
    preflight &&
    ((preflight.walletBalanceUsd || 0) > 0 || (preflight.walletBalanceInr || 0) > 0);

  const isBlocked = preflight && preflight.blockingReasons && preflight.blockingReasons.length > 0;

  // 1. Direct JSON backup of all agents
  const handleExportAgents = async () => {
    try {
      setExportingAgents(true);
      setExportNotice('');
      await api.tenant.exportAgents();
      setExportNotice('Agent configurations successfully downloaded.');
    } catch (err) {
      setExportNotice(err?.message || 'Failed to download agent configurations.');
    } finally {
      setExportingAgents(false);
    }
  };

  // 2. Full Workspace Archive (ZIP)
  const handleExportArchive = async () => {
    try {
      setExportingArchive(true);
      setExportNotice('Queueing full workspace data takeout archive…');
      const res = await api.tenant.createExport();
      const jobId = res?.jobId;
      setExportNotice(res?.message || 'Data takeout export queued. Preparing archive…');

      if (jobId) {
        // Poll status briefly or allow direct download
        setTimeout(async () => {
          try {
            await api.tenant.downloadExportArchive(jobId);
            setExportNotice('Full workspace archive downloaded.');
          } catch {
            setExportNotice('Archive queued. You will be able to download it from the export link.');
          } finally {
            setExportingArchive(false);
          }
        }, 1500);
      } else {
        setExportingArchive(false);
      }
    } catch (err) {
      setExportNotice(err?.message || 'Could not create workspace archive.');
      setExportingArchive(false);
    }
  };

  const handleSubmitDelete = async (e) => {
    e?.preventDefault();
    if (submitting) return;

    if (confirmationName.trim().toLowerCase() !== 'delete') {
      setSubmitError('Please type "delete" to confirm workspace deletion.');
      return;
    }

    setSubmitting(true);
    setSubmitError(null);

    const fullReason = [reason, feedback].filter(Boolean).join(' - ') || 'user_requested';

    try {
      await api.tenant.deleteWorkspace({
        confirmationName: 'delete',
        reason: fullReason,
        forfeitBalanceConfirmed: forfeitConfirmed,
      });

      // Successful quarantine: sign out properly (revokes the refresh cookie too, so a
      // reload cannot silently sign back in) and land on the sign-in screen, where
      // signing in again as the owner opens the restore screen.
      if (typeof window !== 'undefined') {
        try {
          await authService.signOut();
        } catch {
          /* local session is cleared below either way */
        }
        authService.clearSession();
        sessionStorage.removeItem('dialtact_auth_token');
        localStorage.removeItem('dialtact_auth_token');
        window.location.href = '/login?notice=workspace_quarantined';
      }
    } catch (err) {
      setSubmitError(err?.message || 'Failed to delete workspace. Please try again.');
      setSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Delete workspace"
      subtitle={`Step ${step} of 2: ${step === 1 ? 'grace period and backup' : 'confirm deletion'}`}
      maxWidth="max-w-xl"
    >
      <div className="space-y-5">
        {loadingPreflight && (
          <div className="py-12 flex flex-col items-center justify-center text-center gap-3">
            <Loader2 className="w-6 h-6 animate-spin text-danger-fg" />
            <p className="text-ui text-fg-body">Checking what is in this workspace…</p>
          </div>
        )}

        {preflightError && !loadingPreflight && (
          <div className="p-4 rounded-control border border-danger-line bg-danger-soft text-danger-fg text-xs flex gap-3">
            <AlertCircle className="w-4 h-4 text-danger-fg shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">We could not check this workspace</p>
              <p className="mt-0.5 text-danger-fg">{preflightError}</p>
            </div>
          </div>
        )}

        {!loadingPreflight && !preflightError && preflight && (
          <>
            {/* ---------------- STEP 1: GRACE PERIOD & BACKUP OPTIONS ---------------- */}
            {step === 1 && (
              <div className="space-y-4">
                {isBlocked ? (
                  <div className="p-4 rounded-control border border-danger-line bg-danger-soft text-danger-fg text-xs space-y-2">
                    <div className="flex items-center gap-2 font-bold text-danger-fg">
                      <AlertCircle className="w-4 h-4 shrink-0" />
                      Deletion is currently blocked
                    </div>
                    <ul className="list-disc pl-5 space-y-1 text-danger-fg">
                      {preflight.blockingReasons.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                    <p className="text-meta text-danger-fg mt-2">
                      You must resolve these items before this workspace can be deleted.
                    </p>
                  </div>
                ) : (
                  <>
                    {/* Clear 14-day Grace Period Banner */}
                    <div className="p-3.5 rounded-control border border-warning-line bg-warning-soft text-warning-fg text-xs space-y-2">
                      <div className="flex items-center gap-2 font-bold text-warning-fg">
                        <Clock className="w-4 h-4 text-warning-fg shrink-0" />
                        <span>14-day grace period</span>
                      </div>
                      <p className="text-ui text-warning-fg">
                        When you confirm, your workspace is kept for{' '}
                        <strong>14 days</strong> before it is deleted. During that time:
                      </p>
                      <ul className="list-disc pl-5 space-y-1 text-ui text-warning-fg">
                        <li>
                          <strong>Calls stop:</strong> your agents and phone numbers stop taking and
                          making calls straight away.
                        </li>
                        <li>
                          <strong>You can change your mind:</strong> cancel the deletion and get your
                          whole workspace back at any time within 14 days.
                        </li>
                        <li>
                          <strong>Then it is gone:</strong> after 14 days, all agent prompts, call logs,
                          contacts and settings are permanently erased.
                        </li>
                      </ul>
                    </div>

                    {/* Resource Counters Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                      <div className="p-3 rounded-control bg-canvas border border-line text-center">
                        <div className="text-heading font-mono tabular-nums text-ink">{preflight.agentsCount}</div>
                        <div className="text-meta text-fg-muted">Agents</div>
                      </div>
                      <div className="p-3 rounded-control bg-canvas border border-line text-center">
                        <div className="text-heading font-mono tabular-nums text-ink">{preflight.phoneNumbersCount}</div>
                        <div className="text-meta text-fg-muted">Phone numbers</div>
                      </div>
                      <div className="p-3 rounded-control bg-canvas border border-line text-center">
                        <div className="text-heading font-mono tabular-nums text-ink">{preflight.integrationsCount || 0}</div>
                        <div className="text-meta text-fg-muted">Integrations</div>
                      </div>
                      <div className="p-3 rounded-control bg-canvas border border-line text-center">
                        <div className="text-heading font-mono tabular-nums text-ink">{preflight.activeCallsCount}</div>
                        <div className="text-meta text-fg-muted">Calls in progress</div>
                      </div>
                    </div>

                    {/* Warnings List */}
                    {preflight.warnings && preflight.warnings.length > 0 && (
                      <div className="p-3 rounded-control border border-danger-line bg-danger-soft text-danger-fg text-xs space-y-1">
                        <div className="flex items-center gap-1.5 font-bold text-danger-fg">
                          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                          <span>What will be affected</span>
                        </div>
                        <ul className="list-disc pl-5 space-y-0.5 text-danger-fg text-meta">
                          {preflight.warnings.map((warn, i) => (
                            <li key={i}>{warn}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Balance Forfeiture Confirmation Checkbox */}
                    {hasBalance && (
                      <label className="flex items-start gap-2.5 p-3 rounded-control border border-danger-line bg-danger-soft cursor-pointer text-xs">
                        <input
                          type="checkbox"
                          checked={forfeitConfirmed}
                          onChange={(e) => setForfeitConfirmed(e.target.checked)}
                          className="mt-0.5 rounded border-line text-danger-fg focus:ring-danger"
                        />
                        <span className="text-danger-fg font-medium">
                          I agree to give up my remaining wallet balance of{' '}
                          {walletAmounts({ balanceUsd: preflight.walletBalanceUsd || 0 }).primary}{' '}
                          (${(preflight.walletBalanceUsd || 0).toFixed(2)}) when the deletion is complete.
                        </span>
                      </label>
                    )}

                    {/* Multi-Method Backup & Export Section */}
                    <div className="p-3.5 rounded-control bg-canvas border border-line space-y-2.5">
                      <div>
                        <div className="text-copy font-semibold text-ink">
                          Back up your workspace
                        </div>
                        <p className="text-ui text-fg-body">
                          Before you continue, download a copy of your agents and records:
                        </p>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {/* 1. Agent Configurations JSON */}
                        <div className="p-2.5 rounded-control bg-surface border border-line flex flex-col justify-between gap-2">
                          <div className="flex items-start gap-2">
                            <FileJson className="w-4 h-4 text-accent-fg shrink-0 mt-0.5" />
                            <div>
                              <div className="text-meta font-semibold text-ink">
                                Agent settings (JSON)
                              </div>
                              <div className="text-meta text-fg-body leading-tight">
                                Prompts, voices, greetings and scripts
                              </div>
                            </div>
                          </div>
                          <button
                            type="button"
                            disabled={exportingAgents}
                            onClick={handleExportAgents}
                            className="inline-flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-control border border-line hover:border-accent bg-surface text-meta font-semibold text-ink hover:text-accent-fg transition-colors disabled:opacity-50"
                          >
                            {exportingAgents ? (
                              <>
                                <Loader2 className="w-3 h-3 animate-spin" />
                                Downloading…
                              </>
                            ) : (
                              <>
                                <Download className="w-3 h-3 text-accent-fg" />
                                Download JSON
                              </>
                            )}
                          </button>
                        </div>

                        {/* 2. Full Workspace Archive ZIP */}
                        <div className="p-2.5 rounded-control bg-surface border border-line flex flex-col justify-between gap-2">
                          <div className="flex items-start gap-2">
                            <Archive className="w-4 h-4 text-success-fg shrink-0 mt-0.5" />
                            <div>
                              <div className="text-meta font-semibold text-ink">
                                Full archive (ZIP)
                              </div>
                              <div className="text-meta text-fg-body leading-tight">
                                Call logs (CSV), contacts, invoices and agents
                              </div>
                            </div>
                          </div>
                          <button
                            type="button"
                            disabled={exportingArchive}
                            onClick={handleExportArchive}
                            className="inline-flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-control border border-line hover:border-success bg-surface text-meta font-semibold text-ink hover:text-success-fg transition-colors disabled:opacity-50"
                          >
                            {exportingArchive ? (
                              <>
                                <Loader2 className="w-3 h-3 animate-spin" />
                                Exporting…
                              </>
                            ) : (
                              <>
                                <Download className="w-3 h-3 text-success-fg" />
                                Export Takeout
                              </>
                            )}
                          </button>
                        </div>
                      </div>

                      {exportNotice && (
                        <p className="text-meta font-medium text-success-fg bg-success-soft border border-success-line rounded-control px-2.5 py-1.5 flex items-center gap-1.5">
                          <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-success-fg" />
                          <span>{exportNotice}</span>
                        </p>
                      )}
                    </div>
                  </>
                )}

                <div className="flex justify-end gap-2 pt-2 border-t border-line">
                  <button
                    type="button"
                    onClick={onClose}
                    className="min-h-[40px] px-4 py-2 rounded-control text-ui font-semibold text-fg-body hover:text-ink hover:bg-canvas transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={isBlocked || (hasBalance && !forfeitConfirmed)}
                    onClick={() => setStep(2)}
                    className="inline-flex min-h-[40px] items-center gap-1.5 px-4 py-2 rounded-control text-ui font-semibold text-white bg-danger-fg hover:bg-danger disabled:opacity-50 transition-colors shadow-craft-xs"
                  >
                    Proceed to Confirmation
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}

            {/* ---------------- STEP 2: REASON & TYPE "delete" ---------------- */}
            {step === 2 && (
              <form onSubmit={handleSubmitDelete} className="space-y-4">
                <div className="p-3.5 rounded-control border border-danger-line bg-danger-soft text-danger-fg text-xs space-y-1">
                  <div className="flex items-center gap-1.5 font-bold text-danger-fg">
                    <ShieldAlert className="w-4 h-4 text-danger-fg shrink-0" />
                    <span>Confirm deletion</span>
                  </div>
                  <p className="text-ui text-danger-fg">
                    Tell us why you are leaving and type the word <strong>delete</strong> below to start
                    the 14-day grace period.
                  </p>
                </div>

                {submitError && (
                  <p className="text-meta font-medium text-danger-fg bg-danger-soft border border-danger-line rounded-control px-3 py-2 flex items-center gap-1.5">
                    <AlertCircle className="w-3.5 h-3.5 shrink-0 text-danger-fg" />
                    <span>{submitError}</span>
                  </p>
                )}

                {/* Reason survey */}
                <div>
                  <label htmlFor="delete-reason" className="block text-ui font-medium text-ink mb-1">
                    Why are you deleting this workspace?
                  </label>
                  <select
                    id="delete-reason"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    required
                    className="w-full text-base sm:text-ui px-3.5 py-2.5 rounded-control bg-surface border border-line focus:outline-none focus:border-accent text-ink"
                  >
                    <option value="">Select a reason…</option>
                    <option value="pricing">Too expensive</option>
                    <option value="missing_features">Missing required features</option>
                    <option value="switched_providers">Switching to another provider</option>
                    <option value="project_completed">Project or trial completed</option>
                    <option value="setup_complexity">Difficult to configure</option>
                    <option value="other">Other reason</option>
                  </select>
                </div>

                {/* Optional additional notes */}
                <div>
                  <label htmlFor="delete-feedback" className="block text-ui font-medium text-ink mb-1">
                    Additional feedback (optional)
                  </label>
                  <textarea
                    id="delete-feedback"
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                    placeholder="Tell us what we could have done better…"
                    rows={2}
                    className="w-full text-base sm:text-ui px-3.5 py-2 rounded-control bg-surface border border-line focus:outline-none focus:border-accent text-ink resize-none"
                  />
                </div>

                {/* Confirmation input: Type "delete" */}
                <div>
                  <label htmlFor="confirm-delete-word" className="block text-ui font-medium text-ink mb-1">
                    Type the word <span className="text-danger-fg font-bold">delete</span> to confirm
                  </label>
                  <input
                    id="confirm-delete-word"
                    type="text"
                    value={confirmationName}
                    onChange={(e) => setConfirmationName(e.target.value)}
                    placeholder="delete"
                    autoFocus
                    className="w-full text-base sm:text-ui px-3.5 py-2.5 rounded-control bg-surface border border-line focus:outline-none focus:border-danger text-ink font-mono"
                  />
                </div>

                <div className="flex justify-between items-center pt-2 border-t border-line">
                  <button
                    type="button"
                    onClick={() => setStep(1)}
                    disabled={submitting}
                    className="inline-flex min-h-[40px] items-center gap-1.5 px-3 py-2 rounded-control text-ui font-semibold text-fg-body hover:text-ink hover:bg-canvas transition-colors"
                  >
                    <ArrowLeft className="w-3.5 h-3.5" />
                    Back
                  </button>
                  <button
                    type="submit"
                    disabled={
                      submitting ||
                      confirmationName.trim().toLowerCase() !== 'delete' ||
                      !reason
                    }
                    className="inline-flex min-h-[40px] items-center gap-1.5 px-5 py-2.5 rounded-control text-ui font-semibold text-white bg-danger-fg hover:bg-danger disabled:opacity-50 transition-colors shadow-craft-xs"
                  >
                    {submitting ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        Quarantining workspace…
                      </>
                    ) : (
                      <>
                        <Trash2 className="w-3.5 h-3.5" />
                        Delete Workspace
                      </>
                    )}
                  </button>
                </div>
              </form>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}
