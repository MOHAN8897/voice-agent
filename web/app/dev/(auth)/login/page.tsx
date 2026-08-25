import { Suspense } from "react";
import { LoginForm } from "@/components/auth/LoginForm";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Dev Portal — Sign in",
  description: "Developer sign-in for stack, tiers, and platform brain.",
};

export default function DevLoginPage() {
  return (
    <Suspense fallback={<p className="text-sm text-text-muted">Loading…</p>}>
      <LoginForm
        title="Dev Portal"
        subtitle="Configure provider stacks, tiers, and platform brain."
        endpoint="/api/dev/login"
        redirectTo="/dev/stack"
        portalKind="dev"
      />
    </Suspense>
  );
}
