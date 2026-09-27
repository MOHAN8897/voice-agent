import { PageHeader } from "@/components/console/PageHeader";
import { StatCard } from "@/components/console/StatCard";
import Link from "next/link";
import { DevCard } from "@/components/dev/DevCard";

const VOXLY_URL = process.env.NEXT_PUBLIC_VOXLY_URL || "http://127.0.0.1:5173";

const WORKFLOW = [
  {
    title: "Voxly subscriber app",
    body: "Marketing site, sign-in, agents, numbers, billing — the customer product.",
    href: VOXLY_URL,
    step: "01",
    external: true,
  },
  {
    title: "Agents & business brain",
    body: "Create agents, edit drafts, publish — same brain API the subscriber console uses.",
    href: "/dev/agents",
    step: "02",
  },
  {
    title: "Test Studio",
    body: "Live browser voice tests with the resolved agent stack (dev session).",
    href: "/dev/test-studio",
    step: "03",
  },
  {
    title: "Environment",
    body: "API keys and local flags when something fails to connect.",
    href: "/dev/environment",
    step: "04",
  },
];

export default function DevOverviewPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Platform"
        title="Developer portal"
        description="Agent brain + Test Studio on this site. Subscriber UI runs in Voxly (port 5173)."
      />
      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        <StatCard label="Product UI" value="Voxly" hint="npm run dev → :5173" tone="accent" />
        <StatCard label="This portal" value="Dev only" hint="/dev/login" />
        <StatCard label="API" value=":8000" hint="Shared by Voxly + dev" tone="ok" />
      </div>
      <div className="mt-8 grid gap-4 md:grid-cols-2">
        {WORKFLOW.map((item, i) => (
          <DevCard key={item.href} delayMs={i * 60}>
            <p className="font-mono text-sm text-accent/70">{item.step}</p>
            <h3 className="mt-2 text-lg font-semibold text-text">{item.title}</h3>
            <p className="mt-2 text-sm text-text-muted">{item.body}</p>
            {item.external ? (
              <a
                href={item.href}
                className="mt-4 inline-block text-sm font-semibold text-accent hover:underline"
                target="_blank"
                rel="noreferrer"
              >
                Open Voxly →
              </a>
            ) : (
              <Link href={item.href} className="mt-4 inline-block text-sm font-semibold text-accent hover:underline">
                Open →
              </Link>
            )}
          </DevCard>
        ))}
      </div>
    </div>
  );
}
