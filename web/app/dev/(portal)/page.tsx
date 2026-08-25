import { PageHeader } from "@/components/console/PageHeader";
import { StatCard } from "@/components/console/StatCard";
import Link from "next/link";
import { DevCard } from "@/components/dev/DevCard";

const WORKFLOW = [
  {
    title: "Environment & keys",
    body: "Set API keys, enable DeepSeek/Cartesia, and choose config mode.",
    href: "/dev/environment",
    step: "01",
  },
  {
    title: "Configure stacks",
    body: "Pick STT, LLM, and TTS per tier. Run combination tests before saving.",
    href: "/dev/stack",
    step: "02",
  },
  {
    title: "Tune platform brain",
    body: "Edit identity, language rules, memory contract, and output behavior.",
    href: "/dev/platform-brain",
    step: "03",
  },
  {
    title: "Test live agent",
    body: "Run browser Test Studio with the resolved stack.",
    href: "/dev/test-studio",
    step: "04",
  },
  {
    title: "Promote",
    body: "Move tier assignments to staging or production with a reason.",
    href: "/dev/promotion",
    step: "05",
  },
];

export default function DevOverviewPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Platform"
        title="Developer Portal"
        description="Fine-tune voice agent stacks, platform brain, and environment promotion. Not linked from the public website."
      />
      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        <StatCard label="Promotion path" value="3 envs" hint="dev → staging → prod" tone="accent" />
        <StatCard label="Tiers" value="LOW / MED / PREM" hint="Server-resolved at call/start" />
        <StatCard label="Platform brain" value="Protected" hint="Dev session required" tone="ok" />
      </div>
      <div className="mt-8 grid gap-4 md:grid-cols-2">
        {WORKFLOW.map((item, i) => (
          <DevCard key={item.href} delayMs={i * 60}>
            <p className="font-mono text-sm text-accent/70">{item.step}</p>
            <h3 className="mt-2 text-lg font-semibold text-text">{item.title}</h3>
            <p className="mt-2 text-sm text-text-muted">{item.body}</p>
            <Link href={item.href} className="mt-4 inline-block text-sm font-semibold text-accent hover:underline">
              Open →
            </Link>
          </DevCard>
        ))}
      </div>
    </div>
  );
}
