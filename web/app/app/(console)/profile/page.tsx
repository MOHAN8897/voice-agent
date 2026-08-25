import { PageHeader } from "@/components/console/PageHeader";
import { LogoutButton } from "@/components/auth/LogoutButton";
import Link from "next/link";
import { Button } from "@/components/ui/Button";

export default function ProfilePage() {
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        eyebrow="Account"
        title="Profile & security"
        description="Session and tenant for the Business Console."
      />
      <section className="mt-8 rounded-2xl border border-surface-border-subtle bg-surface-card p-6 shadow-card">
        <h2 className="label-caps text-text-subtle">Session</h2>
        <dl className="mt-4 space-y-3 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-text-muted">Environment</dt>
            <dd className="font-mono text-text">development</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-text-muted">Role</dt>
            <dd className="text-text">Administrator</dd>
          </div>
        </dl>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link href="/app/select-tenant">
            <Button variant="secondary" type="button">Switch tenant</Button>
          </Link>
          <LogoutButton kind="app" redirectTo="/app/login" variant="ghost" />
        </div>
      </section>
    </div>
  );
}
