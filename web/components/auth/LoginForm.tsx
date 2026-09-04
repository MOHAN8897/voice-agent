"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { FieldError, Label } from "@/components/ui/Label";
import { Input } from "@/components/ui/Input";
import { portalFetch, refreshPortalSession, storeCsrfToken, portalSessionErrorMessage, type PortalKind } from "@/lib/auth-client";

type LoginFormProps = {
  title: string;
  subtitle: string;
  endpoint: "/api/app/login" | "/api/dev/login";
  redirectTo: string;
  portalKind: PortalKind;
};

export function LoginForm({ title, subtitle, endpoint, redirectTo, portalKind }: LoginFormProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") || redirectTo;
  const apiError = searchParams.get("error");

  useEffect(() => {
    let cancelled = false;
    refreshPortalSession(portalKind)
      .then((ok) => {
        if (!cancelled && ok) {
          router.replace(next.startsWith("/") ? next : redirectTo);
        } else if (!cancelled) {
          setCheckingSession(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(portalSessionErrorMessage(portalKind, err));
          setCheckingSession(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [portalKind, next, redirectTo, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const r = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username, password }),
      });
      const j = await r.json();
      if (!j.ok) {
        setError(j.error?.message || "Invalid credentials. Please try again.");
        return;
      }
      if (j.csrf_token) {
        storeCsrfToken(portalKind, j.csrf_token);
      }
      router.push(next.startsWith("/") ? next : redirectTo);
    } catch {
      setError("Could not reach the server. Check that the API is running.");
    } finally {
      setLoading(false);
    }
  }

  if (checkingSession) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-text-muted">Checking session…</p>
        <p className="max-w-sm text-xs text-text-muted">
          On the public tunnel link? Use{" "}
          <a href="http://localhost:3000/dev/login" className="text-accent underline">
            localhost:3000/dev/login
          </a>{" "}
          if this does not finish in a few seconds.
        </p>
      </div>
    );
  }

  return (
    <div className="w-full max-w-md">
      <h1 className="text-3xl font-semibold tracking-tight text-text">{title}</h1>
      <p className="mt-2 text-sm text-text-muted">{subtitle}</p>

      {apiError === "api_unavailable" && (
        <p className="mt-4 rounded-xl border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning">
          API is unreachable. Start the backend before signing in.
        </p>
      )}

      <form onSubmit={submit} className="mt-8 space-y-5" noValidate>
        <div>
          <Label htmlFor="username">Username</Label>
          <Input
            id="username"
            name="username"
            type="text"
            autoComplete="username"
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="mt-2"
            aria-invalid={!!error}
            aria-describedby={error ? "login-error" : undefined}
          />
        </div>
        <div>
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-2"
            aria-invalid={!!error}
          />
        </div>
        {error && <FieldError id="login-error">{error}</FieldError>}
        <Button type="submit" className="w-full" loading={loading}>
          Sign in
        </Button>
      </form>
    </div>
  );
}
