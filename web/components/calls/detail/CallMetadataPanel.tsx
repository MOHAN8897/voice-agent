"use client";

import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import type { CallMeta } from "@/lib/call-detail-types";
import { formatCallTime, formatDuration, pipelineLabel } from "@/lib/call-list-utils";
import { formatInr, formatUsd } from "@/lib/usage-cost";
import { CallTranscriptSourceBadge } from "@/components/calls/detail/CallTranscriptSourceBadge";

/**
 * Call metadata, split by audience.
 *
 * Wholesale carrier cost, upstream model list rates, the resolved provider stack and
 * PSTN forensics are the platform's internals — a tenant can read their margin off them
 * and shop the same vendors directly. They are only rendered when
 * `internalFieldsHidden` is absent, which is the signal the API sets when it withheld
 * them. The API is the real boundary (see call_redaction.py); this keeps the panel
 * honest about what it is showing instead of leaving blank rows behind.
 */
export function CallMetadataPanel({ meta }: { meta: CallMeta }) {
  const internal = !(meta as { internal_fields_hidden?: boolean }).internal_fields_hidden;
  const fin = meta.finalization || {};
  const stack = internal ? meta.resolved_stack || {} : {};
  const rawUsage = meta.usage || {};
  // Per-minute wholesale rates are internal; the billed total is the customer's.
  const usage: Record<string, any> = internal
    ? rawUsage
    : Object.fromEntries(
        Object.entries(rawUsage).filter(([key]) =>
          ["turns", "input_audio_tokens", "output_audio_tokens", "duration_sec"].includes(key),
        ),
      );
  const costUsd = meta.cost_usd ?? usage.cost_usd;
  const costInr = internal ? meta.cost_inr ?? usage.cost_inr : undefined;
  const perMin = internal ? meta.cost_inr_per_min ?? usage.cost_inr_per_min : undefined;

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
  ];
  if (internal) {
    // Internal bookkeeping: only meaningful to the platform team.
    rows.push(
      { label: "Combination", value: meta.combination_id || "—" },
      { label: "Brain version", value: meta.compiled_brain_version || "—" },
      {
        label: "Dial request ID",
        value: String((meta as { dial_request_id?: string }).dial_request_id || "—"),
      },
    );
  }
  rows.push({ label: "Finalization", value: String(meta.finalization_status || fin.status || "—") });
  if (internal) {
    rows.push(
      { label: "Ledger", value: String(fin.ledger || "—") },
      { label: "Audio archive", value: String(fin.audio || "—") },
      { label: "Outcome job", value: String(fin.outcome || "—") },
    );
  }
  if (internal && usage.llm_model) {
    rows.push({ label: "Realtime model", value: String(usage.llm_model) });
  }
  if (
    internal &&
    (meta.pipeline === "realtime_voice" || meta.channel === "pstn_realtime")
  ) {
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
  const modelInr = internal ? meta.model_cost_inr ?? usage.model_cost_inr : undefined;
  const telnyxInr = internal ? meta.telnyx_inr ?? usage.telnyx_inr : undefined;
  if (modelInr != null) {
    rows.push({
      label: "Model cost",
      value: `${formatInr(Number(modelInr))} (${formatUsd(Number(usage.model_cost_usd || 0))})`,
    });
  }
  if (telnyxInr != null) {
    rows.push({
      label: "Carrier minutes",
      value: `${formatInr(Number(telnyxInr))} (${formatUsd(Number(usage.telnyx_usd || 0))})`,
    });
  }
  const transcriptInr = usage.post_call_transcript_inr;
  if (internal && transcriptInr != null && Number(transcriptInr) > 0) {
    rows.push({
      label: "Post-call transcript",
      value: `${formatInr(Number(transcriptInr))} (${formatUsd(Number(usage.post_call_transcript_usd || 0))})`,
    });
  }
  const txStatus = meta.post_call_transcript?.status;
  if (txStatus) {
    rows.push({ label: "Transcript job", value: String(txStatus) });
  }
  if (internal && usage.transcription_billing) {
    rows.push({ label: "Transcription billing", value: String(usage.transcription_billing) });
  }
  if (internal && meta.transcript_source) {
    rows.push({ label: "Transcript source", value: String(meta.transcript_source) });
  }
  // USD leads everywhere; the rupee figure stays as a secondary reference because
  // settlement is in INR and the two are not the same number at a given rate.
  // The rate comes from the call's own usage record, so a historical call is
  // converted at the rate that actually applied to it.

  if (costUsd != null) {
    rows.push({
      label: "Call cost",
      value: internal && costInr != null
        ? `${formatUsd(Number(costUsd))} (settled ₹${Number(costInr).toFixed(2)})`
        : formatUsd(Number(costUsd)),
    });
  }
  if (perMin != null) {
    rows.push({
      label: "All-in $/min",
      value: formatUsd(Number(perMin) / (Number(usage.fx_rate_inr) || 1)),
    });
  }
  if (internal && usage.model_cost_inr_per_min != null) {
    rows.push({
      label: "Model $/min",
      value: formatUsd(Number(usage.model_cost_inr_per_min) / (Number(usage.fx_rate_inr) || 1)),
    });
  }
  if (internal && usage.telnyx_inr_per_min != null) {
    rows.push({
      label: "Carrier $/min",
      value: formatUsd(Number(usage.telnyx_inr_per_min) / (Number(usage.fx_rate_inr) || 1)),
    });
  }
  if (internal && usage.gemini_list_audio_inr_per_min != null) {
    rows.push({
      label: "Audio list rate $/min",
      value: formatUsd(
        Number(usage.gemini_list_audio_inr_per_min) / (Number(usage.fx_rate_inr) || 1),
      ),
    });
  }
  if (internal && usage.fx_rate_inr != null) {
    const src = usage.fx_source ? ` (${usage.fx_source})` : "";
    rows.push({ label: "FX USD→INR", value: `${Number(usage.fx_rate_inr)}${src}` });
  }
  const forensics = internal
    ? ((meta as CallMeta & { pstn_forensics?: Record<string, unknown> }).pstn_forensics ?? {})
    : {};
  const derived = (forensics.derived_ms || {}) as Record<string, number | null | undefined>;
  if (derived.answer_to_first_audio_sent != null) {
    rows.push({
      label: "Answer → first audio sent",
      value: `${derived.answer_to_first_audio_sent} ms`,
    });
  }
  const playback = (forensics.playback || {}) as Record<string, number | undefined>;
  if (playback.playout_underrun_count != null) {
    rows.push({ label: "Playout underruns", value: String(playback.playout_underrun_count) });
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

      {internal && Object.keys(stack).length > 0 && (
        <div className="mt-4">
          <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Resolved stack</p>
          <pre className="mt-2 max-h-40 overflow-auto rounded-skeuo-sm skeuo-inset p-3 font-mono text-[10px] text-text-muted">
            {JSON.stringify(stack, null, 2)}
          </pre>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        {internal ? (
          <>
            <SkeuoBadge tone="muted">meta.json</SkeuoBadge>
            <SkeuoBadge tone="muted">trace.json</SkeuoBadge>
            <SkeuoBadge tone="muted">transcript.jsonl</SkeuoBadge>
            <SkeuoBadge tone="muted">outcome.json</SkeuoBadge>
          </>
        ) : (
          <SkeuoBadge tone="muted">Billing and archive status</SkeuoBadge>
        )}
      </div>
    </SkeuoPanel>
  );
}
