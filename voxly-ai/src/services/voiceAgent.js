/**
 * Voxly Voice Agent Service Adapter
 * Provides a clean interface for STT, LLM conversation, TTS audio playback,
 * and real-time Web Audio API AnalyserNode integration for 3D character lip-sync.
 */

class VoiceAgentAdapter {
  constructor() {
    this.audioContext = null;
    this.analyser = null;
    this.mediaStream = null;
    this.isListening = false;
    this.isSpeaking = false;
    this.currentUtterance = null;
    this.currentAudioElement = null;
    this.listeners = new Set();
    this.mockResponses = [
      "Hello! I am Voxly, your autonomous voice employee. I can qualify incoming leads, book appointments directly into your calendar, and answer complex customer questions 24/7.",
      "Yes, absolutely! I integrate directly with Salesforce, HubSpot, and your phone lines. Setup takes under 5 minutes without writing a single line of code.",
      "I handle over 500 concurrent conversations with natural human turn-taking, sub-400 millisecond response times, and sentiment tracking.",
      "Would you like me to start a live inbound qualification demo or schedule a workflow test for your team?",
    ];
    this.responseIndex = 0;
    this.availableVoices = [];
    this.playbackToken = 0;

    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      const loadVoices = () => {
        try {
          this.availableVoices = window.speechSynthesis.getVoices() || [];
        } catch (e) {
          this.availableVoices = [];
        }
      };
      loadVoices();
      window.speechSynthesis.onvoiceschanged = loadVoices;
    }
  }

  ensureAudioContext() {
    if (!this.audioContext) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) {
        this.audioContext = new AudioContextClass();
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = 256;
        this.analyser.smoothingTimeConstant = 0.8;
      }
    }
    if (this.audioContext && this.audioContext.state === 'suspended') {
      this.audioContext.resume().catch(() => {});
    }
    return this.audioContext;
  }

  getAnalyser() {
    this.ensureAudioContext();
    return this.analyser;
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  notify(event, data) {
    for (const listener of this.listeners) {
      try {
        listener(event, data);
      } catch (e) {}
    }
  }

  async startListening({ onSpeechResult, onError } = {}) {
    this.ensureAudioContext();

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      if (onError) onError(new Error("Microphone API not supported in this browser."));
      return false;
    }

    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.isListening = true;
      this.notify('stateChange', { state: 'LISTENING', text: 'Listening to your voice...' });

      // Connect microphone to an analyser
      if (this.audioContext && this.mediaStream) {
        try {
          const source = this.audioContext.createMediaStreamSource(this.mediaStream);
          // Only route to analyser, NOT to audioContext.destination to avoid feedback loop
          if (this.analyser) {
            source.connect(this.analyser);
          }
        } catch (e) {}
      }

      // SpeechRecognition support
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SpeechRecognition) {
        const recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'en-US';

        recognition.onresult = (event) => {
          const transcript = event.results[0]?.[0]?.transcript || '';
          this.stopListening();
          if (onSpeechResult) onSpeechResult(transcript);
          this.handleUserInput(transcript);
        };

        recognition.onerror = (e) => {
          this.stopListening();
          if (onSpeechResult) onSpeechResult("Can you tell me how Voxly handles voice calls?");
          this.handleUserInput("Can you tell me how Voxly handles voice calls?");
        };

        recognition.start();
        this.recognition = recognition;
      } else {
        // Fallback simulation timer for browsers without SpeechRecognition
        setTimeout(() => {
          if (this.isListening) {
            this.stopListening();
            const fallbackText = "Tell me how Voxly qualifies inbound leads.";
            if (onSpeechResult) onSpeechResult(fallbackText);
            this.handleUserInput(fallbackText);
          }
        }, 2800);
      }

      return true;
    } catch (err) {
      console.warn("Microphone access denied or unavailable:", err);
      if (onError) onError(err);
      this.notify('error', { message: "Microphone access is needed for live conversation." });
      return false;
    }
  }

  stopListening() {
    this.isListening = false;
    if (this.recognition) {
      try {
        this.recognition.stop();
      } catch (e) {}
      this.recognition = null;
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => {
        try {
          track.stop();
        } catch (e) {}
      });
      this.mediaStream = null;
    }
  }

  handleUserInput(userText) {
    this.notify('stateChange', { state: 'THINKING', userText });

    // Response generation with natural latency
    setTimeout(() => {
      let response = this.mockResponses[this.responseIndex % this.mockResponses.length];
      this.responseIndex++;

      const lower = userText.toLowerCase();
      if (lower.includes('price') || lower.includes('cost')) {
        response = "We charge a simple flat rate of 9.5 cents per minute with pure per-second metering. Unanswered rings and busy signals are always completely free.";
      } else if (lower.includes('transfer') || lower.includes('human')) {
        response = "I immediately perform warm transfers to your human team members, passing a full live audio transcript so they have complete context.";
      } else if (lower.includes('crm') || lower.includes('integrate') || lower.includes('salesforce') || lower.includes('hubspot')) {
        response = "I sync bi-directionally with HubSpot, Salesforce, Cal.com, and Google Calendar. Every qualified lead and appointment is posted autonomously.";
      } else if (lower.includes('fast') || lower.includes('latency') || lower.includes('speed')) {
        response = "My voice response latency is under 350 milliseconds — completely imperceptible from human conversation.";
      }

      this.playTTS(response);
    }, 450);
  }

  /**
   * Play rich, audible futuristic robotic acoustic sound effects via Web Audio API.
   * High-fidelity harmonic synthesis with volume calibrated to industry standards (~0.45 gain).
   */
  async playRobotSound(type = 'chime') {
    const ctx = this.ensureAudioContext();
    if (!ctx) return;
    if (ctx.state === 'suspended') {
      try {
        await ctx.resume();
      } catch (e) {}
    }

    try {
      const now = ctx.currentTime;
      const gain = ctx.createGain();
      gain.gain.setValueAtTime(0.45, now);

      if (type === 'wave' || type === 'happy') {
        // Upbeat melodic two-step chirp (C5 -> G5, E5 -> C6)
        const osc1 = ctx.createOscillator();
        const osc2 = ctx.createOscillator();
        osc1.type = 'sine';
        osc2.type = 'triangle';
        osc1.frequency.setValueAtTime(523.25, now);
        osc1.frequency.exponentialRampToValueAtTime(783.99, now + 0.12);
        osc2.frequency.setValueAtTime(659.25, now + 0.04);
        osc2.frequency.exponentialRampToValueAtTime(1046.5, now + 0.22);

        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.32);
        osc1.connect(gain);
        osc2.connect(gain);
        gain.connect(ctx.destination);
        if (this.analyser) gain.connect(this.analyser);

        osc1.start(now);
        osc2.start(now + 0.04);
        osc1.stop(now + 0.33);
        osc2.stop(now + 0.33);
      } else if (type === 'roll' || type === 'spin') {
        // High-energy ascending acrobatic arpeggiated sweep
        const osc = ctx.createOscillator();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(320, now);
        osc.frequency.exponentialRampToValueAtTime(1400, now + 0.28);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.32);
        osc.connect(gain);
        gain.connect(ctx.destination);
        if (this.analyser) gain.connect(this.analyser);
        osc.start(now);
        osc.stop(now + 0.33);
      } else if (type === 'think') {
        // Thoughtful dual harmonic sonar pulse
        const osc1 = ctx.createOscillator();
        const osc2 = ctx.createOscillator();
        osc1.type = 'sine';
        osc2.type = 'sine';
        osc1.frequency.setValueAtTime(440, now);
        osc1.frequency.linearRampToValueAtTime(880, now + 0.2);
        osc2.frequency.setValueAtTime(660, now);
        osc2.frequency.linearRampToValueAtTime(1320, now + 0.2);

        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
        osc1.connect(gain);
        osc2.connect(gain);
        gain.connect(ctx.destination);
        if (this.analyser) gain.connect(this.analyser);

        osc1.start(now);
        osc2.start(now);
        osc1.stop(now + 0.31);
        osc2.stop(now + 0.31);
      } else if (type === 'celebrate') {
        // Triumphant fanfare arpeggio (C5 -> E5 -> G5 -> C6)
        const notes = [523.25, 659.25, 783.99, 1046.5];
        notes.forEach((freq, idx) => {
          const osc = ctx.createOscillator();
          const noteGain = ctx.createGain();
          const noteStart = now + idx * 0.07;
          osc.type = 'triangle';
          osc.frequency.setValueAtTime(freq, noteStart);
          noteGain.gain.setValueAtTime(0.4, noteStart);
          noteGain.gain.exponentialRampToValueAtTime(0.001, noteStart + 0.25);
          osc.connect(noteGain);
          noteGain.connect(ctx.destination);
          if (this.analyser) noteGain.connect(this.analyser);
          osc.start(noteStart);
          osc.stop(noteStart + 0.26);
        });
      } else if (type === 'dance') {
        // Funky futuristic 3-tone rhythmic bounce
        const notes = [440, 587.33, 880];
        notes.forEach((freq, idx) => {
          const osc = ctx.createOscillator();
          const noteGain = ctx.createGain();
          const noteStart = now + idx * 0.09;
          osc.type = 'sawtooth';
          osc.frequency.setValueAtTime(freq, noteStart);
          noteGain.gain.setValueAtTime(0.25, noteStart);
          noteGain.gain.exponentialRampToValueAtTime(0.001, noteStart + 0.16);
          osc.connect(noteGain);
          noteGain.connect(ctx.destination);
          if (this.analyser) noteGain.connect(this.analyser);
          osc.start(noteStart);
          osc.stop(noteStart + 0.17);
        });
      } else if (type === 'tickle' || type === 'pouty') {
        // Playful double warble
        const osc = ctx.createOscillator();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(800, now);
        osc.frequency.linearRampToValueAtTime(550, now + 0.08);
        osc.frequency.linearRampToValueAtTime(950, now + 0.16);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
        osc.connect(gain);
        gain.connect(ctx.destination);
        if (this.analyser) gain.connect(this.analyser);
        osc.start(now);
        osc.stop(now + 0.26);
      } else {
        // Standard high-clarity harmonic greeting chime (587Hz -> 880Hz / 440Hz -> 659Hz)
        const osc1 = ctx.createOscillator();
        const osc2 = ctx.createOscillator();
        osc1.type = 'sine';
        osc2.type = 'triangle';
        osc1.frequency.setValueAtTime(587.33, now);
        osc1.frequency.exponentialRampToValueAtTime(880.0, now + 0.1);
        osc2.frequency.setValueAtTime(440.0, now);
        osc2.frequency.exponentialRampToValueAtTime(659.25, now + 0.1);

        gain.gain.setValueAtTime(0.45, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);

        osc1.connect(gain);
        osc2.connect(gain);
        gain.connect(ctx.destination);
        if (this.analyser) gain.connect(this.analyser);

        osc1.start(now);
        osc2.start(now);
        osc1.stop(now + 0.36);
        osc2.stop(now + 0.36);
      }
    } catch (e) {
      console.warn('Robot sound synthesis error:', e);
    }
  }

  playTTS(text, onEnd, onStart, options = {}) {
    this.stopTTS(false);
    const currentToken = ++this.playbackToken;

    this.ensureAudioContext();
    this.isSpeaking = true;
    this.notify('stateChange', { state: 'TALKING', responseText: text });

    // High-clarity acoustic connect chime (calibrated to audible 0.35 gain)
    this.playRobotSound(options.soundType || 'chime');

    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      try {
        if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
          window.speechSynthesis.cancel();
        }
        window.speechSynthesis.resume();
      } catch (e) {}

      const utterance = new SpeechSynthesisUtterance(text);
      // Fast, energetic childish robot voice defaults (user-requested)
      utterance.rate = options.rate || options.speed || 1.15;
      utterance.pitch = options.pitch !== undefined ? (1.0 + options.pitch) : 1.3;
      utterance.volume = 1.0; // Maximum volume for robust audibility

      // Pick a friendly, high-quality, high-gain voice
      const voices = this.availableVoices.length > 0 ? this.availableVoices : window.speechSynthesis.getVoices();
      if (voices && voices.length > 0) {
        let preferredVoice = null;
        if (options.voiceName) {
          preferredVoice = voices.find((v) => v.name.toLowerCase().includes(options.voiceName.toLowerCase()));
        }
        if (!preferredVoice) {
          preferredVoice = voices.find(
            (v) => v.lang.startsWith('en') && (
              v.name.includes('Google') ||
              v.name.includes('Natural') ||
              v.name.includes('Jenny') ||
              v.name.includes('Aria') ||
              v.name.includes('Guy') ||
              v.name.includes('Samantha') ||
              v.name.includes('Daniel') ||
              v.name.includes('Zira')
            )
          ) || voices.find((v) => v.lang.startsWith('en'));
        }
        if (preferredVoice) utterance.voice = preferredVoice;
      }

      let osc = null;
      let gain = null;

      if (this.audioContext && this.analyser) {
        try {
          osc = this.audioContext.createOscillator();
          gain = this.audioContext.createGain();
          gain.gain.value = 0.0001;
          osc.frequency.setValueAtTime(240, this.audioContext.currentTime);
          osc.connect(gain);
          gain.connect(this.analyser);
          osc.start();
        } catch (e) {}
      }

      let hasCleanedUp = false;
      const cleanup = () => {
        if (hasCleanedUp) return;
        hasCleanedUp = true;
        if (osc) {
          try {
            osc.stop();
            gain.disconnect();
          } catch (e) {}
          osc = null;
        }
        if (this.playbackToken === currentToken) {
          this.isSpeaking = false;
          this.currentUtterance = null;
          this.notify('stateChange', { state: 'IDLE' });
        }
      };

      utterance.onstart = () => {
        if (this.playbackToken === currentToken && onStart) onStart();
      };

      utterance.onend = () => {
        if (this.playbackToken === currentToken) {
          cleanup();
          if (onEnd) onEnd();
        }
      };

      utterance.onerror = () => {
        if (this.playbackToken === currentToken) {
          cleanup();
          if (onEnd) onEnd();
        }
      };

      this.currentUtterance = utterance;

      try {
        window.speechSynthesis.speak(utterance);
      } catch (e) {
        if (this.playbackToken === currentToken) {
          cleanup();
          if (onEnd) onEnd();
        }
      }

      // Safety timeout: Chrome can sometimes hang onend for long utterances
      const estimatedDurationMs = Math.max(2000, (text.split(' ').length / 2.5) * 1000 + 1500);
      setTimeout(() => {
        if (this.isSpeaking && this.currentUtterance === utterance && this.playbackToken === currentToken) {
          cleanup();
          if (onEnd) onEnd();
        }
      }, estimatedDurationMs);
    } else {
      setTimeout(() => {
        if (this.playbackToken === currentToken) {
          this.isSpeaking = false;
          this.notify('stateChange', { state: 'IDLE' });
          if (onEnd) onEnd();
        }
      }, 2500);
    }
  }

  /**
   * Play high-quality neural voice audio clips with seamless fallback to SpeechSynthesis.
   * Feeds the Web Audio AnalyserNode for 3D character lip-sync and plays at full volume.
   */
  playAudioClip(audioUrl, onEnd, onStart, options = {}) {
    this.stopTTS(false);
    const currentToken = ++this.playbackToken;

    this.ensureAudioContext();
    this.isSpeaking = true;
    this.notify('stateChange', { state: 'TALKING', audioUrl });

    if (options.playSoundEffect) {
      this.playRobotSound(options.soundType || 'chime');
    }

    const fallbackText = options.fallbackText || options.speech;

    let osc = null;
    let gain = null;
    let mediaSource = null;

    try {
      const audio = new Audio();
      audio.crossOrigin = 'anonymous';
      audio.src = audioUrl;
      audio.volume = 1.0;
      audio.preload = 'auto';
      this.currentAudioElement = audio;

      // Route audio through Web Audio API for analyser lip-sync
      if (this.audioContext && this.analyser) {
        try {
          mediaSource = this.audioContext.createMediaElementSource(audio);
          mediaSource.connect(this.analyser);
          mediaSource.connect(this.audioContext.destination);
        } catch (e) {
          // Fallback: create a synthetic oscillator for lip-sync simulation
          try {
            osc = this.audioContext.createOscillator();
            gain = this.audioContext.createGain();
            gain.gain.value = 0.0001;
            osc.frequency.setValueAtTime(240, this.audioContext.currentTime);
            osc.connect(gain);
            gain.connect(this.analyser);
            osc.start();
          } catch (e2) {}
        }
      }

      let hasCleanedUp = false;
      const cleanup = () => {
        if (hasCleanedUp) return;
        hasCleanedUp = true;
        if (osc) {
          try {
            osc.stop();
            gain.disconnect();
          } catch (e) {}
          osc = null;
        }
        if (mediaSource) {
          try {
            mediaSource.disconnect();
          } catch (e) {}
          mediaSource = null;
        }
        if (this.playbackToken === currentToken) {
          this.isSpeaking = false;
          this.currentAudioElement = null;
          this.notify('stateChange', { state: 'IDLE' });
        }
      };

      audio.onplay = () => {
        if (this.playbackToken === currentToken && onStart) onStart();
      };

      audio.onended = () => {
        if (this.playbackToken === currentToken) {
          cleanup();
          if (onEnd) onEnd();
        }
      };

      audio.onerror = (e) => {
        if (this.playbackToken !== currentToken) return;
        console.warn('Audio element error, falling back to speech synthesis:', e);
        cleanup();
        if (fallbackText) {
          this.playTTS(fallbackText, onEnd, onStart, options);
        }
      };

      const playPromise = audio.play();
      if (playPromise !== undefined) {
        playPromise.catch((err) => {
          if (this.playbackToken !== currentToken || err.name === 'AbortError') return;
          console.warn('Audio play() promise failed, falling back to speech synthesis:', err);
          cleanup();
          if (fallbackText) {
            this.playTTS(fallbackText, onEnd, onStart, options);
          }
        });
      }
    } catch (e) {
      if (this.playbackToken !== currentToken) return;
      console.warn('playAudioClip exception, falling back to speech synthesis:', e);
      if (fallbackText) {
        this.playTTS(fallbackText, onEnd, onStart, options);
      } else {
        this.isSpeaking = false;
        this.notify('stateChange', { state: 'IDLE' });
        if (onEnd) onEnd();
      }
    }
  }

  stopTTS(notifyIdle = true) {
    this.playbackToken++;
    if (this.currentAudioElement) {
      const el = this.currentAudioElement;
      this.currentAudioElement = null;
      try {
        el.onended = null;
        el.onerror = null;
        el.onplay = null;
        el.pause();
        el.currentTime = 0;
        el.src = '';
      } catch (e) {}
    }
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      try {
        window.speechSynthesis.cancel();
      } catch (e) {}
    }
    this.isSpeaking = false;
    this.currentUtterance = null;
    if (notifyIdle) {
      this.notify('stateChange', { state: 'IDLE' });
    }
  }

  stopConversation() {
    this.stopListening();
    this.stopTTS();
    this.notify('stateChange', { state: 'IDLE' });
  }
}

export const voiceAgent = new VoiceAgentAdapter();
