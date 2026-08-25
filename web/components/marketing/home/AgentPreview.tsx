export function AgentPreview() {
  const bars = [0.42, 0.7, 1, 0.58, 0.92, 0.48, 0.78, 0.4, 0.86, 0.52, 0.74, 0.46, 0.9, 0.6];

  return (
    <div className="overflow-hidden rounded-2xl border border-surface-border-subtle bg-surface-card shadow-card">
      <div className="flex items-center gap-2 border-b border-surface-border-subtle bg-surface-raised px-4 py-3">
        <span className="h-2.5 w-2.5 rounded-full bg-red-500/80" />
        <span className="h-2.5 w-2.5 rounded-full bg-warning/80" />
        <span className="h-2.5 w-2.5 rounded-full bg-surface-border" />
        <span className="ml-3 font-mono text-[11px] uppercase tracking-wider text-text-subtle">
          live · sales-agent · active call
        </span>
        <span className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-accent/30 bg-accent-dim px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-accent">
          <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-dot" />
          on call
        </span>
      </div>
      <div className="grid md:grid-cols-5">
        <div className="border-b border-surface-border-subtle p-5 md:col-span-2 md:border-b-0 md:border-r">
          <p className="label-caps text-text-subtle">Live transcript</p>
          <div className="mt-4 space-y-3">
            <div className="rounded-xl bg-surface-raised px-3 py-2.5">
              <p className="font-mono text-[10px] uppercase tracking-wider text-text-subtle">Caller · 0:08</p>
              <p className="mt-1 text-sm text-text">Hello, I wanted to ask about the flat price.</p>
            </div>
            <div className="rounded-xl border border-accent/25 bg-accent-dim/50 px-3 py-2.5">
              <p className="font-mono text-[10px] uppercase tracking-wider text-accent">Agent · 0:12</p>
              <p className="mt-1 text-sm text-text">Our project pricing starts from ₹45 lakh. I can share layout options.</p>
            </div>
          </div>
        </div>
        <div className="flex flex-col justify-between p-5 md:col-span-3">
          <div className="flex h-28 items-end justify-center gap-1.5" aria-hidden>
            {bars.map((h, i) => (
              <div
                key={i}
                className="wave-bar w-1.5 rounded-full bg-accent/80"
                style={{ height: `${h * 100}%`, animationDelay: `${i * 0.08}s` }}
              />
            ))}
          </div>
          <div className="mt-5 grid grid-cols-3 gap-2">
            {[
              { label: "STT", val: "98ms" },
              { label: "Brain", val: "142ms" },
              { label: "TTS", val: "46ms" },
            ].map((m) => (
              <div
                key={m.label}
                className="rounded-xl border border-surface-border-subtle bg-surface-raised px-2 py-2 text-center"
              >
                <p className="font-mono text-sm text-text">{m.val}</p>
                <p className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-text-subtle">{m.label}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
