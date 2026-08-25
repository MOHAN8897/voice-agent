import Link from "next/link";
import { BrandMark } from "@/components/brand/BrandMark";

type AuthShellProps = {
  children: React.ReactNode;
  variant?: "business" | "dev";
};

export function AuthShell({ children, variant = "business" }: AuthShellProps) {
  const isDev = variant === "dev";

  return (
    <div className="flex min-h-screen flex-col bg-surface lg:flex-row">
      <aside
        className="relative hidden w-full flex-col justify-between overflow-hidden border-r border-surface-border-subtle bg-surface-elevated p-10 lg:flex lg:w-[44%] xl:w-[42%]"
        aria-label="Product information"
      >
        <div className="absolute inset-0 grid-bg opacity-30" aria-hidden />
        <div className="absolute -right-20 top-1/4 h-64 w-64 rounded-full bg-accent/10 blur-3xl" aria-hidden />

        <div className="relative">
          <BrandMark />
        </div>

        <div className="relative max-w-md">
          <p className="label-caps text-accent">
            {isDev ? "Restricted access" : "Business Console"}
          </p>
          <h1 className="mt-4 text-4xl font-semibold leading-tight tracking-tight text-text xl:text-5xl">
            {isDev
              ? "Platform configuration for authorized staff only"
              : "Configure agents, test voice, deploy with confidence"}
          </h1>
          <p className="mt-4 text-base leading-relaxed text-text-muted">
            {isDev
              ? "Stack resolution, platform brain, and environment promotion. Not visible on the public website."
              : "Structured business brains, live Test Studio, and call archive with memory and disposition."}
          </p>
          <ul className="mt-8 space-y-3 text-sm text-text-muted">
            {(isDev
              ? ["Stack & tier editor", "Platform Brain", "Promotion workflow"]
              : ["8-section Business Brain", "Live Test Studio", "Call transcript & outcomes"]
            ).map((item) => (
              <li key={item} className="flex items-center gap-2">
                <span className="text-accent" aria-hidden>✓</span>
                {item}
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-text-subtle">Serving Telugu-speaking customers · PSTN ready</p>
      </aside>

      <main className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-surface-border-subtle px-6 py-4 lg:border-none lg:px-10 lg:pt-10">
          <span className="lg:hidden">
            <BrandMark />
          </span>
          {isDev ? (
            <span className="text-xs font-mono uppercase tracking-wider text-text-subtle">Authorized access only</span>
          ) : (
            <Link href="/" className="text-sm text-text-muted hover:text-text">← Back to website</Link>
          )}
        </header>

        <div className="flex flex-1 items-center justify-center px-6 py-10 lg:px-16">{children}</div>
      </main>
    </div>
  );
}
