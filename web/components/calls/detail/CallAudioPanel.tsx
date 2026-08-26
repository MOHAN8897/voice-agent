"use client";

import { useState } from "react";
import { SkeuoPanel } from "@/components/ui/skeuo/SkeuoPanel";
import { SkeuoButton } from "@/components/ui/skeuo/SkeuoButton";
import { cn } from "@/lib/cn";

type AudioKind = "mix" | "user" | "agent";

export function CallAudioPanel({ callId }: { callId: string }) {
  const [kind, setKind] = useState<AudioKind>("mix");
  const [failed, setFailed] = useState(false);
  const src = `/api/call/${callId}/audio/${kind}`;

  return (
    <SkeuoPanel title="Audio" description="Mix, user, and agent archives — scrub playback" padding="md">
      <div className="flex flex-wrap gap-2">
        {(["mix", "user", "agent"] as AudioKind[]).map((k) => (
          <SkeuoButton
            key={k}
            variant={kind === k ? "primary" : "secondary"}
            size="sm"
            onClick={() => {
              setKind(k);
              setFailed(false);
            }}
          >
            {k}
          </SkeuoButton>
        ))}
      </div>

      <div className="mt-4 skeuo-inset rounded-skeuo-md p-4">
        {!failed ? (
          <audio
            key={src}
            controls
            src={src}
            className="w-full"
            onError={() => setFailed(true)}
          />
        ) : (
          <p className="text-sm text-text-muted">
            {kind} archive not available yet — finalization may still be processing.
          </p>
        )}
      </div>

      <p className={cn("mt-2 font-mono text-[10px] text-text-subtle")}>
        USER AUDIO · scrub to correlate with transcript timeline below
      </p>
    </SkeuoPanel>
  );
}
