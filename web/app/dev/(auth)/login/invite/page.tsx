import { Suspense } from "react";
import type { Metadata } from "next";
import { AcceptInviteForm } from "@/components/auth/AcceptInviteForm";

export const metadata: Metadata = {
  title: "Dev Portal — Set your password",
  description: "Accept an admin invite or finish a password reset.",
};

/** Lives under /dev/login so the session middleware lets it through without a session. */
export default function AcceptInvitePage() {
  return (
    <Suspense fallback={<p className="text-sm text-text-muted">Loading…</p>}>
      <AcceptInviteForm />
    </Suspense>
  );
}
