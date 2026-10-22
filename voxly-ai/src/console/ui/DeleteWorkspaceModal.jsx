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

      // Successful quarantine: clear session tokens and redirect to login
      if (typeof window !== 'undefined') {
        sessionStorage.removeItem('voxly_auth_token');
        localStorage.removeItem('voxly_auth_token');
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
      title="Delete Workspace"
      subtitle={`Step ${step} of 2 — ${step === 1 ? 'Grace period & workspace backup' : 'Confirm deletion'}`}
      maxWidth="max-w-xl"
    >
      <div className="p-5 sm:p-6 space-y-5">
        {loadingPreflight && (
          <div className="py-12 flex flex-col items-center justify-center text-center gap-3">
            <Loader2 className="w-6 h-6 animate-spin text-rose-600" />
            <p className="text-xs text-[#524E5E]">Checking workspace resources and active services…</p>
          </div>
        )}

        {preflightError && !loadingPreflight && (
          <div className="p-4 rounded-xl border border-rose-200 bg-rose-50 text-rose-900 text-xs flex gap-3">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">Unable to run preflight check</p>
              <p className="mt-0.5 text-rose-800">{preflightError}</p>
            </div>
          </div>
        )}

        {!loadingPreflight && !preflightError && preflight && (
          <>
            {/* ---------------- STEP 1: GRACE PERIOD & BACKUP OPTIONS ---------------- */}
            {step === 1 && (
              <div className="space-y-4">
                {isBlocked ? (
                  <div className="p-4 rounded-xl border border-rose-200 bg-rose-50 text-rose-950 text-xs space-y-2">
                    <div className="flex items-center gap-2 font-bold text-rose-700">
                      <AlertCircle className="w-4 h-4 shrink-0" />
                      Deletion is currently blocked
                    </div>
                    <ul className="list-disc pl-5 space-y-1 text-rose-900">
                      {preflight.blockingReasons.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                    <p className="text-[11px] text-rose-800 mt-2">
                      You must resolve these items before this workspace can be deleted.
                    </p>
                  </div>
                ) : (
                  <>
                    {/* Clear 14-day Grace Period Banner */}
                    <div className="p-3.5 rounded-xl border border-amber-200 bg-amber-50/70 text-amber-950 text-xs space-y-2">
                      <div className="flex items-center gap-2 font-bold text-amber-900">
                        <Clock className="w-4 h-4 text-amber-700 shrink-0" />
                        <span>14-Day Quarantine Grace Period</span>
                      </div>
                      <p className="text-[11px] text-amber-900 leading-relaxed">
                        When you confirm deletion, your workspace enters a{' '}
                        <strong>14-day safety grace period</strong>. During this window:
                      </p>
                      <ul className="list-disc pl-5 space-y-1 text-[11px] text-amber-900">
                        <li>
                          <strong>Calls are paused:</strong> Voice assistants and telephony trunks are
                          deactivated immediately.
                        </li>
                        <li>
                          <strong>1-Click Restoration:</strong> You can cancel deletion and reactivate
                          your entire workspace at any time within 14 days.
                        </li>
                        <li>
                          <strong>Permanent Purge:</strong> After 14 days, all voice prompts, call logs,
                          contacts, and configurations are permanently erased.
                        </li>
                      </ul>
                    </div>

                    {/* Resource Counters Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                      <div className="p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-center">
                        <div className="text-lg font-bold text-[#0F0E17]">{preflight.agentsCount}</div>
                        <div className="text-[10px] text-[#524E5E] font-medium">Voice Agents</div>
                      </div>
                      <div className="p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-center">
                        <div className="text-lg font-bold text-[#0F0E17]">{preflight.phoneNumbersCount}</div>
                        <div className="text-[10px] text-[#524E5E] font-medium">Phone Numbers</div>
                      </div>
                      <div className="p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-center">
                        <div className="text-lg font-bold text-[#0F0E17]">{preflight.integrationsCount || 0}</div>
                        <div className="text-[10px] text-[#524E5E] font-medium">Integrations</div>
                      </div>
                      <div className="p-3 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] text-center">
                        <div className="text-lg font-bold text-[#0F0E17]">{preflight.activeCallsCount}</div>
                        <div className="text-[10px] text-[#524E5E] font-medium">Active Calls</div>
                      </div>
                    </div>

                    {/* Warnings List */}
                    {preflight.warnings && preflight.warnings.length > 0 && (
                      <div className="p-3 rounded-xl border border-rose-200 bg-rose-50/50 text-rose-950 text-xs space-y-1">
                        <div className="flex items-center gap-1.5 font-bold text-rose-800">
                          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                          <span>Resources Affected</span>
                        </div>
                        <ul className="list-disc pl-5 space-y-0.5 text-rose-900 text-[11px]">
                          {preflight.warnings.map((warn, i) => (
                            <li key={i}>{warn}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Balance Forfeiture Confirmation Checkbox */}
                    {hasBalance && (
                      <label className="flex items-start gap-2.5 p-3 rounded-xl border border-rose-200 bg-rose-50/60 cursor-pointer text-xs">
                        <input
                          type="checkbox"
                          checked={forfeitConfirmed}
                          onChange={(e) => setForfeitConfirmed(e.target.checked)}
                          className="mt-0.5 rounded border-[#E4E2EB] text-rose-600 focus:ring-rose-500"
                        />
                        <span className="text-rose-950 font-medium">
                          I agree to forfeit my remaining wallet balance of $
                          {(preflight.walletBalanceUsd || 0).toFixed(2)} upon deletion completion.
                        </span>
                      </label>
                    )}

                    {/* Multi-Method Backup & Export Section */}
                    <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-2.5">
                      <div>
                        <div className="text-xs font-bold text-[#0F0E17]">
                          Backup & Export Workspace Data
                        </div>
                        <p className="text-[11px] text-[#524E5E]">
                          Before proceeding, export your agents and workspace records to keep a local copy:
                        </p>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {/* 1. Agent Configurations JSON */}
                        <div className="p-2.5 rounded-lg bg-white border border-[#E4E2EB] flex flex-col justify-between gap-2">
                          <div className="flex items-start gap-2">
                            <FileJson className="w-4 h-4 text-[#6344E7] shrink-0 mt-0.5" />
                            <div>
                              <div className="text-[11px] font-semibold text-[#0F0E17]">
                                Agent Configs (JSON)
                              </div>
                              <div className="text-[10px] text-[#524E5E] leading-tight">
                                Prompts, voice stack, greetings & scripts
                              </div>
                            </div>
                          </div>
                          <button
                            type="button"
                            disabled={exportingAgents}
                            onClick={handleExportAgents}
                            className="inline-flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-[#E4E2EB] hover:border-[#6344E7] bg-white text-[11px] font-semibold text-[#0F0E17] hover:text-[#6344E7] transition-colors disabled:opacity-50"
                          >
                            {exportingAgents ? (
                              <>
                                <Loader2 className="w-3 h-3 animate-spin" />
                                Downloading…
                              </>
                            ) : (
                              <>
                                <Download className="w-3 h-3 text-[#6344E7]" />
                                Download JSON
                              </>
                            )}
                          </button>
                        </div>

                        {/* 2. Full Workspace Archive ZIP */}
                        <div className="p-2.5 rounded-lg bg-white border border-[#E4E2EB] flex flex-col justify-between gap-2">
                          <div className="flex items-start gap-2">
                            <Archive className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                            <div>
                              <div className="text-[11px] font-semibold text-[#0F0E17]">
                                Full Archive (ZIP)
                              </div>
                              <div className="text-[10px] text-[#524E5E] leading-tight">
                                Call logs CSV, contacts, invoices & agents
                              </div>
                            </div>
                          </div>
                          <button
                            type="button"
                            disabled={exportingArchive}
                            onClick={handleExportArchive}
                            className="inline-flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-[#E4E2EB] hover:border-emerald-600 bg-white text-[11px] font-semibold text-[#0F0E17] hover:text-emerald-700 transition-colors disabled:opacity-50"
                          >
                            {exportingArchive ? (
                              <>
                                <Loader2 className="w-3 h-3 animate-spin" />
                                Exporting…
                              </>
                            ) : (
                              <>
                                <Download className="w-3 h-3 text-emerald-600" />
                                Export Takeout
                              </>
                            )}
                          </button>
                        </div>
                      </div>

                      {exportNotice && (
                        <p className="text-[11px] font-medium text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg px-2.5 py-1.5 flex items-center gap-1.5">
                          <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-emerald-600" />
                          <span>{exportNotice}</span>
                        </p>
                      )}
                    </div>
                  </>
                )}

                <div className="flex justify-end gap-2 pt-2 border-t border-[#E4E2EB]">
                  <button
                    type="button"
                    onClick={onClose}
                    className="px-4 py-2 rounded-xl text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17] transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={isBlocked || (hasBalance && !forfeitConfirmed)}
                    onClick={() => setStep(2)}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 disabled:opacity-50 transition-all shadow-sm"
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
                <div className="p-3.5 rounded-xl border border-rose-200 bg-rose-50/70 text-rose-950 text-xs space-y-1">
                  <div className="flex items-center gap-1.5 font-bold text-rose-800">
                    <ShieldAlert className="w-4 h-4 text-rose-600 shrink-0" />
                    <span>Workspace Deletion Confirmation</span>
                  </div>
                  <p className="text-[11px] text-rose-900 leading-relaxed">
                    No password or email verification code is required. Simply select the reason for
                    leaving and type the word <strong>delete</strong> below to begin the 14-day quarantine.
                  </p>
                </div>

                {submitError && (
                  <p className="text-[11px] font-medium text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2 flex items-center gap-1.5">
                    <AlertCircle className="w-3.5 h-3.5 shrink-0 text-rose-600" />
                    <span>{submitError}</span>
                  </p>
                )}

                {/* Reason survey */}
                <div>
                  <label htmlFor="delete-reason" className="block text-[11px] font-semibold text-[#0F0E17] mb-1">
                    Why are you deleting this workspace?
                  </label>
                  <select
                    id="delete-reason"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    required
                    className="w-full text-xs px-3.5 py-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] focus:outline-none focus:border-[#6344E7] text-[#0F0E17]"
                  >
                    <option value="">Select a reason…</option>
                    <option value="pricing">Pricing / Too expensive</option>
                    <option value="missing_features">Missing required features</option>
                    <option value="switched_providers">Switching to another provider</option>
                    <option value="project_completed">Project or trial completed</option>
                    <option value="setup_complexity">Difficult to configure</option>
                    <option value="other">Other reason</option>
                  </select>
                </div>

                {/* Optional additional notes */}
                <div>
                  <label htmlFor="delete-feedback" className="block text-[11px] font-semibold text-[#0F0E17] mb-1">
                    Additional feedback (optional)
                  </label>
                  <textarea
                    id="delete-feedback"
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                    placeholder="Tell us what we could have done better…"
                    rows={2}
                    className="w-full text-xs px-3.5 py-2 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] focus:outline-none focus:border-[#6344E7] text-[#0F0E17] resize-none"
                  />
                </div>

                {/* Confirmation input: Type "delete" */}
                <div>
                  <label htmlFor="confirm-delete-word" className="block text-[11px] font-semibold text-[#0F0E17] mb-1">
                    Type the word <span className="text-rose-600 font-bold">delete</span> to confirm
                  </label>
                  <input
                    id="confirm-delete-word"
                    type="text"
                    value={confirmationName}
                    onChange={(e) => setConfirmationName(e.target.value)}
                    placeholder="delete"
                    autoFocus
                    className="w-full text-xs px-3.5 py-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] focus:outline-none focus:border-rose-600 text-[#0F0E17] font-mono"
                  />
                </div>

                <div className="flex justify-between items-center pt-2 border-t border-[#E4E2EB]">
                  <button
                    type="button"
                    onClick={() => setStep(1)}
                    disabled={submitting}
                    className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17] transition-colors"
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
                    className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 disabled:opacity-50 transition-all shadow-sm"
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
