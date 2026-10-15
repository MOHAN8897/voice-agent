/** Live web-agent session — PCM16 16 kHz over /ws/web-agent (same loop as PSTN). */

import { api } from './api';
import { showToast } from '../console/ui/ToastHost';
import { voiceAgent } from './voiceAgent';

const SAMPLE_RATE = 16000;
const WEB_AGENT_SUBPROTOCOL = 'voxly-web-agent';
const WEB_AGENT_AUTH_PREFIX = 'voxly-auth.';

function downsampleToInt16(float32, fromRate) {
  const ratio = fromRate / SAMPLE_RATE;
  const length = Math.max(1, Math.floor(float32.length / ratio));
  const out = new Int16Array(length);
  for (let i = 0; i < length; i += 1) {
    const sample = float32[Math.floor(i * ratio)] || 0;
    const clipped = Math.max(-1, Math.min(1, sample));
    out[i] = clipped < 0 ? clipped * 0x8000 : clipped * 0x7fff;
  }
  return out;
}

function int16ToFloat32(int16) {
  const out = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i += 1) {
    out[i] = int16[i] / (int16[i] < 0 ? 0x8000 : 0x7fff);
  }
  return out;
}

export function createWebAgentSession() {
  let socket = null;
  let mediaStream = null;
  let audioContext = null;
  let processor = null;
  let source = null;
  let playTime = 0;
  let listeners = new Set();
  let muted = false;
  let audioUnlock = Promise.resolve();

  const emit = (event, data) => {
    listeners.forEach((fn) => {
      try {
        fn(event, data);
      } catch {
        /* ignore listener errors */
      }
    });
  };

  const teardownAudio = ({ keepContext = false } = {}) => {
    try {
      processor?.disconnect();
    } catch {
      /* ignore */
    }
    try {
      source?.disconnect();
    } catch {
      /* ignore */
    }
    processor = null;
    source = null;
    mediaStream?.getTracks().forEach((t) => t.stop());
    mediaStream = null;
    if (audioContext && !keepContext) {
      audioContext.close().catch(() => {});
      audioContext = null;
    }
    playTime = 0;
  };

  const prepareAudio = () => {
    // Invoke from the Start click before permission or activation requests await.
    const AudioCtx = typeof window !== 'undefined' ? (window.AudioContext || window.webkitAudioContext) : null;
    if (!AudioCtx) throw new Error('Audio playback is unavailable in this browser.');
    try {
      if (!audioContext || audioContext.state === 'closed') {
        try {
          audioContext = new AudioCtx({ sampleRate: SAMPLE_RATE });
        } catch {
          audioContext = new AudioCtx();
        }
      }
      if (audioContext.state === 'suspended') {
        audioUnlock = audioContext.resume().catch(() => {});
      } else {
        audioUnlock = Promise.resolve();
      }
      return audioUnlock;
    } catch {
      throw new Error('Could not initialize browser audio playback.');
    }
  };

  const playPcm16 = (bytes) => {
    if (!audioContext || !bytes?.byteLength) return;
    const int16 = new Int16Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 2));
    const float32 = int16ToFloat32(int16);
    const buffer = audioContext.createBuffer(1, float32.length, SAMPLE_RATE);
    buffer.getChannelData(0).set(float32);
    const node = audioContext.createBufferSource();
    node.buffer = buffer;
    node.connect(audioContext.destination);
    const now = audioContext.currentTime;
    if (playTime < now) playTime = now;
    node.start(playTime);
    playTime += buffer.duration;
  };

  const handleMessage = (raw) => {
    let payload = raw;
    if (typeof raw === 'string') {
      try {
        payload = JSON.parse(raw);
      } catch {
        return;
      }
    }
    const type = payload?.type;
    if (type === 'ready') {
      emit('ready', payload);
      return;
    }
    if (type === 'hangup_initiated' || (type === 'hangup' && payload.stage === 'initiated')) {
      showToast(payload.message || 'Hangup initiated — the agent is ending the call.', 'info');
      emit('hangup_initiated', payload);
      return;
    }
    if (type === 'hangup_complete') {
      showToast(payload.message || 'The agent hung up. Session closed.', 'success');
      emit('hangup_complete', payload);
      return;
    }
    if (type === 'error') {
      showToast(payload.message || 'Voice session error', 'error');
      emit('error', payload);
    }
  };

  const earlyAudioQueue = [];

  return {
    prepareAudio,
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    async start({ agentId, language } = {}) {
      if (!agentId) throw new Error('Select an agent to test.');
      const token = api.getToken();
      if (!token) throw new Error('Sign in to test live voice.');

      // Clean up any lingering previous session
      if (socket) {
        try {
          socket.close();
        } catch {
          /* ignore */
        }
        socket = null;
      }
      teardownAudio({ keepContext: Boolean(audioContext && audioContext.state !== 'closed') });
      earlyAudioQueue.length = 0;

      // Unlock speaker playback synchronously from the user's Start click. If we
      // wait for the asynchronous microphone permission query first, browsers can
      // discard transient activation and leave the incoming voice context suspended.
      prepareAudio();

      // Check mic permission early
      let isListenOnly = false;
      let micState = 'unknown';
      try {
        micState = await voiceAgent.getMicrophonePermissionState();
      } catch {
        // Mic status must not block listen-only playback.
      }
      if (micState === 'denied') {
        isListenOnly = true;
        showToast('Microphone access is blocked. Starting in listen-only mode so you can hear the agent.', 'info', 6000);
      } else if (micState === 'prompt' || micState === 'unknown') {
        showToast('Allow microphone access when prompted to speak with the agent.', 'info', 4000);
      }

      // Initialize audio stream and AudioContext in parallel with WebSocket connection
      const audioInitPromise = (async () => {
        let stream = null;
        if (!isListenOnly && typeof navigator !== 'undefined' && navigator.mediaDevices?.getUserMedia) {
          try {
            stream = await navigator.mediaDevices.getUserMedia({
              audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
              },
              video: false,
            });
          } catch (mediaErr) {
            console.warn('Microphone capture not available, falling back to listen-only:', mediaErr);
            if (mediaErr.name === 'NotAllowedError' || mediaErr.name === 'PermissionDeniedError') {
              showToast('Microphone access denied. Connected in listen-only mode.', 'info', 5000);
            } else if (mediaErr.name === 'NotFoundError' || mediaErr.name === 'DevicesNotFoundError') {
              showToast('No microphone detected. Connected in listen-only mode so you can hear the agent.', 'info', 5000);
            }
            stream = null;
          }
        }

        return { stream, ctx: audioContext };
      })();

      const qs = new URLSearchParams({
        agentId,
        language: language || 'en-IN',
      });
      const url = `${api.getWsOrigin()}/ws/web-agent?${qs.toString()}`;
      // Browsers cannot attach Authorization headers to WebSocket upgrades. Send
      // the bearer token as a private subprotocol instead of a URL query value,
      // which would be copied into proxy and access logs.
      socket = new WebSocket(url, [WEB_AGENT_SUBPROTOCOL, `${WEB_AGENT_AUTH_PREFIX}${token}`]);
      socket.binaryType = 'arraybuffer';

      const readyPromise = new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error('Voice server did not become ready in time.')), 45000);
        socket.onerror = () => {
          clearTimeout(timeout);
          reject(new Error('Could not connect to the voice server. Please check backend status.'));
        };
        socket.onclose = () => {
          clearTimeout(timeout);
          reject(new Error('Voice connection closed before ready.'));
        };
        socket.onmessage = (event) => {
          if (event.data instanceof ArrayBuffer) {
            earlyAudioQueue.push(event.data);
            return;
          }
          try {
            const payload = JSON.parse(event.data);
            if (payload?.type === 'ready') {
              clearTimeout(timeout);
              handleMessage(payload);
              resolve(payload);
            } else if (payload?.type === 'error') {
              clearTimeout(timeout);
              handleMessage(payload);
              reject(new Error(payload.message || 'Voice session error'));
            }
          } catch {
            /* ignore non-json until ready */
          }
        };
      });

      // Await both server ready and audio setup concurrently
      let audioSetup;
      try {
        const results = await Promise.all([readyPromise, audioInitPromise]);
        audioSetup = results[1];
        await audioUnlock;
        if (audioContext?.state === 'suspended') {
          try {
            await audioContext.resume();
          } catch {
            /* The following state check reports a useful startup error. */
          }
        }
        if (!audioContext || audioContext.state !== 'running') {
          throw new Error('Browser audio is blocked. Allow audio playback and start the session again.');
        }
      } catch (err) {
        if (socket) {
          try {
            socket.close();
          } catch {
            /* ignore */
          }
          socket = null;
        }
        teardownAudio();
        throw err;
      }

      mediaStream = audioSetup.stream;
      audioContext = audioSetup.ctx;

      if (mediaStream && audioContext) {
        source = audioContext.createMediaStreamSource(mediaStream);
        processor = audioContext.createScriptProcessor(2048, 1, 1);
        processor.onaudioprocess = (event) => {
          if (!socket || socket.readyState !== WebSocket.OPEN) return;
          const input = event.inputBuffer.getChannelData(0);
          const pcm = muted
            ? new Int16Array(Math.max(1, Math.floor(input.length * (SAMPLE_RATE / (audioContext.sampleRate || SAMPLE_RATE)))))
            : downsampleToInt16(input, audioContext.sampleRate || SAMPLE_RATE);
          socket.send(pcm.buffer);
        };
        source.connect(processor);
        const mute = audioContext.createGain();
        mute.gain.value = 0;
        processor.connect(mute);
        mute.connect(audioContext.destination);
      }

      socket.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          playPcm16(new Uint8Array(event.data));
          emit('audio');
          return;
        }
        handleMessage(event.data);
      };

      // Immediately play any early buffered audio frames
      while (earlyAudioQueue.length > 0) {
        const chunk = earlyAudioQueue.shift();
        playPcm16(new Uint8Array(chunk));
        emit('audio');
      }

      socket.onclose = () => {
        teardownAudio();
        emit('closed');
      };
    },
    setMuted(nextMuted) {
      muted = Boolean(nextMuted);
    },
    stop() {
      try {
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: 'end' }));
          socket.close();
        }
      } catch {
        /* ignore */
      }
      socket = null;
      earlyAudioQueue.length = 0;
      teardownAudio();
    },
  };
}
