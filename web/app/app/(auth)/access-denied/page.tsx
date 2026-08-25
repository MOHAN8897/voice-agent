import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Access denied",
  robots: { index: false },
};

export default function AccessDeniedPage() {
  return (
    <div className="w-full max-w-md text-center">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-warning/30 bg-warning/10 text-2xl text-warning">
        !
      </div>
      <h1 className="mt-6 text-3xl font-semibold tracking-tight text-text">Access denied</h1>
      <p className="mt-3 text-sm leading-relaxed text-text-muted">
        Your account does not have permission to view this resource. Contact your platform administrator or
        switch to a tenant you can access.
      </p>
      <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-center">
        <Link
          href="/app/select-tenant"
          className="inline-flex items-center justify-center rounded-xl bg-accent px-4 py-2.5 text-sm font-medium text-white"
        >
          Switch tenant
        </Link>
        <Link
          href="/"
          className="inline-flex items-center justify-center rounded-xl border border-surface-border px-4 py-2.5 text-sm font-medium text-text"
        >
          Back to home
        </Link>
      </div>
    </div>
  );
}
