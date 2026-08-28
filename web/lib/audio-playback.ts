export class AudioPlaybackManager {
  private el: HTMLAudioElement;
  private queue: Array<{ url: string; resolve: () => void; reject: (e: Error) => void }> = [];
  private playing = false;
  unlocked = false;

  constructor(audioEl: HTMLAudioElement) {
    this.el = audioEl;
    this.el.addEventListener("ended", () => this._onClipDone());
    this.el.addEventListener("error", () => {
      const mediaError = this.el.error;
      if (mediaError?.code === MediaError.MEDIA_ERR_ABORTED) {
        this._onClipDone();
        return;
      }
      this._onClipDone(new Error("audio error"));
    });
  }

  userGesture() {
    this.unlocked = true;
    if (!this.playing && this.queue.length) this._playNext();
  }

  enqueueBase64(b64: string, mime = "audio/wav"): Promise<void> {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const url = URL.createObjectURL(new Blob([bytes], { type: mime }));
    return this.enqueueUrl(url, true);
  }

  enqueueUrl(url: string, revoke = false): Promise<void> {
    return new Promise((resolve, reject) => {
      this.queue.push({ url, resolve, reject });
      if (!this.playing) this._playNext();
      if (revoke) {
        const item = this.queue[this.queue.length - 1];
        const orig = item.resolve;
        item.resolve = () => {
          URL.revokeObjectURL(url);
          orig();
        };
      }
    });
  }

  stop() {
    const pending = [...this.queue];
    this.queue = [];
    this.playing = false;
    for (const item of pending) {
      if (item.url.startsWith("blob:")) {
        URL.revokeObjectURL(item.url);
      }
      item.resolve();
    }
    try {
      this.el.pause();
    } catch {
      /* ignore */
    }
    const el = this.el;
    requestAnimationFrame(() => {
      if (this.playing || this.queue.length) return;
      el.removeAttribute("src");
      try {
        el.load();
      } catch {
        /* ignore */
      }
    });
  }

  private _onClipDone(err?: Error) {
    const item = this.queue.shift();
    if (item) {
      if (err) item.reject(err);
      else item.resolve();
    }
    this.playing = false;
    if (this.queue.length) this._playNext();
  }

  private _playNext() {
    if (!this.queue.length) return;
    if (!this.unlocked) return;
    const item = this.queue[0];
    this.playing = true;
    this.el.src = item.url;
    this.el.play().catch((e) => {
      if (e instanceof DOMException && (e.name === "AbortError" || e.message.includes("aborted"))) {
        this._onClipDone();
        return;
      }
      this._onClipDone(e instanceof Error ? e : new Error(String(e)));
    });
  }
}
