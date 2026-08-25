/**
 * pcm-worklet.js — AudioWorklet processor (ported from client/)
 */
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Int16Array(2048);
    this._offset = 0;
  }
  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const ch = input[0];
    for (let i = 0; i < ch.length; i++) {
      let s = ch[i];
      s = s < -1 ? -1 : s > 1 ? 1 : s;
      this._buffer[this._offset++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      if (this._offset >= this._buffer.length) {
        this.port.postMessage(this._buffer.buffer.slice(0), [this._buffer.buffer.slice(0)]);
        this._buffer = new Int16Array(2048);
        this._offset = 0;
      }
    }
    return true;
  }
}
registerProcessor("pcm-processor", PCMProcessor);
