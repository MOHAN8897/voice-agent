/**
 * audio_playback_manager.js — Hands-free automatic playback engine
 */
class AudioPlaybackManager {
  constructor(audioEl) {
    this.el = audioEl;
    this.queue = [];
    this.playing = false;
    this.current = null;
    this.unlocked = false;
    this.onStarted = null;
    this.onFinished = null;
    this.onError = null;
    this.onBlocked = null;
    this.onLog = null;

    this.el.addEventListener("ended", () => {
      this._log("PLAY_ENDED", { currentTime: this.el.currentTime, duration: this.el.duration });
      this._onClipDone(null);
    });
    this.el.addEventListener("playing", () => {
      this._log("PLAY_STARTED", { currentTime: this.el.currentTime, readyState: this.el.readyState });
    });
    this.el.addEventListener("error", () => {
      const code = this.el.error ? this.el.error.code : "?";
      const msg = this.el.error ? this.el.error.message : "unknown";
      this._log("PLAY_ERROR", { code, msg });
      this._onClipDone(new Error("audio element error: " + msg));
    });
  }

  _log(tag, extra) {
    const line = `[VOICE][AUDIO] ${tag} ` + JSON.stringify({
      paused: this.el.paused,
      readyState: this.el.readyState,
      muted: this.el.muted,
      volume: this.el.volume,
      queueLen: this.queue.length,
      ...(extra || {}),
    });
    console.log(line);
    if (this.onLog) this.onLog(tag, extra);
  }

  userGesture() {
    this.unlocked = true;
    this._log("USER_GESTURE", {});
    if (!this.playing && this.queue.length > 0) this._playNext();
  }

  enqueueBase64(b64, mime = "audio/wav", meta = {}) {
    try {
      const decode = window.AudioUtils ? window.AudioUtils.base64ToArrayBuffer(b64) : (() => {
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        return bytes.buffer;
      })();
      return this.enqueueBytes(decode, mime, meta);
    } catch (e) {
      this._log("DECODE_ERROR", { message: String(e.message || e) });
      return Promise.reject(e);
    }
  }

  enqueueBytes(buffer, mime = "audio/wav", meta = {}) {
    if (!buffer || !buffer.byteLength) {
      this._log("EMPTY_BUFFER", {});
      return Promise.reject(new Error("empty audio buffer"));
    }
    const url = URL.createObjectURL(new Blob([buffer], { type: mime }));
    this._log("CHUNK_RECEIVED", { bytes: buffer.byteLength, mime });
    return this.enqueueUrl(url, { ...meta, _revoke: true, bytes: buffer.byteLength, mime });
  }

  enqueueUrl(url, meta = {}) {
    return new Promise((resolve, reject) => {
      this.queue.push({ url, meta, resolve, reject });
      this._log("ENQUEUED", { url: url.slice(0, 40), queueLen: this.queue.length });
      if (!this.playing) this._playNext();
    });
  }

  async _playNext() {
    if (this.playing) return;
    const item = this.queue.shift();
    if (!item) return;
    this.playing = true;
    this.current = item;

    const cleanup = () => {
      if (item.meta && item.meta._revoke && item.url.startsWith("blob:")) {
        try { URL.revokeObjectURL(item.url); } catch {}
      }
      this.current = null;
      this.playing = false;
    };

    try {
      this.el.muted = false;
      this.el.volume = 1.0;
      this.el.src = item.url;
      this.el.load();
      this._log("PLAY_REQUEST", { bytes: item.meta?.bytes, mime: item.meta?.mime });
      await this.el.play();
      this.unlocked = true;
      if (this.onStarted) this.onStarted(item);
    } catch (err) {
      const name = err && err.name;
      this._log(name === "NotAllowedError" ? "PLAY_BLOCKED" : "PLAY_ERROR", { name, message: String(err.message || err) });
      if (name === "NotAllowedError" || String(err.message || "").toLowerCase().includes("autoplay")) {
        this.queue.unshift(item);
        cleanup();
        if (this.onBlocked) this.onBlocked();
        return;
      }
      cleanup();
      if (this.onError) this.onError(err, item);
      item.resolve({ skipped: true, error: String(err && err.message || err) });
      this._playNext();
    }
  }

  _onClipDone(err) {
    if (!this.playing) return;
    const item = this.current;
    this.playing = false;
    if (item) {
      if (item.meta && item.meta._revoke && item.url.startsWith("blob:")) {
        try { URL.revokeObjectURL(item.url); } catch {}
      }
      if (err) {
        if (this.onError) this.onError(err, item);
        item.resolve({ skipped: true, error: String(err.message || err) });
      } else {
        item.resolve({ ok: true });
        if (this.onFinished) this.onFinished(item);
      }
    }
    this.current = null;
    this._playNext();
  }

  stopAll() {
    const had = this.queue.length > 0 || this.playing;
    const pending = this.queue.splice(0, this.queue.length);
    for (const p of pending) p.resolve({ skipped: true, reason: "stopped" });
    this.current = null;
    this.playing = false;
    try { this.el.pause(); } catch {}
    try { this.el.removeAttribute("src"); this.el.load(); } catch {}
    this._log("STOP_ALL", { had });
    if (had && this.onFinished) this.onFinished({ stopped: true });
  }
}

window.AudioPlaybackManager = AudioPlaybackManager;
