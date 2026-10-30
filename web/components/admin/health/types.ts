export type HealthStatus = "healthy" | "degraded" | "failing" | "not_configured";

export type KeySlot = {
  slot: string;
  configured: boolean;
  state: "active" | "standby" | "cooling_down";
  category: string | null;
  retryInSeconds: number;
  failures: number;
  lastFailureAt: string | null;
  lastSuccessAt: string | null;
};

export type KeyPool = {
  provider: string;
  activeSlot: string | null;
  slots: KeySlot[];
  allKeysCoolingDown: boolean;
  configuredKeys: number;
};

export type ProviderCard = {
  component: string;
  provider: string;
  label: string;
  configured: boolean;
  status: HealthStatus;
  headline: string;
  category: string | null;
  categoryLabel: string | null;
  detail: string | null;
  since: string | null;
  lastSeen: string | null;
  count: number;
  callsAffected: number;
  callsRejected: number;
  tenantsAffected: number;
  incidentIds: string[];
  billingUrl: string | null;
  recentlyRecovered: string | null;
  keys?: KeyPool;
  activeSlot?: string | null;
};

export type Incident = {
  id: string;
  provider: string;
  component: string;
  category: string;
  message: string;
  detail?: string;
  firstSeen: string;
  lastSeen: string;
  count: number;
  status: number | null;
  keySlot?: string;
  failedOverTo?: string | null;
  allKeysFailed?: boolean;
  callsRejected?: number;
  callsAffected: number;
  tenantsAffected: number;
  active: boolean;
  resolvedAt: string | null;
  acknowledgedAt: string | null;
};

export type BannerItem = {
  component: string;
  provider: string;
  label: string;
  status: HealthStatus;
  headline: string;
  since: string | null;
  callsRejected: number;
  billingUrl: string | null;
};

export type ProviderHealth = {
  checkedAt: string;
  overall: HealthStatus;
  banner: BannerItem[];
  components: Array<{ component: string; label: string; providers: ProviderCard[] }>;
  incidents: Incident[];
  categories: Record<string, string>;
  recheck?: Array<{ slot: string; status: number | null; category: string | null; ok: boolean }>;
};

export const PROVIDER_HEALTH_PATH = "/api/dev/admin/provider-health";
