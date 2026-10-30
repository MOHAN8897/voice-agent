import React, { useEffect, useState } from 'react';
import { Modal } from '../../ui/Modal';
import { TactileButton } from '../../ui/TactileButton';
import { api } from '../../../services/api';

/** Confirm before anything that dials a real number or changes a record. */
export function ConfirmDialog({ open, title, body, confirmLabel, busy, error, onConfirm, onClose, tone = 'primary' }) {
  return (
    <Modal isOpen={open} onClose={() => { if (!busy) onClose(); }} title={title} maxWidth="max-w-md">
      <div className="space-y-4">
        <p className="text-copy text-fg-body">{body}</p>
        {error && <p role="alert" className="rounded-control bg-danger-soft p-3 text-ui text-danger-fg">{error}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          <TactileButton variant="ghost" onClick={onClose} disabled={busy}>Cancel</TactileButton>
          <TactileButton variant={tone} onClick={onConfirm} loading={busy}>{confirmLabel}</TactileButton>
        </div>
      </div>
    </Modal>
  );
}

function toLocalInput(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime()) || d.getTime() <= Date.now()) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/**
 * Approve or cancel a follow-up waiting for review. Same API and the same explicit
 * consent as the Follow-ups queue on the Leads page (wallet charges, DND, hours).
 */
export function FollowUpDialog({ target, onClose, onDone }) {
  const [due, setDue] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const approving = target?.action.kind === 'approve_followup';

  useEffect(() => {
    if (!target) return;
    setDue(toLocalInput(target.action.dueAt));
    setConfirmed(false);
    setError('');
  }, [target]);

  const submit = async (event) => {
    event.preventDefault();
    if (!target || busy || !confirmed) return;
    setBusy(true);
    setError('');
    try {
      await api.followups.update(target.action.followUpId, {
        action: approving ? 'schedule' : 'cancel',
        dueAt: approving ? new Date(due).toISOString() : null,
        expectedUpdatedAt: target.action.updatedAt,
        confirm: true,
      });
      onDone(approving ? 'Follow-up approved. Calling hours, DND and wallet checks still apply.' : 'Follow-up cancelled.');
    } catch (e) {
      setError(e?.message || 'Could not update this follow-up.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      isOpen={Boolean(target)}
      onClose={() => { if (!busy) onClose(); }}
      title={approving ? 'Approve this follow-up call' : 'Cancel this follow-up?'}
      subtitle={target?.item?.text}
      maxWidth="max-w-lg"
    >
      <form onSubmit={submit} className="space-y-4">
        {target?.item?.meta?.requestedWhen && (
          <p className="text-ui text-fg-body">Caller asked: {target.item.meta.requestedWhen}</p>
        )}
        {approving && (
          <label className="block text-ui font-medium text-ink">
            Call time ({Intl.DateTimeFormat().resolvedOptions().timeZone})
            <input
              type="datetime-local"
              required
              value={due}
              onChange={(e) => setDue(e.target.value)}
              className="mt-1.5 min-h-11 w-full rounded-control border border-line px-3 text-base sm:text-copy focus:border-accent focus:outline-none"
            />
          </label>
        )}
        <label className="flex items-start gap-3 rounded-control bg-warning-soft p-3 text-ui text-warning-fg">
          <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            {approving
              ? 'I approve this call and its wallet charge. Calling hours may move it later; DND or a conversion can block it.'
              : 'Cancel the pending request. A call already placed cannot be recalled.'}
          </span>
        </label>
        {error && <p role="alert" className="text-ui text-danger-fg">{error}</p>}
        <div className="flex justify-end gap-2">
          <TactileButton variant="ghost" onClick={onClose} disabled={busy}>Back</TactileButton>
          <TactileButton type="submit" variant={approving ? 'primary' : 'danger'} loading={busy} disabled={!confirmed || (approving && !due)}>
            {approving ? 'Approve call' : 'Cancel follow-up'}
          </TactileButton>
        </div>
      </form>
    </Modal>
  );
}

/** Plays a call recording in place, using the same endpoint as the Calls page. */
export function RecordingDialog({ callId, title, onClose }) {
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!callId) return undefined;
    let revoked = '';
    let active = true;
    setUrl('');
    setError('');
    api.calls
      .recording(callId)
      .then((res) => {
        if (!active) return;
        const blob = res?.blob || res;
        revoked = URL.createObjectURL(blob);
        setUrl(revoked);
      })
      .catch((e) => active && setError(e?.message || 'The recording is not available.'));
    return () => {
      active = false;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [callId]);

  return (
    <Modal isOpen={Boolean(callId)} onClose={onClose} title="Call recording" subtitle={title} maxWidth="max-w-md">
      {error ? (
        <p role="alert" className="text-ui text-danger-fg">{error}</p>
      ) : url ? (
        <audio controls autoPlay src={url} className="w-full" aria-label="Call recording" />
      ) : (
        <p role="status" className="text-ui text-fg-muted">Loading recording…</p>
      )}
    </Modal>
  );
}
