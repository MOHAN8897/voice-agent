/**
 * pcm-worklet.js — AudioWorklet processor
 * Captures mic Float32 → converts to Int16 linear16 PCM, posts ~128ms chunks.
 * Used by /ws/stt-realtime (browser → server → Sarvam saaras:v3-realtime).
 */
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Int16Array(2048); // ~128ms @16kHz mono
    this._offset = 0;
  }
  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const ch = input[0];
    for (let i = 0; i < ch.length; i++) {
      // clamp + convert float [-1,1] → int16
      let s = ch[i];
      s = s < -1 ? -1 : s > 1 ? 1 : s;
      this._buffer[this._offset++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      if (this._offset >= this._buffer.length) {
        this.port.postMessage(this._buffer.buffer.slice(0), [this._buffer.buffer.slice(0)]);
        // postMessage with transfer — recreate buffer
        this._buffer = new Int16Array(2048);
        this._offset = 0;
      }
    }
    return true;
  }
}
registerProcessor("pcm-processor", PCMProcessor);
