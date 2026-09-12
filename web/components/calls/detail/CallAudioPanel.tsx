"use client";

import { useEffect, useState } from "react";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { cn } from "@/lib/cn";

type AudioKind = "mix" | "user" | "agent";

const KIND_LABEL: Record<AudioKind, string> = {
  mix: "Mix (both)",
  user: "Caller",
  agent: "Agent",
};

export function CallAudioPanel({
  callId,
  title = "Play recording",
  description = "After hangup — mix, caller, and agent as WAV",
}: {
  callId: string;
  title?: string;
  description?: string;
}) {
  const [kind, setKind] = useState<AudioKind>("mix");
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const src = `/api/call/${callId}/audio/${kind}?r=${retry}`;

  useEffect(() => {
    setFailed(false);
    setRetry(0);
  }, [callId, kind]);

  useEffect(() => {
    if (!failed || retry >= 8) return;
    const timer = window.setTimeout(() => {
      setFailed(false);
      setRetry((n) => n + 1);
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [failed, retry]);

  return (
    <SkeuoPanel title={title} description={description} padding="md">
      <div className="flex flex-wrap gap-2">
        {(["mix", "user", "agent"] as AudioKind[]).map((k) => (
          <SkeuoButton
            key={k}
            variant={kind === k ? "primary" : "secondary"}
            size="sm"
            onClick={() => {
              setKind(k);
              setFailed(false);
              setRetry(0);
            }}
          >
            {KIND_LABEL[k]}
          </SkeuoButton>
        ))}
      </div>

      <div className="mt-4 skeuo-inset rounded-skeuo-md p-4">
        {!failed ? (
          <audio
            key={src}
            controls
            preload="metadata"
            src={src}
            className="w-full"
            onError={() => setFailed(true)}
          />
        ) : (
          <p className="text-sm text-text-muted">
            {KIND_LABEL[kind]} archive not available yet — hang up and wait a few seconds for mix.wav.
          </p>
        )}
      </div>

      <p className={cn("mt-2 font-mono text-[10px] text-text-subtle")}>
        Use the player controls to play / pause / scrub · Mix is stereo (L=caller R=agent)
      </p>
    </SkeuoPanel>
  );
}
