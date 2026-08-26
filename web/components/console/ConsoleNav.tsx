"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PRIMARY_NAV } from "@/lib/constants";
import { SkeuoNavItem } from "@/components/ui/skeuo";
import {
  IconAgents,
  IconBenchmark,
  IconCalls,
  IconChart,
  IconMic,
  IconOverview,
  IconPlug,
  IconRack,
  IconSettings,
} from "@/components/ui/skeuo/icons";

const ICONS: Record<string, React.ReactNode> = {
  overview: <IconOverview className="h-4 w-4" />,
  agents: <IconAgents className="h-4 w-4" />,
  mic: <IconMic className="h-4 w-4" />,
  calls: <IconCalls className="h-4 w-4" />,
  chart: <IconChart className="h-4 w-4" />,
  benchmark: <IconBenchmark className="h-4 w-4" />,
  rack: <IconRack className="h-4 w-4" />,
  plug: <IconPlug className="h-4 w-4" />,
  settings: <IconSettings className="h-4 w-4" />,
};

export function ConsoleNav() {
  const pathname = usePathname();

  return (
    <ul className="space-y-1">
      {PRIMARY_NAV.map((item) => {
        const active = item.href === "/app" ? pathname === "/app" : pathname.startsWith(item.href);
        const live = item.href === "/app/test-studio" && pathname.startsWith("/app/test-studio");
        return (
          <SkeuoNavItem
            key={item.href}
            href={item.href}
            label={item.label}
            active={active}
            icon={ICONS[item.icon]}
            status={live ? "live" : undefined}
          />
        );
      })}
    </ul>
  );
}
