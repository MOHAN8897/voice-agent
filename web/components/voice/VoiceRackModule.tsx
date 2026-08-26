import { SkeuoStatusLight } from "@/components/ui/skeuo/SkeuoStatusLight";
import { SkeuoBadge } from "@/components/ui/skeuo/SkeuoBadge";
import { cn } from "@/lib/cn";

type Stage = "stt" | "llm" | "tts";

const STAGE_LABEL: Record<Stage, string> = {
  stt: "STT",
  llm: "LLM",
  tts: "TTS",
};

const STAGE_MODE: Record<Stage, string> = {
  stt: "REALTIME",
  llm: "STREAMING",
  tts: "STREAMING",
};

export function VoiceRackModule({
  stage,
  provider,
  model,
  language,
  healthy,
  configured,
  className,
}: {
  stage: Stage;
  provider?: string;
  model?: string;
  language?: string;
  healthy?: boolean;
  configured?: boolean;
  className?: string;
}) {
  const status = !configured ? "idle" : healthy ? "ok" : "warn";
  const statusLabel = !configured ? "Not configured" : healthy ? "Healthy" : "Degraded";

  return (
    <article
      className={cn(
        "skeuo-rack-module relative rounded-skeuo-lg border border-surface-border-subtle skeuo-panel overflow-hidden",
        className
      )}
    >
      <div className="absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-border-highlight/25 via-transparent to-transparent" aria-hidden />

      <header className="flex items-center justify-between gap-3 border-b border-surface-border-subtle px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="skeuo-inset flex h-10 w-10 items-center justify-center rounded-skeuo-sm font-mono text-xs font-bold text-accent-primary">
            {STAGE_LABEL[stage]}
          </div>
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-subtle">Rack module</p>
            <p className="text-sm font-medium text-text">{STAGE_LABEL[stage]} pipeline</p>
          </div>
        </div>
        <SkeuoStatusLight status={status} label={statusLabel} />
      </header>

      <div className="p-4 space-y-3">
        <div className="skeuo-inset rounded-skeuo-md px-3 py-3">
          <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Provider</p>
          <p className="mt-1 text-lg font-semibold tracking-tight text-text capitalize">
            {provider || "—"}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="skeuo-inset rounded-skeuo-sm px-3 py-2">
            <p className="font-mono text-[9px] uppercase tracking-wider text-text-subtle">Model</p>
            <p className="mt-0.5 font-mono text-xs text-text truncate">{model || "—"}</p>
          </div>
          <div className="skeuo-inset rounded-skeuo-sm px-3 py-2">
            <p className="font-mono text-[9px] uppercase tracking-wider text-text-subtle">Language</p>
            <p className="mt-0.5 font-mono text-xs text-text">{language || "—"}</p>
          </div>
        </div>
        <SkeuoBadge tone="info">{STAGE_MODE[stage]}</SkeuoBadge>
      </div>
    </article>
  );
}
