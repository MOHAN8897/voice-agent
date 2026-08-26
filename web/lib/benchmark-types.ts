export type BenchmarkScenario = {
  id: string;
  name: string;
  language: string;
  description?: string;
};

export type BenchmarkCombination = {
  tier: string;
  combination_id?: string | null;
  label?: string | null;
};

export type BenchmarkSession = {
  session_id: string;
  name: string;
  environment: string;
  languages: string[];
  scenario_ids: string[];
  combinations: BenchmarkCombination[];
  estimated_runs?: number;
  status: string;
  created_at?: string;
  started_at?: string | null;
  completed_at?: string | null;
  results?: BenchmarkResultRow[];
  runner_note?: string;
};

export type BenchmarkResultRow = {
  combination_id: string;
  tier?: string;
  scenario_id: string;
  metrics: Record<string, number | null>;
  status?: string;
};

export const BENCHMARK_METRICS = [
  { key: "latency_ms", label: "Latency", unit: "ms", lowerIsBetter: true },
  { key: "stt_accuracy", label: "STT accuracy", unit: "%", lowerIsBetter: false },
  { key: "llm_quality", label: "LLM quality", unit: "score", lowerIsBetter: false },
  { key: "tts_quality", label: "TTS quality", unit: "score", lowerIsBetter: false },
  { key: "reliability", label: "Reliability", unit: "score", lowerIsBetter: false },
  { key: "cost_inr", label: "Cost", unit: "INR", lowerIsBetter: true },
] as const;
