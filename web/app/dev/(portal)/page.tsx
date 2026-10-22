import { PageHeader } from "@/components/console/PageHeader";
import Link from "next/link";
import { DevCard } from "@/components/dev/DevCard";

const VOXLY_URL = process.env.NEXT_PUBLIC_VOXLY_URL || "http://127.0.0.1:5173";

/**
 * Grouped by job, matching the sidebar. A flat list of every page made "where do I
 * manage users?" a hunt; these are the four things an operator actually comes here to do.
 */
const SECTIONS = [
  {
    title: "Build the product",
    blurb: "The voice agents subscribers buy, and the phone stack they run on.",
    links: [
      { href: "/dev/agents", label: "Agents & brain", body: "Create, edit, and publish agent brains." },
      {
        href: "/dev/saas-phone-stack",
        label: "SaaS phone AI",
        body: "The one live-phone stack every subscriber tenant shares.",
      },
      { href: "/dev/stack", label: "Stack & tiers", body: "Provider tiers and promotion." },
    ],
  },
  {
    title: "Operate it",
    blurb: "Test an agent on a real call before customers hear it.",
    links: [
      {
        href: "/dev/test-studio",
        label: "Test Studio",
        body: "Live browser and PSTN calls, with per-call forensics.",
      },
    ],
  },
  {
    title: "Maintain the SaaS",
    blurb: "Accounts, money, numbers, and who is allowed to do what.",
    links: [
      { href: "/dev/admin", label: "Overview", body: "Calls, talk time, missed calls, revenue." },
      { href: "/dev/admin/users", label: "Users", body: "Invite, suspend, reactivate, reset." },
      { href: "/dev/admin/tenants", label: "Tenants", body: "Plans, status, and limits per workspace." },
      {
        href: "/dev/admin/numbers",
        label: "Phone numbers",
        body: "Allocate, reassign, and release routed numbers.",
      },
      { href: "/dev/admin/billing", label: "Billing", body: "Purchases, failed provisioning, refunds." },
      {
        href: "/dev/admin/access",
        label: "Roles & access",
        body: "The permission matrix the API enforces.",
      },
    ],
  },
  {
    title: "Fix the platform",
    blurb: "Only needed when something will not connect.",
    links: [
      {
        href: "/dev/environment",
        label: "Environment",
        body: "API keys and local flags for provider failures.",
      },
    ],
  },
];

export default function DevOverviewPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Platform"
        title="Developer portal"
        description="Agent brain, Test Studio, and SaaS operations. The subscriber UI runs in Voxly."
      />

      <div className="mt-8 space-y-8">
        {SECTIONS.map((section) => (
          <section key={section.title}>
            <h2 className="text-base font-semibold text-text">{section.title}</h2>
            <p className="mt-0.5 text-sm text-text-muted">{section.blurb}</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {section.links.map((link) => (
                <Link key={link.href} href={link.href}>
                  <DevCard className="h-full transition-colors hover:border-accent-primary/30">
                    <h3 className="font-semibold text-text">{link.label}</h3>
                    <p className="mt-1 text-sm text-text-muted">{link.body}</p>
                  </DevCard>
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>

      <div className="mt-8">
        <a
          href={VOXLY_URL}
          target="_blank"
          rel="noreferrer"
          className="text-sm font-semibold text-accent hover:underline"
        >
          Open the subscriber product (Voxly) →
        </a>
      </div>
    </div>
  );
}
