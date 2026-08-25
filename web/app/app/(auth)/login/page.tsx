import { Suspense } from "react";
import { LoginForm } from "@/components/auth/LoginForm";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to the Vāṇi Business Console.",
};

export default function AppLoginPage() {
  return (
    <Suspense fallback={<p className="text-sm text-text-muted">Loading…</p>}>
      <LoginForm
        title="Sign in"
        subtitle="Access your agents, calls, and Test Studio."
        endpoint="/api/app/login"
        redirectTo="/app"
        portalKind="app"
      />
    </Suspense>
  );
}
