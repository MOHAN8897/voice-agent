"use client";

import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import type { CallMeta } from "@/lib/call-detail-types";
import { formatCallTime, formatDuration, pipelineLabel } from "@/lib/call-list-utils";
import { formatInr, formatUsd } from "@/lib/usage-cost";
import { CallTranscriptSourceBadge } from "@/components/calls/detail/CallTranscriptSourceBadge";

export function CallMetadataPanel({ meta }: { meta: CallMeta }) {
  const fin = meta.finalization || {};
  const stack = meta.resolved_stack || {};
  const usage = meta.usage || {};
  const costInr = meta.cost_inr ?? usage.cost_inr;
  const costUsd = meta.cost_usd ?? usage.cost_usd;
  const perMin = meta.cost_inr_per_min ?? usage.cost_inr_per_min;

  const rows: Array<{ label: string; value: string }> = [
    { label: "Agent", value: meta.agent_id || "—" },
    { label: "Channel", value: meta.channel || "—" },
    { label: "Pipeline", value: pipelineLabel(meta.pipeline, meta.channel) },
    { label: "Direction", value: meta.direction || "—" },
    { label: "Caller", value: meta.caller_id || "—" },
    { label: "Tier", value: meta.tier || "—" },
    { label: "Environment", value: meta.environment || "—" },
    { label: "Started", value: formatCallTime(meta.started_at) },
    { label: "Ended", value: formatCallTime(meta.ended_at) },
    { label: "Duration", value: formatDuration(meta.duration_sec ?? usage.duration_sec) },
    { label: "End reason", value: meta.end_reason || "—" },
    { label: "Combination", value: meta.combination_id || "—" },
    { label: "Brain version", value: meta.compiled_brain_version || "—" },
    { label: "Finalization", value: String(meta.finalization_status || fin.status || "—") },
    { label: "Ledger", value: String(fin.ledger || "—") },
    { label: "Audio archive", value: String(fin.audio || "—") },
    { label: "Outcome job", value: String(fin.outcome || "—") },
  ];
  if (usage.llm_model) {
    rows.push({ label: "Realtime model", value: String(usage.llm_model) });
  }
  if (meta.pipeline === "realtime_voice" || meta.channel === "pstn_realtime") {
    rows.push({
      label: "STT/TTS on stack",
      value: "Not used — Live speech model handles audio (Sarvam/Cartesia slots ignored)",
    });
  }
  if (usage.turns != null) {
    rows.push({ label: "Billed turns", value: String(usage.turns) });
  }
  if (usage.input_audio_tokens != null || usage.output_audio_tokens != null) {
    rows.push({
      label: "Audio tokens",
      value: `${usage.input_audio_tokens ?? 0} in / ${usage.output_audio_tokens ?? 0} out`,
    });
  }
  if (usage.input_image_tokens) {
    rows.push({ label: "Image tokens", value: String(usage.input_image_tokens) });
  }
  const modelInr = meta.model_cost_inr ?? usage.model_cost_inr;
  const telnyxInr = meta.telnyx_inr ?? usage.telnyx_inr;
  if (modelInr != null) {
    rows.push({
      label: "Model cost",
      value: `${formatInr(Number(modelInr))} (${formatUsd(Number(usage.model_cost_usd || 0))})`,
    });
  }
  if (telnyxInr != null) {
    rows.push({
      label: "Telnyx minutes",
      value: `${formatInr(Number(telnyxInr))} (${formatUsd(Number(usage.telnyx_usd || 0))})`,
    });
  }
  const transcriptInr = usage.post_call_transcript_inr;
  if (transcriptInr != null && Number(transcriptInr) > 0) {
    rows.push({
      label: "Post-call transcript",
      value: `${formatInr(Number(transcriptInr))} (${formatUsd(Number(usage.post_call_transcript_usd || 0))})`,
    });
  }
  const txStatus = meta.post_call_transcript?.status;
  if (txStatus) {
    rows.push({ label: "Transcript job", value: String(txStatus) });
  }
  if (usage.transcription_billing) {
    rows.push({ label: "Transcription billing", value: String(usage.transcription_billing) });
  }
  if (meta.transcript_source) {
    rows.push({ label: "Transcript source", value: String(meta.transcript_source) });
  }
  if (costInr != null) {
    rows.push({ label: "Total cost", value: `${formatInr(Number(costInr))} (${formatUsd(Number(costUsd || 0))})` });
  }
  if (perMin != null) {
    rows.push({ label: "All-in ₹/min", value: formatInr(Number(perMin)) });
  }
  if (usage.model_cost_inr_per_min != null) {
    rows.push({ label: "Model ₹/min", value: formatInr(Number(usage.model_cost_inr_per_min)) });
  }
  if (usage.telnyx_inr_per_min != null) {
    rows.push({ label: "Telnyx ₹/min", value: formatInr(Number(usage.telnyx_inr_per_min)) });
  }
  if (usage.gemini_list_audio_inr_per_min != null) {
    rows.push({
      label: "Gemini audio list ₹/min",
      value: `${formatInr(Number(usage.gemini_list_audio_inr_per_min))} ($0.005 in + $0.018 out)`,
    });
  }
  if (usage.fx_rate_inr != null) {
    const src = usage.fx_source ? ` (${usage.fx_source})` : "";
    rows.push({ label: "FX USD→INR", value: `${Number(usage.fx_rate_inr)}${src}` });
  }

  return (
    <SkeuoPanel title="Metadata" description="Configuration snapshot and archive status" padding="md">
      <div className="mb-4">
        <CallTranscriptSourceBadge meta={meta} />
      </div>
      <ul className="space-y-2">
        {rows.map((row) => (
          <li key={row.label} className="flex justify-between gap-3 text-sm border-b border-surface-border-subtle/60 pb-2">
            <span className="text-text-muted">{row.label}</span>
            <span className="font-mono text-xs text-text text-right break-all">{row.value}</span>
          </li>
        ))}
      </ul>

      {Object.keys(stack).length > 0 && (
        <div className="mt-4">
          <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Resolved stack</p>
          <pre className="mt-2 max-h-40 overflow-auto rounded-skeuo-sm skeuo-inset p-3 font-mono text-[10px] text-text-muted">
            {JSON.stringify(stack, null, 2)}
          </pre>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <SkeuoBadge tone="muted">meta.json</SkeuoBadge>
        <SkeuoBadge tone="muted">trace.json</SkeuoBadge>
        <SkeuoBadge tone="muted">transcript.jsonl</SkeuoBadge>
        <SkeuoBadge tone="muted">outcome.json</SkeuoBadge>
      </div>
    </SkeuoPanel>
  );
}
