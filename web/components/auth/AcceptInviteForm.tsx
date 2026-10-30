"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { FieldError, Label } from "@/components/ui/Label";
import { Input } from "@/components/ui/Input";

type LinkInfo = {
  purpose: "invite" | "reset";
  username: string;
  email: string;
  fullName: string;
  roleLabel: string;
  expiresAt: string | null;
  minPasswordLength: number;
};

async function post(path: string, body: unknown): Promise<{ ok: boolean; data: unknown; message: string }> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  const detail = (data as { detail?: { error?: { message?: string } } | string } | null)?.detail;
  const message =
    typeof detail === "string" ? detail : detail?.error?.message ?? (res.ok ? "" : "Something went wrong. Try again.");
  return { ok: res.ok, data, message };
}

/**
 * One-time admin invite / password-reset link. The token in the URL is the only
 * credential; the server checks it, its expiry and that it is unused.
 */
export function AcceptInviteForm() {
  const token = useSearchParams().get("token") ?? "";
  const [info, setInfo] = useState<LinkInfo | null>(null);
  const [linkError, setLinkError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setLinkError("This link is missing its token. Open the full link you were sent.");
      return;
    }
    let cancelled = false;
    void post("/api/dev/admin-invite/inspect", { token }).then((r) => {
      if (cancelled) return;
      if (r.ok) setInfo(r.data as LinkInfo);
      else setLinkError(r.message);
    });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const min = info?.minPasswordLength ?? 12;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < min) return setError(`Use at least ${min} characters.`);
    if (password !== confirm) return setError("The two passwords don't match.");
    setBusy(true);
    try {
      const r = await post("/api/dev/admin-invite/accept", { token, password });
      if (r.ok) setDone((r.data as { username?: string })?.username ?? info?.username ?? "");
      else setError(r.message);
    } catch {
      setError("Could not reach the server. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (done !== null) {
    return (
      <div className="w-full max-w-md space-y-4">
        <h1 className="text-3xl font-semibold tracking-tight text-text">Password set</h1>
        <p className="text-sm text-text-muted">
          Sign in with your username <span className="font-mono text-text">{done}</span> and the password you just chose.
        </p>
        <Link href="/dev/login" className="inline-block text-sm text-accent underline">
          Go to sign in
        </Link>
      </div>
    );
  }

  if (linkError) {
    return (
      <div className="w-full max-w-md space-y-4">
        <h1 className="text-3xl font-semibold tracking-tight text-text">Link can&apos;t be used</h1>
        <p className="text-sm text-text-muted">{linkError}</p>
        <Link href="/dev/login" className="inline-block text-sm text-accent underline">
          Back to sign in
        </Link>
      </div>
    );
  }

  if (!info) return <p className="text-sm text-text-muted">Checking your link…</p>;

  return (
    <div className="w-full max-w-md">
      <h1 className="text-3xl font-semibold tracking-tight text-text">
        {info.purpose === "invite" ? "Join the admin portal" : "Choose a new password"}
      </h1>
      <p className="mt-2 text-sm text-text-muted">
        {info.purpose === "invite"
          ? `You've been invited as ${info.roleLabel}.`
          : "An admin reset your password."}{" "}
        Your username is <span className="font-mono text-text">{info.username}</span> ({info.email}).
        {info.expiresAt && ` This link expires ${new Date(info.expiresAt).toLocaleString()} and works once.`}
      </p>
      <form onSubmit={submit} className="mt-8 space-y-5" noValidate>
        <input type="text" name="username" autoComplete="username" value={info.username} readOnly hidden />
        <div>
          <Label htmlFor="new-password">New password</Label>
          <Input
            id="new-password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-2"
            aria-describedby="password-hint"
          />
          <p id="password-hint" className="mt-1 text-xs text-text-muted">
            At least {min} characters, and not containing your username or email.
          </p>
        </div>
        <div>
          <Label htmlFor="confirm-password">Confirm password</Label>
          <Input
            id="confirm-password"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="mt-2"
          />
        </div>
        {error && <FieldError id="accept-error">{error}</FieldError>}
        <Button type="submit" className="w-full" loading={busy}>
          Set password
        </Button>
      </form>
    </div>
  );
}
