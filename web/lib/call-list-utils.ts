export type CallListItem = {
  call_id: string;
  agent_id?: string;
  channel?: string;
  pipeline?: string;
  tier?: string;
  disposition?: string;
  started_at?: string;
  ended_at?: string;
  duration_sec?: number;
  finalization_status?: string;
  customer?: string;
  summary?: string;
  cost_usd?: number;
  cost_inr?: number;
  cost_inr_per_min?: number;
  has_recording?: boolean;
  usage?: {
    cost_usd?: number;
    cost_inr?: number;
    cost_inr_per_min?: number;
    pipeline?: string;
    turns?: number;
  };
};

export function formatCallTime(value?: string): string {
  if (!value) return "—";
  try {
    const d = new Date(value);
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    const min = String(d.getMinutes()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd} ${hh}:${min}`;
  } catch {
    return value;
  }
}

export function formatDuration(seconds?: number): string {
  if (seconds == null || seconds < 0) return "—";
  const sec = Math.floor(Number(seconds));
  if (!Number.isFinite(sec) || sec < 0) return "—";
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

export function callCustomerLabel(call: CallListItem): string {
  return call.customer?.trim() || "Unknown caller";
}

export function callSummaryLine(call: CallListItem): string {
  if (call.summary?.trim()) return call.summary.trim();
  if (call.finalization_status && call.finalization_status !== "complete") {
    return `Finalization: ${call.finalization_status}`;
  }
  return "No summary yet — outcome may still be processing.";
}

export function pipelineLabel(pipeline?: string, channel?: string): string {
  if (pipeline === "realtime_voice") return "Realtime PSTN";
  if (pipeline === "realtime_text" && channel === "pstn") return "Full PSTN";
  if (pipeline === "realtime_text" && channel === "browser") return "Agent";
  if (pipeline === "realtime_text") return "Composed";
  return channel || "—";
}
