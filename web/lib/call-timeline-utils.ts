import type {
  MemoryEvent,
  TraceTurn,
  TranscriptLine,
  UnifiedTimelineEvent,
} from "@/lib/call-detail-types";

const LANE_ORDER: Record<string, number> = {
  audio: 0,
  stt: 1,
  llm: 2,
  tts: 3,
  memory: 4,
  error: 5,
};

export function elapsedFromStart(ts?: string, startTs?: string): string {
  if (!ts || !startTs) return "—";
  try {
    const delta = new Date(ts).getTime() - new Date(startTs).getTime();
    if (delta < 0) return "0:00";
    const sec = Math.floor(delta / 1000);
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  } catch {
    return "—";
  }
}

export function buildUnifiedTimeline(
  lines: TranscriptLine[],
  traceTurns: TraceTurn[],
  memoryEvents: MemoryEvent[]
): UnifiedTimelineEvent[] {
  const events: UnifiedTimelineEvent[] = [];

  for (const line of lines) {
    const turn = line.seq;
    if (line.role === "user") {
      events.push({
        id: `audio-${turn}`,
        lane: "audio",
        turn,
        label: "User audio",
        detail: "Utterance captured",
        ts: line.ts,
      });
      events.push({
        id: `stt-${turn}`,
        lane: "stt",
        turn,
        label: "STT final",
        detail: line.text,
        ms: line.stt_latency_ms,
        ts: line.ts,
      });
    } else if (line.role === "assistant") {
      events.push({
        id: `llm-${turn}`,
        lane: "llm",
        turn,
        label: "LLM stream",
        detail: line.text,
        ms: line.brain_latency_ms,
        ts: line.ts,
      });
      if (line.tts_first_byte_ms != null) {
        events.push({
          id: `tts-${turn}`,
          lane: "tts",
          turn,
          label: "TTS first audio",
          ms: line.tts_first_byte_ms,
          ts: line.ts,
        });
      }
    }
  }

  for (const t of traceTurns) {
    const turn = t.turn;
    if (t.memory_ops_applied) {
      events.push({
        id: `mem-turn-${turn}`,
        lane: "memory",
        turn,
        label: "Memory merge",
        detail: `${t.memory_ops_applied} operation(s) applied`,
        ms: t.memory_merge_ms,
      });
    }
    for (const [i, err] of (t.errors || []).entries()) {
      events.push({
        id: `err-${turn}-${i}`,
        lane: "error",
        turn,
        label: "Pipeline error",
        detail: String(err),
      });
    }
  }

  for (const [i, ev] of memoryEvents.entries()) {
    events.push({
      id: `mem-ev-${i}`,
      lane: "memory",
      turn: ev.turn_seq,
      label: "Memory event",
      detail: ev.source || "model",
      ts: ev.at,
    });
  }

  return events.sort((a, b) => {
    const ta = a.turn ?? 0;
    const tb = b.turn ?? 0;
    if (ta !== tb) return ta - tb;
    return (LANE_ORDER[a.lane] ?? 9) - (LANE_ORDER[b.lane] ?? 9);
  });
}

export function traceTurnLatencies(turns: TraceTurn[]) {
  return turns.map((t) => ({
    turn: t.turn ?? 0,
    sttMs: t.stt_final_ms ?? 0,
    llmMs: t.llm_ttft_ms ?? 0,
    ttsMs: t.tts_first_audio_ms ?? 0,
    e2eMs: t.e2e_ms ?? 0,
  }));
}
