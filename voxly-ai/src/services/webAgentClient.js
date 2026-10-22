/** Live web-agent session — PCM16 16 kHz over /ws/web-agent (same loop as PSTN). */

import { api } from './api';
import { showToast } from '../console/ui/ToastHost';

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
  let silentGain = null;
  let playTime = 0;
  const listeners = new Set();
  let muted = false;
  let audioUnlock = Promise.resolve();
  let generation = 0;
  let cancelStartup = null;
  const queuedAudio = [];
  let queuedBytes = 0;
  const playingNodes = new Set();

  const clearPlayback = () => {
    for (const node of playingNodes) {
      try { node.stop(); node.disconnect(); } catch { /* already ended */ }
    }
    playingNodes.clear();
    playTime = 0;
    queuedAudio.length = 0;
    queuedBytes = 0;
  };

  const emit = (event, data) => {
    listeners.forEach((fn) => {
      try { fn(event, data); } catch { /* subscriber failure must not stop media */ }
    });
  };
  const teardownAudio = ({ keepContext = false } = {}) => {
    clearPlayback();
    for (const node of [processor, source, silentGain]) {
      try { node?.disconnect(); } catch { /* already disconnected */ }
    }
    processor = source = silentGain = null;
    mediaStream?.getTracks().forEach((track) => track.stop());
    mediaStream = null;
    if (audioContext && !keepContext) {
      audioContext.close().catch(() => {});
      audioContext = null;
    }
    playTime = 0;
    queuedAudio.length = 0;
    queuedBytes = 0;
  };
  const prepareAudio = () => {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) throw new Error('Audio playback is unavailable in this browser.');
    if (!audioContext || audioContext.state === 'closed') {
      try { audioContext = new AudioCtx({ sampleRate: SAMPLE_RATE }); }
      catch { audioContext = new AudioCtx(); }
    }
    audioUnlock = audioContext.state === 'suspended' ? audioContext.resume() : Promise.resolve();
    // The state check in start reports a failed unlock without an unhandled rejection.
    audioUnlock.catch(() => {});
    return audioUnlock;
  };
  const playPcm16 = (bytes) => {
    if (!audioContext || !bytes?.byteLength) return;
    const aligned = bytes.byteOffset % 2 === 0 ? bytes : bytes.slice();
    const pcm = new Int16Array(aligned.buffer, aligned.byteOffset, Math.floor(aligned.byteLength / 2));
    const buffer = audioContext.createBuffer(1, pcm.length, SAMPLE_RATE);
    buffer.getChannelData(0).set(int16ToFloat32(pcm));
    const node = audioContext.createBufferSource();
    node.buffer = buffer;
    node.connect(audioContext.destination);
    playingNodes.add(node);
    node.onended = () => { playingNodes.delete(node); node.disconnect(); };
    playTime = Math.max(playTime, audioContext.currentTime);
    node.start(playTime);
    playTime += buffer.duration;
    emit('audio');
  };
  const flushAudio = () => {
    if (audioContext?.state !== 'running') return;
    while (queuedAudio.length) playPcm16(new Uint8Array(queuedAudio.shift()));
    queuedBytes = 0;
  };
  const stop = () => {
    generation += 1;
    cancelStartup?.(new Error('Voice session was stopped.'));
    cancelStartup = null;
    const previous = socket;
    socket = null;
    try {
      if (previous?.readyState === WebSocket.OPEN) previous.send(JSON.stringify({ type: 'end' }));
      previous?.close(); // CONNECTING sockets also need to be cancelled.
    } catch { /* transport may have already closed */ }
    teardownAudio();
  };

  return {
    prepareAudio,
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    async start({ agentId, language } = {}) {
      if (!agentId) throw new Error('Select an agent to test.');
      const token = api.getToken();
      if (!token) throw new Error('Sign in to test live voice.');
      if (socket) stop();
      const attempt = ++generation;
      teardownAudio({ keepContext: Boolean(audioContext && audioContext.state !== 'closed') });
      // Unlock within the click, before microphone permission or any network await.
      prepareAudio();
      let connected = false;
      let failed = false;
      let timeout;
      const cancelled = new Promise((_, reject) => { cancelStartup = reject; });
      const url = `${api.getWsOrigin()}/ws/web-agent?${new URLSearchParams({ agentId, language: language || 'en-IN' })}`;
      const ws = new WebSocket(url, [WEB_AGENT_SUBPROTOCOL, `${WEB_AGENT_AUTH_PREFIX}${token}`]);
      socket = ws;
      ws.binaryType = 'arraybuffer';
      const serverReady = new Promise((resolve, reject) => {
        ws.onmessage = (event) => {
          if (attempt !== generation) return;
          if (event.data instanceof ArrayBuffer) {
            // Speaker playback is independent of a slow microphone permission prompt.
            if (audioContext?.state === 'running') playPcm16(new Uint8Array(event.data));
            else {
              queuedBytes += event.data.byteLength;
              if (queuedBytes > SAMPLE_RATE * 2 * 30) {
                failed = true;
                reject(new Error('Browser audio remained blocked. Allow playback and retry.'));
                ws.close();
              } else queuedAudio.push(event.data);
            }
            return;
          }
          let payload;
          try { payload = JSON.parse(event.data); } catch { return; }
          if (payload.type === 'ready') resolve(payload);
          else if (payload.type === 'error') {
            failed = true;
            if (connected) emit('error', payload);
            reject(new Error(payload.message || 'Voice session failed.'));
            ws.close();
          } else if (payload.type === 'clear_audio') {
            clearPlayback();
            emit('interrupted');
          } else if (payload.type === 'hangup_initiated' || payload.type === 'hangup_complete') {
            emit(payload.type, payload);
          }
        };
        ws.onerror = () => {
          if (attempt !== generation) return;
          failed = true;
          const error = new Error('Could not connect to the voice server. Please check backend status.');
          if (connected) emit('error', { message: error.message });
          reject(error);
          ws.close();
        };
        ws.onclose = () => {
          if (attempt !== generation) return;
          reject(new Error('Voice connection closed before ready.'));
          socket = null;
          teardownAudio();
          if (connected && !failed) emit('closed');
        };
      });
      serverReady.catch(() => {});
      const audioReady = (async () => {
        let stream = null;
        if (navigator.mediaDevices?.getUserMedia) {
          try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: {
              echoCancellation: true, noiseSuppression: true, autoGainControl: true,
            }, video: false });
          } catch {
            showToast('Microphone unavailable. Connected in listen-only mode.', 'info', 5000);
          }
        }
        if (attempt !== generation || socket !== ws) {
          stream?.getTracks().forEach((track) => track.stop());
          throw new Error('Voice session was stopped.');
        }
        mediaStream = stream;
        await audioUnlock;
        if (audioContext?.state === 'suspended') await audioContext.resume();
        if (!audioContext || audioContext.state !== 'running') {
          throw new Error('Browser audio is blocked. Allow audio playback and retry.');
        }
        if (stream) {
          source = audioContext.createMediaStreamSource(stream);
          processor = audioContext.createScriptProcessor(2048, 1, 1);
          processor.onaudioprocess = (event) => {
            if (attempt !== generation || ws.readyState !== WebSocket.OPEN || ws.bufferedAmount > 256000) return;
            const input = event.inputBuffer.getChannelData(0);
            const pcm = muted
              ? new Int16Array(Math.max(1, Math.floor(input.length * SAMPLE_RATE / audioContext.sampleRate)))
              : downsampleToInt16(input, audioContext.sampleRate);
            ws.send(pcm.buffer);
          };
          source.connect(processor);
          silentGain = audioContext.createGain();
          silentGain.gain.value = 0;
          processor.connect(silentGain);
          silentGain.connect(audioContext.destination);
        }
        flushAudio();
        emit('microphone', { mode: stream ? 'capturing' : 'listen-only' });
        return Boolean(stream);
      })();
      try {
        const deadline = new Promise((_, reject) => {
          timeout = setTimeout(() => reject(new Error('Voice startup timed out. Check microphone permission and try again.')), 45000);
        });
        const [ready, capturing] = await Promise.race([Promise.all([serverReady, audioReady]), cancelled, deadline]);
        if (attempt !== generation || socket !== ws) throw new Error('Voice session was stopped.');
        connected = true;
        cancelStartup = null;
        emit('ready', { ...ready, microphoneMode: capturing ? 'capturing' : 'listen-only' });
        return ready;
      } catch (error) {
        if (attempt === generation) stop();
        throw error;
      } finally {
        clearTimeout(timeout);
      }
    },
    setMuted(nextMuted) { muted = Boolean(nextMuted); },
    stop,
  };
}
