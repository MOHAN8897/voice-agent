/**
 * Short playback through the live AudioContext so browser AEC can converge
 * before the first user turn (recommended for mobile speakerphone).
 */
export async function warmupBrowserAec(ctx: AudioContext, durationMs = 280): Promise<void> {
  if (ctx.state === "suspended") {
    await ctx.resume();
  }
  const sampleRate = ctx.sampleRate;
  const length = Math.max(1, Math.floor((sampleRate * durationMs) / 1000));
  const buffer = ctx.createBuffer(1, length, sampleRate);
  const data = buffer.getChannelData(0);
  // Very quiet noise — audible enough for AEC reference, not user-perceptible.
  for (let i = 0; i < length; i += 1) {
    data[i] = (Math.random() * 2 - 1) * 0.018;
  }
  const src = ctx.createBufferSource();
  src.buffer = buffer;
  const gain = ctx.createGain();
  gain.gain.value = 0.35;
  src.connect(gain);
  gain.connect(ctx.destination);
  await new Promise<void>((resolve) => {
    src.onended = () => resolve();
    src.start();
  });
}
