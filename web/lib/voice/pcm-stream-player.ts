/** Low-latency PCM stream player — schedules linear16 via Web Audio (reference: client/app.js). */
export type PcmStreamPlayer = {
  sampleRate: number;
  hadAudio: () => boolean;
  idle: () => boolean;
  reset: () => void;
  appendPcm16: (arrayBuffer: ArrayBuffer) => void;
  waitUntilIdle: (timeoutMs?: number) => Promise<void>;
};

export function createPcmStreamPlayer(ctx: AudioContext, sampleRate = 24000): PcmStreamPlayer {
  let nextTime = 0;
  const sources = new Set<AudioBufferSourceNode>();
  let hadAudio = false;

  const reset = () => {
    nextTime = 0;
    for (const s of sources) {
      try {
        s.stop();
      } catch {
        /* ignore */
      }
    }
    sources.clear();
    hadAudio = false;
  };

  const appendPcm16 = (arrayBuffer: ArrayBuffer) => {
    if (!arrayBuffer?.byteLength) return;
    hadAudio = true;
    const int16 = new Int16Array(arrayBuffer);
    const floats = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) floats[i] = int16[i] / 32768;
    const buf = ctx.createBuffer(1, floats.length, sampleRate);
    buf.getChannelData(0).set(floats);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    const now = ctx.currentTime;
    if (nextTime < now + 0.02) nextTime = now + 0.02;
    src.start(nextTime);
    nextTime += buf.duration;
    sources.add(src);
    src.onended = () => sources.delete(src);
  };

  const waitUntilIdle = (timeoutMs = 120_000) =>
    new Promise<void>((resolve) => {
      const t0 = Date.now();
      const tick = () => {
        if (sources.size === 0 && ctx.currentTime >= nextTime - 0.05) {
          resolve();
          return;
        }
        if (Date.now() - t0 > timeoutMs) {
          resolve();
          return;
        }
        setTimeout(tick, 40);
      };
      tick();
    });

  return {
    sampleRate,
    hadAudio: () => hadAudio,
    idle: () => sources.size === 0 && ctx.currentTime >= nextTime - 0.05,
    reset,
    appendPcm16,
    waitUntilIdle,
  };
}
