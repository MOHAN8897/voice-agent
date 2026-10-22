/**
 * pcm-worklet.js — mix all mic channels to mono, downsample to 16 kHz linear16 PCM.
 * Always emit 16 kHz so Sarvam STT gets the rate it supports (8000 | 16000).
 */
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._outRate = 16000;
    this._acc = 0;
    this._accN = 0;
    this._need = Math.max(1, sampleRate / this._outRate);
    this._buffer = new Int16Array(2048);
    this._offset = 0;
  }

  _emit(sample) {
    let s = sample;
    if (s < -1) s = -1;
    else if (s > 1) s = 1;
    this._buffer[this._offset++] = s < 0 ? s * 0x8000 : s * 0x7fff;
    if (this._offset >= this._buffer.length) {
      const copy = this._buffer.slice();
      this.port.postMessage(copy.buffer, [copy.buffer]);
      this._offset = 0;
    }
  }

  process(inputs) {
    const chans = inputs[0];
    if (!chans || !chans[0] || chans[0].length === 0) return true;
    const frames = chans[0].length;
    const nch = chans.length;
    for (let i = 0; i < frames; i++) {
      let mixed = 0;
      for (let c = 0; c < nch; c++) {
        const ch = chans[c];
        if (ch) mixed += ch[i] || 0;
      }
      mixed /= nch;
      this._acc += mixed;
      this._accN += 1;
      if (this._accN >= this._need) {
        this._emit(this._acc / this._accN);
        this._acc = 0;
        this._accN = 0;
      }
    }
    return true;
  }
}
registerProcessor("pcm-processor", PCMProcessor);
