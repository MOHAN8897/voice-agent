/** Live web-agent session — PCM16 16 kHz over /ws/web-agent (same loop as PSTN). */

import { api } from './api';
import { showToast } from '../console/ui/ToastHost';
import { voiceAgent } from './voiceAgent';

const SAMPLE_RATE = 16000;

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

  const emit = (event, data) => {
    listeners.forEach((fn) => {
      try {
        fn(event, data);
      } catch {
        /* ignore listener errors */
      }
    });
  };

  const teardownAudio = () => {
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
    if (audioContext) {
      audioContext.close().catch(() => {});
      audioContext = null;
    }
    playTime = 0;
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

  return {
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    async start({ agentId, language } = {}) {
      if (!agentId) throw new Error('Select an agent to test.');
      const token = api.getToken();
      if (!token) throw new Error('Sign in to test live voice.');
      const qs = new URLSearchParams({
        token,
        agentId,
        language: language || 'en-IN',
      });
      const url = `${api.getWsOrigin()}/ws/web-agent?${qs.toString()}`;
      socket = new WebSocket(url);
      socket.binaryType = 'arraybuffer';

      await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error('Voice server did not become ready.')), 45000);
        socket.onerror = () => {
          clearTimeout(timeout);
          reject(new Error('Could not connect to the voice server.'));
        };
        socket.onclose = () => {
          clearTimeout(timeout);
          reject(new Error('Voice connection closed before ready.'));
        };
        socket.onmessage = (event) => {
          if (event.data instanceof ArrayBuffer) return;
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

      audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });
      if (audioContext.state === 'suspended') await audioContext.resume();

      // Mic only when the user starts a web-agent session — never on page load.
      // If already granted, getUserMedia is silent (no second OS prompt).
      const micState = await voiceAgent.getMicrophonePermissionState();
      if (micState === 'denied') {
        throw new Error(
          'Microphone is blocked for this site. Allow the mic in browser settings, then start again.'
        );
      }
      if (micState === 'prompt' || micState === 'unknown') {
        showToast('Allow the microphone for this call (audio only — no camera).', 'info', 5000);
      }
      mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: false,
      });
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

      socket.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          playPcm16(new Uint8Array(event.data));
          emit('audio');
          return;
        }
        handleMessage(event.data);
      };
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
      teardownAudio();
    },
  };
}
