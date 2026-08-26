"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { SkeuoNavItem } from "@/components/ui/skeuo";
import {
  IconAgents,
  IconBenchmark,
  IconChart,
  IconMic,
  IconOverview,
  IconRack,
  IconSettings,
} from "@/components/ui/skeuo/icons";

const DEV_NAV = [
  { href: "/dev", label: "Overview", icon: "overview" },
  { href: "/dev/environment", label: "Environment", icon: "settings" },
  { href: "/dev/stack", label: "Stack & tiers", icon: "rack" },
  { href: "/dev/runtime", label: "Runtime tuning", icon: "chart" },
  { href: "/dev/platform-brain", label: "Platform Brain", icon: "settings" },
  { href: "/dev/compiled", label: "Compiled preview", icon: "chart" },
  { href: "/dev/providers", label: "Providers", icon: "rack" },
  { href: "/dev/agents", label: "Agent studio", icon: "agents" },
  { href: "/dev/test-studio", label: "Test Studio", icon: "mic" },
  { href: "/dev/benchmarks", label: "Benchmarks", icon: "benchmark" },
  { href: "/dev/promotion", label: "Promotion", icon: "chart" },
] as const;

const ICONS: Record<string, React.ReactNode> = {
  overview: <IconOverview className="h-4 w-4" />,
  agents: <IconAgents className="h-4 w-4" />,
  mic: <IconMic className="h-4 w-4" />,
  chart: <IconChart className="h-4 w-4" />,
  benchmark: <IconBenchmark className="h-4 w-4" />,
  rack: <IconRack className="h-4 w-4" />,
  settings: <IconSettings className="h-4 w-4" />,
};

export function DevNav() {
  const pathname = usePathname();

  return (
    <ul className="space-y-1">
      {DEV_NAV.map((item) => {
        const active = item.href === "/dev" ? pathname === "/dev" : pathname.startsWith(item.href);
        return (
          <SkeuoNavItem
            key={item.href}
            href={item.href}
            label={item.label}
            active={active}
            icon={ICONS[item.icon]}
            status={item.href === "/dev/test-studio" && active ? "live" : undefined}
          />
        );
      })}
    </ul>
  );
}
