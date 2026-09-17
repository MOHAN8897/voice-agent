/** PSTN Test Studio live-call stages. Telnyx statuses are event names, not Twilio verbs. */

export type PstnLifecycleStage =
  | "idle"
  | "placed"
  | "ringing"
  | "lifted"
  | "ongoing"
  | "closing"
  | "hangup";

export const PSTN_LIFECYCLE_STEPS: {
  id: PstnLifecycleStage;
  label: string;
  hint: string;
}[] = [
  { id: "placed", label: "Call placed", hint: "Outbound dial accepted by provider" },
  { id: "ringing", label: "Ringing", hint: "Callee phone is ringing" },
  { id: "lifted", label: "Call lifted", hint: "Callee answered — media stream starting" },
  { id: "ongoing", label: "In progress", hint: "Agent and caller are connected" },
  { id: "closing", label: "Closing", hint: "Playing farewell — short pause, then disconnect" },
  { id: "hangup", label: "Hangup", hint: "Call ended — finalizing recording and cost" },
];

const STAGE_RANK: Record<PstnLifecycleStage, number> = {
  idle: -1,
  placed: 0,
  ringing: 1,
  lifted: 2,
  ongoing: 3,
  closing: 4,
  hangup: 5,
};

const TERMINAL = new Set([
  "completed",
  "failed",
  "busy",
  "no-answer",
  "no_answer",
  "canceled",
  "cancelled",
  "hangup",
  "ended",
  "stream-error",
  "stream_error",
  "voice_start_failed",
  "stream_start_failed",
]);

const INTERNAL_CALL_ID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isInternalCallId(id?: string | null): boolean {
  return Boolean(id && INTERNAL_CALL_ID_RE.test(String(id).trim()));
}

export type ProviderStatusHints = {
  hasInternal?: boolean;
  lastEvent?: string;
  ended?: boolean;
  mediaFramesIn?: number;
  mediaFramesOut?: number;
};

function token(raw?: string): string {
  return (raw || "")
    .toLowerCase()
    .trim()
    .replace(/^call\./, "")
    .replace(/^streaming\./, "streaming.");
}

export function isTerminalProviderStatus(status?: string, ended?: boolean): boolean {
  if (ended) return true;
  const st = token(status);
  if (!st) return false;
  if (TERMINAL.has(st)) return true;
  if (st.includes("hangup")) return true;
  return false;
}

export function mapProviderStatus(status?: string, hints: boolean | ProviderStatusHints = {}): PstnLifecycleStage {
  const extra: ProviderStatusHints = typeof hints === "boolean" ? { hasInternal: hints } : hints || {};
  const st = token(status);
  const ev = token(extra.lastEvent);
  const frames = (extra.mediaFramesIn || 0) + (extra.mediaFramesOut || 0);

  if (extra.ended || isTerminalProviderStatus(st) || isTerminalProviderStatus(ev)) {
    return "hangup";
  }
  if (st === "closing" || st === "hangup_closing" || ev === "hangup_closing") {
    return "closing";
  }
  if (
    st === "streaming" ||
    st.startsWith("streaming.") ||
    st === "in-progress" ||
    st === "in_progress" ||
    st === "active" ||
    st === "bridged"
  ) {
    if (st.includes("fail")) {
      return extra.hasInternal ? "ongoing" : "placed";
    }
    return "ongoing";
  }
  if (frames > 0) return "ongoing";
  if (st === "stream-stopped" || st === "stream-error" || st === "stream_stopped" || st === "stream_error") {
    if (extra.hasInternal) return "ongoing";
    return "hangup";
  }
  if (st === "answered" || ev === "answered") return "lifted";
  if (extra.hasInternal) return "lifted";
  if (st === "ringing" || ev === "ringing") return "ringing";
  if (!st && !ev && !extra.hasInternal) return "idle";
  if (st === "initiated" || st === "placed" || st === "queued" || st === "dialing" || ev === "initiated") {
    return "placed";
  }
  if (st || ev) return "placed";
  return "idle";
}

/** Never walk the timeline backwards mid-call (provider events can regress to stream-stopped). */
export function advanceLifecycle(
  prev: PstnLifecycleStage,
  next: PstnLifecycleStage,
): PstnLifecycleStage {
  if (next === "idle") return prev === "hangup" ? "hangup" : prev;
  if (prev === "idle") return next;
  return STAGE_RANK[next] >= STAGE_RANK[prev] ? next : prev;
}

export function stageIndex(stage: PstnLifecycleStage): number {
  if (stage === "idle") return -1;
  return PSTN_LIFECYCLE_STEPS.findIndex((s) => s.id === stage);
}

export function matchTelephonyRow<T extends {
  call_sid?: string;
  call_control_id?: string;
  call_uuid?: string;
  internal_call_id?: string;
}>(
  rows: T[],
  externalId?: string | null,
  internalId?: string | null,
): T | null {
  const ext = (externalId || "").trim();
  const internal = (internalId || "").trim();
  if (ext) {
    const hit = rows.find((row) => {
      const sid = String(row.call_sid || "");
      const control = String(row.call_control_id || "");
      const uuid = String(row.call_uuid || "");
      const key = sid || control || uuid;
      return key === ext || sid === ext || control === ext || uuid === ext;
    });
    if (hit) return hit;
  }
  if (internal) {
    const hit = rows.find((row) => String(row.internal_call_id || "") === internal);
    if (hit) return hit;
  }
  return null;
}
