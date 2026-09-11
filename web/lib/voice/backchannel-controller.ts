/** Client-side listening sounds while the user is still speaking (web Test Studio). */

export type BackchannelLang = "en-IN" | "te-IN" | "hi-IN";

const PHRASES: Record<BackchannelLang, string[]> = {
  "en-IN": ["Hmm.", "Mhm.", "Right.", "I see.", "Okay."],
  "te-IN": ["Hmm.", "Mhm.", "Aha.", "Sare.", "Avunu."],
  "hi-IN": ["Hmm.", "Haan.", "Achha.", "Theek hai."],
};

const MIN_SPEECH_MS = 750;
const PAUSE_MS = 280;
const COOLDOWN_MS = 2500;
const FIRE_PROBABILITY = 0.72;
const MIN_WORDS = 4;

function wordCount(text: string): number {
  const t = text.trim();
  if (!t) return 0;
  const spaced = t.split(/\s+/).filter(Boolean).length;
  return spaced >= 2 ? spaced : t.length >= 8 ? 2 : spaced;
}

function pickPhrase(lang: BackchannelLang): string {
  const pool = PHRASES[lang] || PHRASES["en-IN"];
  return pool[Math.floor(Math.random() * pool.length)];
}

export type BackchannelGate = {
  agentSpeaking: boolean;
  brainStreaming: boolean;
  listening: boolean;
};

export class BackchannelController {
  private speechStartedAt = 0;
  private lastPartialAt = 0;
  private lastFireAt = 0;
  private watchTimer: ReturnType<typeof setTimeout> | null = null;

  reset(): void {
    if (this.watchTimer) {
      clearTimeout(this.watchTimer);
      this.watchTimer = null;
    }
    this.speechStartedAt = 0;
    this.lastPartialAt = 0;
  }

  onPartial(text: string, gate: BackchannelGate, languageCode: BackchannelLang): void {
    if (!gate.listening || gate.agentSpeaking || gate.brainStreaming) {
      this.reset();
      return;
    }
    const words = wordCount(text);
    if (words < MIN_WORDS) return;
    const now = Date.now();
    if (this.speechStartedAt <= 0) this.speechStartedAt = now;
    this.lastPartialAt = now;
    if (this.watchTimer) clearTimeout(this.watchTimer);
    this.watchTimer = setTimeout(() => this.tryFire(gate, languageCode), PAUSE_MS);
  }

  onFinal(): void {
    this.reset();
  }

  private tryFire(gate: BackchannelGate, languageCode: BackchannelLang): void {
    this.watchTimer = null;
    if (!gate.listening || gate.agentSpeaking || gate.brainStreaming) return;
    const now = Date.now();
    if (now - this.lastPartialAt < PAUSE_MS * 0.85) return;
    if (this.speechStartedAt <= 0 || now - this.speechStartedAt < MIN_SPEECH_MS) return;
    if (this.lastFireAt && now - this.lastFireAt < COOLDOWN_MS) return;
    if (Math.random() > FIRE_PROBABILITY) return;
    this.lastFireAt = now;
    const phrase = pickPhrase(languageCode);
    if (typeof window === "undefined" || !window.speechSynthesis) return;
    try {
      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(phrase);
      utter.volume = 0.38;
      utter.rate = 1.05;
      window.speechSynthesis.speak(utter);
    } catch {
      /* ignore — optional UX polish */
    }
  }
}
