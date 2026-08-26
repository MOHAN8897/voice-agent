export const TIER_META = {
  low: {
    label: "LOW",
    cost: "Lowest",
    latency: "Fast",
    quality: "Acceptable",
    description: "Cost-optimized stack for high-volume traffic.",
  },
  medium: {
    label: "MEDIUM",
    cost: "Balanced",
    latency: "Balanced",
    quality: "Balanced",
    description: "Default production balance of cost, speed, and quality.",
  },
  premium: {
    label: "PREMIUM",
    cost: "Higher",
    latency: "Quality-first",
    quality: "Highest",
    description: "Maximum quality for critical conversations.",
  },
} as const;

export type TierName = keyof typeof TIER_META;

export const TIER_ORDER: TierName[] = ["low", "medium", "premium"];
