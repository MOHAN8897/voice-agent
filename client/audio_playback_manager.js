/**
 * audio_playback_manager.js — Hands-free automatic playback engine
 *
 * Industry-standard behaviors:
 *  • FIFO queue — multiple responses play back-to-back, never overlap
 *  • Auto-play immediately on enqueue (no Play button)
 *  • Autoplay-policy recovery: browsers allow audio after ANY prior user gesture.
 *    If blocked (NotAllowedError), we surface ONE "Enable voice" tap, then every
 *    future playback is silent-start for the session.
 *  • Non-blocking: playback is fully async; callers get a Promise per clip that
 *    resolves when that clip finishes (or is skipped).
 *  • Completion notification: onFinished(item) → conversation manager re-opens mic.
 *  • stopAll() for barge-in / session end; skips queue cleanly.
 *  • Errors: decode/play failures skip to next item via onError, never hang UI.
 */
class AudioPlaybackManager {
  constructor(audioEl) {
    this.el = audioEl;
    this.queue = [];
    this.playing = false;
    this.current = null;          // {url, mime, resolve, reject, meta}
    this.unlocked = false;
    this.onStarted = null;        // (item) => void
    this.onFinished = null;       // (item) => void   ← conversation manager hook
    this.onError = null;          // (err, item) => void
    this.onBlocked = null;        // () => void       ← show unlock overlay once
    this._objectUrls = new Set();

    // Element-level wiring
    this.el.addEventListener("ended", () => this._onClipDone(null));
    this.el.addEventListener("error", () => {
      const err = new Error("audio element error: " + (this.el.error ? this.el.error.message : "unknown"));
      this._onClipDone(err);
    });
  }

  /** Call from any real user gesture (mic click). Unlocks future autoplay. */
  userGesture() {
    this.unlocked = true;
    // If something was queued while blocked, start it now
    if (!this.playing && this.queue.length > 0) this._playNext();
  }

  /** Enqueue base64-encoded audio. Returns promise resolving when THIS clip finishes. */
  enqueueBase64(b64, mime = "audio/wav", meta = {}) {
    try {
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      return this.enqueueBytes(bytes.buffer, mime, meta);
    } catch (e) {
      return Promise.reject(e);
    }
  }

  /** Enqueue raw ArrayBuffer. */
  enqueueBytes(buffer, mime = "audio/wav", meta = {}) {
    const url = URL.createObjectURL(new Blob([buffer], { type: mime }));
    return this.enqueueUrl(url, { ...meta, _revoke: true });
  }

  /** Enqueue an object URL (ownership stays with caller unless meta._revoke). */
  enqueueUrl(url, meta = {}) {
    return new Promise((resolve, reject) => {
      this.queue.push({ url, meta, resolve, reject });
      // Never let the visual queue grow unbounded (barge-in clears it anyway)
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
      // Some browsers need the element attached & resumed after gesture
      this.el.src = item.url;
      this.el.load();
      await this.el.play().catch((e) => { throw e; });
      this.unlocked = true;
      if (this.onStarted) this.onStarted(item);
    } catch (err) {
      if (err && (err.name === "NotAllowedError" || String(err.message || "").toLowerCase().includes("autoplay"))) {
        // Autoplay policy: park at head of queue and request one-time unlock
        this.queue.unshift(item);
        cleanup();
        if (this.onBlocked) this.onBlocked();
        return;
      }
      // Any other error → report + skip this clip
      cleanup();
      if (this.onError) this.onError(err, item);
      item.resolve({ skipped: true, error: String(err && err.message || err) });
      this._playNext();
      return;
    }
  }

  /** Internal: current clip finished (ended or errored). */
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
        if (this.onFinished) this.onFinished(item);   // ← notify conversation manager
      }
    }
    this.current = null;
    this._playNext();
  }

  /** Barge-in / stop-everything: drop queue + kill current instantly. */
  stopAll() {
    const had = this.queue.length > 0 || this.playing;
    const pending = this.queue.splice(0, this.queue.length);
    for (const p of pending) p.resolve({ skipped: true, reason: "stopped" });
    if (this.current) {
      const cur = this.current;
      this.current = null;
    }
    this.playing = false;
    try { this.el.pause(); } catch {}
    try { this.el.removeAttribute("src"); this.el.load(); } catch {}
    if (had && this.onFinished) this.onFinished({ stopped: true });
  }
}

// Expose globally (plain-script bundle)
window.AudioPlaybackManager = AudioPlaybackManager;
