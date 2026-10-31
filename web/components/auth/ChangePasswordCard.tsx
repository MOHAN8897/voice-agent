"use client";

import { useState } from "react";
import { Panel } from "@/components/console/Panel";
import { SkeuoButton, SkeuoInput } from "@/components/ui/skeuo";
import { portalFetch, PortalKind } from "@/lib/auth-client";

const MIN_LENGTH = 8;

type PortalKindProp = Extract<PortalKind, "app"> | PortalKind;

function readError(payload: unknown, status: number): string {
  const detail = (payload as { detail?: { error?: { message?: string } } } | null)?.detail;
  const message = detail?.error?.message;
  if (typeof message === "string" && message) return message;
  return `Could not change the password (HTTP ${status}).`;
}

/**
 * Change password for the portal session.
 *
 * The endpoint existed with no UI behind it, so the only way to change a password was
 * signing out and using the reset email. Changing it in place also keeps the user
 * signed in: the API revokes every other refresh token for the account and returns a
 * fresh session for this browser.
 */
export function ChangePasswordCard({ kind = "app" }: { kind?: PortalKindProp }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setError(null);
    setNotice(null);

    if (newPassword.length < MIN_LENGTH) {
      setError(`New password must be at least ${MIN_LENGTH} characters.`);
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("The two new passwords do not match.");
      return;
    }

    setBusy(true);
    try {
      const res = await portalFetch(kind, "/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ currentPassword, newPassword }),
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => null);
        setError(readError(payload, res.status));
        return;
      }
      setNotice("Password updated. Other sessions were signed out.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch {
      setError("Could not reach the API. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel
      title="Password"
      description="Changing it signs out every other device. This session stays signed in."
    >
      <form onSubmit={submit} className="space-y-3" data-testid="change-password-form">
        <label className="block text-sm text-text-muted">
          Current password
          <SkeuoInput
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            autoComplete="current-password"
            required
            aria-label="Current password"
            data-testid="change-password-current"
          />
        </label>
        <label className="block text-sm text-text-muted">
          New password
          <SkeuoInput
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            autoComplete="new-password"
            minLength={MIN_LENGTH}
            required
            aria-label="New password"
            data-testid="change-password-new"
          />
        </label>
        <label className="block text-sm text-text-muted">
          Confirm new password
          <SkeuoInput
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            autoComplete="new-password"
            minLength={MIN_LENGTH}
            required
            aria-label="Confirm new password"
            data-testid="change-password-confirm"
          />
        </label>

        {error ? (
          <p data-testid="change-password-error" className="text-xs text-danger">
            {error}
          </p>
        ) : null}
        {notice ? (
          <p data-testid="change-password-notice" className="text-xs text-accent-primary">
            {notice}
          </p>
        ) : null}

        <SkeuoButton type="submit" variant="primary" disabled={busy} data-testid="change-password-submit">
          {busy ? "Updating…" : "Update password"}
        </SkeuoButton>
      </form>
    </Panel>
  );
}

export default ChangePasswordCard;