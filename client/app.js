/**
 * Telugu Voice Agent — client/app.js
 * Phases 1-4: health → mic (MediaRecorder) → STT → Brain → TTS → Playback + Custom Instructions
 * No secrets in client. All provider calls via server proxy.
 */
const $ = (id) => document.getElementById(id);

const healthDot = $("healthDot");
const healthText = $("healthText");
const healthError = $("healthError");
const sessionInfo = $("sessionInfo");
const micBtn = $("micBtn");
const stateLabel = $("stateLabel");
const transcriptEl = $("transcript");
const responseEl = $("response");
const usageEl = $("usage");
const metricsEl = $("metrics");
const conversationEl = $("conversation");
const clearBtn = $("clearBtn");
const testBtn = $("testBtn");
const stopAudioBtn = $("stopAudioBtn");
const voiceMode = $("voiceMode");
const realtimeMode = $("realtimeMode");
const liveBadge = $("liveBadge");
const partialsCard = $("partialsCard");
const partialsEl = $("partials");

// Playback
const audioPlayer = $("audioPlayer");
const noAudio = $("noAudio");
const ttsInfo = $("ttsInfo");
const replayBtn = $("replayBtn");
const ttsOnlyBtn = $("ttsOnlyBtn");
const ttsError = $("ttsError");

// Custom AI
const customInstructions = $("customInstructions");
const responseStyle = $("responseStyle");
const saveBtn = $("saveInstructions");
const resetBtn = $("resetInstructions");
const previewBtn = $("previewInstructions");
const viewPromptBtn = $("viewPromptBtn");
const previewOutput = $("previewOutput");
const effectivePrompt = $("effectivePrompt");
const saveStatus = $("saveStatus");
const activeBadge = $("activeBadge");
const historyCount = $("historyCount");
const metricsBtn = $("metricsBtn");
const metricsOut = $("metricsOut");
const interruptBtn = $("interruptBtn");

// Session
let sessionId = localStorage.getItem("telugu_session_id");
if (!sessionId) {
  sessionId = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());
  localStorage.setItem("telugu_session_id", sessionId);
}
sessionInfo.textContent = "session " + sessionId.slice(0, 8);

// Playback state
let lastAudioBase64 = null;
let lastAudioMime = "audio/wav";
let lastBrainText = "";
let currentObjectUrl = null;
let consecutiveEmpty = 0;

// ---- Hands-free AudioPlaybackManager (auto-play, queue, no overlap) ----
const playback = new AudioPlaybackManager(audioPlayer);

playback.onStarted = () => {
  setState("Speaking…");
  stopAudioBtn.style.display = "";
  ttsError.style.display = "none";
};

// Completion hook → conversation manager re-opens mic (hands-free loop)
playback.onFinished = (item) => {
  stopAudioBtn.style.display = "none";
  if (live.active) { backToListening(); return; }
  if (!voiceMode.checked) { setState("Ready — press mic to continue"); return; }
  if ($("handsFree") && $("handsFree").checked && !realtimeMode.checked) {
    if (consecutiveEmpty >= 3) {
      $("emptyGuardMsg").style.display = "block";
      setState("Paused — press mic to resume");
      return;
    }
    setState("Listening…");
    startRecording();
  } else {
    setState("Ready — press mic to continue");
  }
};

playback.onError = (err, item) => {
  ttsError.style.display = "block";
  ttsError.textContent = "Playback issue: " + String(err.message || err);
};
playback.onBlocked = () => {
  // Browser requires ONE gesture — show the single unlock card
  const u = $("unlockAudio");
  if (u) u.style.display = "block";
  ttsError.style.display = "none";
};

$("unlockAudio").addEventListener("click", () => {
  $("unlockAudio").style.display = "none";
  playback.userGesture();   // replays manager queue
  // Also retry live MSE playback if it was blocked
  if (live.mse) {
    live._playAttempted = false;
    if (live.sb && live.mseQueue.length > 0) {
      try { live.sb.appendBuffer(live.mseQueue.shift()); } catch {}
    }
    if (audioPlayer.paused && audioPlayer.src) {
      audioPlayer.play().catch(() => {});
    }
  }
});

// -- Helpers: audio play (auto via manager — no Play button anywhere) --
function playBase64(base64, mime = "audio/wav") {
  audioPlayer.style.display = "block";
  noAudio.style.display = "none";
  replayBtn.disabled = false;
  return playback.enqueueBase64(base64, mime);
}
function stopAudio() {
  playback.stopAll();
  audioPlayer.style.display = "none";
  if (voiceAbort) { try { voiceAbort.abort(); } catch {} voiceAbort = null; }
  // Fire interrupt to server (barge-in)
  try { fetch("/api/session/interrupt", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sessionId }) }); } catch {}
  setState(live.active ? "Interrupted — listening…" : "Stopped");
}
stopAudioBtn.addEventListener("click", stopAudio);
replayBtn.addEventListener("click", () => {
  if (lastAudioBase64) playBase64(lastAudioBase64, lastAudioMime);
});
ttsOnlyBtn.addEventListener("click", async () => {
  const text = (responseEl.textContent || "").trim();
  if (!text || text.startsWith("—")) { ttsError.style.display = "block"; ttsError.textContent = "No response text to synthesize yet — ask something first."; return; }
  ttsError.style.display = "none";
  setState("Speaking… (TTS only)");
  try {
    const r = await fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: text.slice(0, 2500), language_code: "te-IN" }) });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      throw new Error((j.detail && j.detail.error && j.detail.error.message) || r.statusText);
    }
    const buf = await r.arrayBuffer();
    const b64 = btoa(String.fromCharCode(...new Uint8Array(buf)));
    lastAudioBase64 = b64;
    lastAudioMime = r.headers.get("content-type") || "audio/wav";
    playBase64(b64, lastAudioMime);
    const speaker = r.headers.get("x-speaker") || "shubh";
    ttsInfo.textContent = `• ${speaker} • ${buf.byteLength} bytes`;
  } catch (e) {
    ttsError.style.display = "block";
    ttsError.textContent = "TTS error: " + String(e.message || e);
    setState("Ready");
  }
});

// -- Health --
async function checkHealth() {
  try {
    const r = await fetch("/api/health");
    const j = await r.json();
    const ok = j.ok;
    healthDot.className = "dot " + (ok ? "ok" : "bad");
    healthText.textContent = ok ? `Ready — ${j.version} • ${j.supportedLanguages.join(", ")}` : "Configuration invalid — check .env";
    if (j.error) { healthError.style.display = "block"; healthError.textContent = j.error; } else healthError.style.display = "none";
    if (!ok) {
      const p = j.presence || {};
      const missing = Object.entries(p).filter(([, v]) => !v).map(([k]) => k).join(", ");
      if (missing) { healthError.textContent += " Missing: " + missing; healthError.style.display = "block"; }
    }
    return ok;
  } catch (e) {
    healthDot.className = "dot bad";
    healthText.textContent = "Server not reachable";
    healthError.style.display = "block";
    healthError.textContent = String(e);
    return false;
  }
}
checkHealth();

// -- Instructions: dual-channel (behaviour + business), load/save with 10k caps --
const bizEl = $("businessInstructions");
const behavCount = $("behavCount");
const bizCount = $("bizCount");

async function loadInstructions() {
  const localB = localStorage.getItem("telugu_behaviour") || localStorage.getItem("telugu_custom_instructions") || "";
  const localZ = localStorage.getItem("telugu_business") || "";
  const localStyle = localStorage.getItem("telugu_response_style") || "concise, conversational";
  customInstructions.value = localB;
  bizEl.value = localZ;
  responseStyle.value = localStyle;
  try {
    const r = await fetch("/api/instructions?sessionId=" + encodeURIComponent(sessionId));
    if (r.ok) {
      const j = await r.json();
      if (j.behaviour) { customInstructions.value = j.behaviour; localStorage.setItem("telugu_behaviour", j.behaviour); }
      if (j.business) { bizEl.value = j.business; localStorage.setItem("telugu_business", j.business); }
      if (j.style) { responseStyle.value = j.style; localStorage.setItem("telugu_response_style", j.style); }
    }
  } catch {}
  updateActiveBadge();
}
function updateActiveBadge() {
  const has = (customInstructions.value || "").trim().length > 0 || (bizEl.value || "").trim().length > 0;
  activeBadge.style.display = has ? "" : "none";
}
function updateHistoryCount() {
  const n = conversationEl.children.length;
  historyCount.textContent = n ? `• ${n/2} turns` : "";
}
customInstructions.addEventListener("input", () => {
  localStorage.setItem("telugu_behaviour", customInstructions.value);
  behavCount.textContent = customInstructions.value.length;
  updateActiveBadge();
});
bizEl.addEventListener("input", () => {
  localStorage.setItem("telugu_business", bizEl.value);
  bizCount.textContent = bizEl.value.length;
  updateActiveBadge();
});
responseStyle.addEventListener("change", () => {
  localStorage.setItem("telugu_response_style", responseStyle.value);
});
loadInstructions();

saveBtn.addEventListener("click", async () => {
  saveStatus.style.display = "block";
  saveStatus.textContent = "Saving…";
  try {
    const r = await fetch("/api/instructions", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sessionId,
        behaviourInstructions: customInstructions.value,
        businessInstructions: bizEl.value,
        responseStyle: responseStyle.value,
      }),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail ? JSON.stringify(j.detail) : r.statusText);
    localStorage.setItem("telugu_behaviour", j.behaviour);
    localStorage.setItem("telugu_business", j.business);
    localStorage.setItem("telugu_response_style", j.responseStyle || responseStyle.value);
    saveStatus.textContent = `Saved ✓ behaviour ${j.behaviourLength}/10000 • business ${j.businessLength}/10000 • style: ${j.responseStyle}`;
    updateActiveBadge();
    setTimeout(() => saveStatus.style.display = "none", 3500);
  } catch (e) {
    saveStatus.textContent = "Save failed: " + String(e.message || e);
  }
});
resetBtn.addEventListener("click", async () => {
  customInstructions.value = "";
  bizEl.value = "";
  responseStyle.value = "concise, conversational";
  behavCount.textContent = "0"; bizCount.textContent = "0";
  ["telugu_behaviour", "telugu_custom_instructions", "telugu_business", "telugu_response_style"].forEach(k => localStorage.removeItem(k));
  updateActiveBadge();
  saveStatus.style.display = "block";
  saveStatus.textContent = "Clearing…";
  try {
    await fetch("/api/instructions?sessionId=" + encodeURIComponent(sessionId), { method: "DELETE" });
    saveStatus.textContent = "Cleared ✓ — back to default Telugu-first";
  } catch { saveStatus.textContent = "Cleared locally ✓"; }
  setTimeout(() => saveStatus.style.display = "none", 2000);
});
// View effective prompt (transparency)
if (viewPromptBtn) viewPromptBtn.addEventListener("click", async () => {
  effectivePrompt.style.display = "block";
  effectivePrompt.textContent = "Loading effective prompt…";
  try {
    const r = await fetch("/api/prompt/effective?sessionId=" + encodeURIComponent(sessionId) + "&transcript=" + encodeURIComponent("Python అంటే ఏమిటి?"));
    const j = await r.json();
    effectivePrompt.textContent = `Hierarchy:\n${JSON.stringify(j.hierarchy, null, 2)}\n\nDeveloper instructions preview (${j.full_developer_instructions_length} chars):\n${j.developer_instructions_preview}`;
  } catch (e) { effectivePrompt.textContent = "Error: " + String(e); }
});
// Metrics + interrupt
if (metricsBtn) metricsBtn.addEventListener("click", async () => {
  metricsOut.style.display = "block";
  metricsOut.textContent = "Loading /api/metrics…";
  try {
    const r = await fetch("/api/metrics"); const j = await r.json();
    metricsOut.textContent = JSON.stringify(j, null, 2);
  } catch (e) { metricsOut.textContent = "Error: " + String(e); }
});
if (interruptBtn) interruptBtn.addEventListener("click", async () => {
  try {
    const r = await fetch("/api/session/interrupt", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sessionId }) });
    const j = await r.json();
    metricsOut.style.display = "block";
    metricsOut.textContent = "Interrupt: " + JSON.stringify(j, null, 2);
    stopAudio();
  } catch (e) { metricsOut.textContent = "Interrupt error: " + String(e); }
});

// State
function setState(s) {
  stateLabel.textContent = s;
  const low = s.toLowerCase();
  let cls = "";
  if (low.includes("listen")) cls = "listening";
  else if (low.includes("understand") || low.includes("processing")) cls = "thinking";
  else if (low.includes("think")) cls = "thinking";
  else if (low.includes("speak") || low.includes("generating")) cls = "speaking";
  stateLabel.className = "state " + cls;
}

// Conversation
function addBubble(role, text) {
  const d = document.createElement("div");
  d.className = "bubble " + role;
  d.textContent = text;
  conversationEl.appendChild(d);
  conversationEl.scrollTop = conversationEl.scrollHeight;
  updateHistoryCount();
}
clearBtn.addEventListener("click", async () => {
  conversationEl.innerHTML = "";
  transcriptEl.textContent = "— no speech yet —"; transcriptEl.style.color = "var(--muted)";
  responseEl.textContent = "— waiting —"; responseEl.style.color = "var(--muted)";
  usageEl.textContent = ""; metricsEl.textContent = "";
  ttsInfo.textContent = ""; stopAudio();
  lastAudioBase64 = null; lastBrainText = "";
  replayBtn.disabled = true; audioPlayer.style.display = "none"; noAudio.style.display = "";
  setState("Ready — press mic and speak Telugu");
  try { await fetch("/api/session/clear", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sessionId }) }); } catch {}
});

// Mic logic — push-to-talk (REST) + CONTINUOUS FULL-DUPLEX LIVE SESSION (realtime WS)
// Industry patterns applied (Deepgram/AssemblyAI/GoNoGo/Stream guides, 2026):
//   • Persistent STT socket across turns; agent stays LISTENING until user stops it
//   • Browser AEC via getUserMedia({echoCancellation}) — cancels our own <audio> MSE playback
//   • Two-tier RMS echo gate: hard-suppress frames while agent speaks + cooldown window
//   • Barge-in on MODEL-level speech (≥2-word partial while speaking) → fewer false triggers
//   • Cancellation = stop generation + stop playback + keep heard-so-far context
let mediaRecorder = null;
let chunks = [];
let isRecording = false;
let streamRef = null;
let voiceAbort = null;

const live = {
  active: false,
  socket: null,
  ctx: null,
  worklet: null,
  stream: null,
  busy: false,
  pendingFinal: null,
  agentSpeaking: false,
  ttsSock: null,
  mse: null,
  sb: null,
  mseQueue: [],
  bargeCooldownUntil: 0,
  turnN: 0,
  sawVadStart: false,
  // Echo-gate tuning (RMS of Int16 ≈ amplitude/32768)
  rmsGate: true,
  RMS_SPEAKING: 0.012,
  RMS_COOLDOWN: 0.03,
  COOLDOWN_MS: 1200,
};

function wsUrl(path) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return proto + "//" + location.host + path;
}

function rms16(int16arr) {
  let sum = 0;
  for (let i = 0; i < int16arr.length; i += 4) { // sample every 2nd for speed
    const v = int16arr[i] / 32768;
    sum += v * v;
  }
  return Math.sqrt(sum / Math.ceil(int16arr.length / 4));
}

function wordCount(t) { return (t.trim().match(/\S+/g) || []).length; }

// Friendly error extraction — handles AppError shape AND FastAPI 422 validation arrays
function extractErr(body, status) {
  const d = body && body.detail;
  if (d && d.error && d.error.message) return d.error.message;
  if (Array.isArray(d) && d.length) {
    const f = d[0];
    const loc = (f.loc || []).filter(x => x !== "body").join(".");
    return `${loc || "input"}: ${f.msg || "invalid value"}`;
  }
  if (d && typeof d === "string") return d;
  if (body && body.error && body.error.message) return body.error.message;
  return "request failed (HTTP " + status + ")";
}

async function startLiveSession() {
  partialsCard.style.display = "";
  partialsEl.textContent = "…connecting live session…";

  // Pull Fine-tune console settings into connection params
  const q = new URLSearchParams({ language_code: "te-IN", stream_type: "fast", mode: "transcribe" });
  try {
    const rt = await (await fetch("/api/settings/runtime?sessionId=" + encodeURIComponent(sessionId))).json();
    if (rt.values.sttLanguage) q.set("language_code", rt.values.sttLanguage);
    if (rt.values.sttStreamType) q.set("stream_type", rt.values.sttStreamType);
    if (rt.values.sttMode) q.set("mode", rt.values.sttMode);
    if (rt.values.sttSilenceMs) q.set("silence_duration_ms", String(rt.values.sttSilenceMs));
    if (rt.values.sttThreshold != null) q.set("threshold", String(rt.values.sttThreshold));
  } catch {}

  // Mic with platform-native AEC (cancels our own MSE <audio> playback), NS + AGC
  try {
    live.stream = await navigator.mediaDevices.getUserMedia({
      audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (e) {
    setState(e.name === "NotAllowedError" ? "Microphone permission denied" : e.name === "NotFoundError" ? "No microphone found" : "Mic error: " + e.message);
    return;
  }
  try {
    live.ctx = new AudioContext({ sampleRate: 16000 });
    await live.ctx.audioWorklet.addModule("/pcm-worklet.js");
    const src = live.ctx.createMediaStreamSource(live.stream);
    await live.ctx.resume();
    live.worklet = new AudioWorkletNode(live.ctx, "pcm-processor");
    live.worklet.port.onmessage = onPcmChunk;
    src.connect(live.worklet); // NOT to destination — avoids feedback loop
  } catch (e) {
    setState("Audio init failed: " + e.message);
    stopLiveSession();
    return;
  }

  // Persistent socket — stays open across turns
  live.socket = new WebSocket(wsUrl("/ws/stt-realtime") + "?" + q.toString());
  live.socket.binaryType = "arraybuffer";
  live.socket.onopen = () => {
    live.active = true;
    isRecording = true;
    micBtn.classList.add("recording");
    micBtn.textContent = "⏹️";
    micBtn.title = "Stop live session";
    setState("Listening… (live — just speak)");
    partialsEl.textContent = "…ready — speak Telugu…";
    liveBadge.style.display = "";
  };
  live.socket.onmessage = (ev) => {
    let m; try { m = JSON.parse(ev.data); } catch { return; }
    routeLiveEvent(m);
  };
  live.socket.onerror = () => { if (live.active) partialsEl.textContent = "WS error"; };
  live.socket.onclose = () => {
    if (!live.active) return;      // we closed it ourselves
    // Unexpected drop → auto-stop with clear message (reconnect UX later)
    cleanupLiveMedia();
    finishLiveUi("Live session dropped — press mic to restart");
  };
}

function onPcmChunk(e) {
  if (!live.active || !live.socket || live.socket.readyState !== WebSocket.OPEN) return;
  if (!(e.data instanceof ArrayBuffer)) return;
  const now = performance.now();
  // Two-tier RMS gate (only gates ECHO; real user voice passes both tiers)
  if (live.agentSpeaking || now < live.bargeCooldownUntil) {
    const thr = now < live.bargeCooldownUntil ? live.RMS_COOLDOWN : live.RMS_SPEAKING;
    if (live.rmsGate && rms16(new Int16Array(e.data)) < thr) return;
  }
  live.socket.send(e.data);
}

function routeLiveEvent(m) {
  switch (m.event) {
    case "session.begin":
      partialsEl.textContent = "…live — speak anytime…";
      break;
    case "vad.speech_start":
      live.sawVadStart = true;
      break;
    case "transcript.partial": {
      const t = m.text || "";
      partialsEl.textContent = t || partialsEl.textContent;
      if (live.agentSpeaking) {
        // Model-level barge-in guard: ≥2 words beats echo/noise artifacts
        if (wordCount(t) >= 2) doBargeIn("partial≥2w");
        else if (live.sawVadStart && wordCount(t) >= 1 && performance.now() > live.bargeCooldownUntil) doBargeIn("vad+partial");
      } else if (live.busy && performance.now() - (live.thinkingSince || 0) > 350) {
        // User changed their mind while the brain is still thinking → cancel generation
        if (wordCount(t) >= 2) {
          if (voiceAbort) { try { voiceAbort.abort(); } catch {} }
          setState("Interrupted — listening…");
          partialsEl.textContent = "⚡ cancelled — keep talking…";
        }
      }
      break;
    }
    case "transcript.final": {
      live.sawVadStart = false;
      console.log("[VOICE][STT] FINAL");
      const text = (m.text || "").trim();
      if (!text || wordCount(text) < 1) { partialsEl.textContent = "(empty)…listening…"; break; }
      transcriptEl.textContent = text; transcriptEl.style.color = "var(--text)";
      if (live.busy) { live.pendingFinal = text; partialsEl.textContent = "✓ queued: " + text.slice(0, 60); }
      else runTurn(text, m.sttFinalMs);
      break;
    }
    case "error":
      partialsEl.textContent = "STT error: " + (m.message || m.code);
      if (m.is_fatal) { stopLiveSession(); setState("Fatal STT error — restart live"); }
      break;
  }
}

// Guards: hard caps (server rejects >10000 per channel) — trim + warn instead of silent 422
const INSTR_MAX = 10000;

function getInstructionsSafe() {   // BEHAVIOUR channel
  const raw = customInstructions.value.trim();
  if (raw.length > INSTR_MAX) {
    saveStatus.style.display = "block";
    saveStatus.textContent = `⚠️ Behavioural prompt too long (${raw.length}/${INSTR_MAX}) — using first ${INSTR_MAX}.`;
    setTimeout(() => saveStatus.style.display = "none", 4000);
    return raw.slice(0, INSTR_MAX);
  }
  return raw;
}

function getBusinessSafe() {       // BUSINESS channel
  const raw = bizEl.value.trim();
  if (raw.length > INSTR_MAX) {
    saveStatus.style.display = "block";
    saveStatus.textContent = `⚠️ Business prompt too long (${raw.length}/${INSTR_MAX}) — using first ${INSTR_MAX}.`;
    setTimeout(() => saveStatus.style.display = "none", 4000);
    return raw.slice(0, INSTR_MAX);
  }
  return raw;
}

function getBizSafeRaw() { return bizEl.value.trim(); }

// ---------- STREAMING TURN (industry cascaded pipeline) ----------
// Brain SSE deltas → forwarded into Sarvam TTS WS as they arrive (Sarvam buffers
// and sentence-splits server-side via min_buffer_size/max_chunk_length) → audio
// chunks stream back → MediaSource plays from the FIRST sentence. No waiting for
// the full brain response. Barge-in aborts SSE + closes TTS + kills audio.

function ttsConfigFromConsole() {
  const speakerSel = document.getElementById("ttsSpeaker");
  const paceInp = document.getElementById("ttsPace");
  const tempInp = document.getElementById("ttsTemperature");
  const codecSel = document.getElementById("ttsCodec");
  const minBuf = document.getElementById("ttsMinBuffer") || null;
  const maxChunk = document.getElementById("ttsMaxChunk") || null;
  const cfg = {
    speaker: (speakerSel && speakerSel.value) || "shubh",
    language_code: "te-IN",
    pace: paceInp ? Number(paceInp.value) : 1.0,
    min_buffer_size: minBuf ? Number(minBuf.value) : 50,   // lower = faster first audio
    max_chunk_length: maxChunk ? Number(maxChunk.value) : 200,
    output_audio_codec: "mp3",
    output_audio_bitrate: "128k",
  };
  if (tempInp && cfg.temp !== false) {
    const tv = Number(tempInp.value);
    if (!Number.isNaN(tv)) cfg.temperature = tv;           // bulbul:v3 only (server enforces)
  }
  return cfg;
}

async function runTurn(text, sttFinalMs) {
  live.busy = true;
  live.turnN++;
  addBubble("user", text);
  setState("Thinking…");
  const userInstructions = getInstructionsSafe();
  const style = responseStyle.value;
  voiceAbort = new AbortController();
  live.thinkingSince = performance.now();
  live.agentSpeaking = false;
  live.mseDone = false;
  live._playAttempted = false;
  live._playLoggedPlaying = false;
  resetTtsAcc();

  // STEP 12: latency instrumentation t0..t9
  _perf = { turn: live.turnN, t0: performance.now(), sttFinalMs: sttFinalMs ?? null,
            brainFirstDelta: null, firstSentence: null,
            t5_ttsStart: null, t6_firstAudio: null, t7_firstAppend: null,
            t8_playReq: null, t9_audioStarted: null };
  console.log("[VOICE][TURN] START turn_id=turn_" + String(live.turnN).padStart(3, "0"));

  let full = "";
  let sawAudio = false;
  let sseFailed = null;

  // 1) Open TTS socket ONCE — stays warm across the whole answer
  hooks_onAudioFirst = () => { sawAudio = true; setState("Speaking…"); };
  try {
    await openTtsStream();
  } catch (e) {
    ttsError.style.display = "block";
    ttsError.textContent = "TTS WS unavailable (" + e.message + ") — will use REST fallback";
  }

  // 2) Stream brain deltas → pipe each into TTS immediately
  const pipeline = readBrainSSE(text, userInstructions, style, {
    onDelta(delta, fullSoFar) {
      if (_perf && !_perf.brainFirstDelta) { _perf.brainFirstDelta = performance.now() - _perf.t0; console.log("[VOICE][BRAIN] FIRST_DELTA"); }
      full = fullSoFar;
      responseEl.textContent = full;                       // live text on screen
      responseEl.style.color = "var(--text)";
      pushTtsText(delta);                                  // Sarvam buffers + sentence-splits
    },
    onAudioFirst() {
      sawAudio = true;
      setState("Speaking…");
    },
  })
    .then((finalText) => { full = finalText || full; })
    .catch((e) => { sseFailed = e; });

  await pipeline;

  // Interrupted mid-think/mid-speech by user speech? Yield without fallback spam.
  if (voiceAbort.signal.aborted) {
    live.busy = false;
    backToListening();
    return;
  }

  // 3) Flush any buffered tail so nothing is cut
  closeTtsStream();

  if (sseFailed) {
    // Fallback: one-shot JSON brain + single TTS (still keeps session live)
    live.busy = false;
    try {
      const br = await fetch("/api/brain", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript: text, language_code: "te-IN", sessionId, userInstructions: userInstructions || undefined, businessInstructions: getBizSafeRaw() || undefined, responseStyle: style }),
      });
      const bj = await br.json().catch(() => ({}));
      if (!br.ok) throw new Error(extractErr(bj, br.status));
      full = (bj.text || "").trim();
      responseEl.textContent = full; responseEl.style.color = "var(--text)";
      addBubble("assistant", full);
      setState("Speaking…");
      await playTtsOverWs(full);
    } catch (e2) {
      responseEl.textContent = "Brain error: " + (e2.message || e2); responseEl.style.color = "#ff8a80";
      backToListening(); return;
    }
  } else {
    if (!full.trim()) { full = "క్షమించండి, నాకు అర్థం కాలేదు."; responseEl.textContent = full; }
    addBubble("assistant", full);
    // 4) Wait until playback of streamed audio finishes (or user interrupts)
    await waitPlaybackDone();
  }

  usageEl.textContent = `→ te-IN${/[A-Za-z]/.test(full) && /[\u0C00-\u0C7F]/.test(full) ? " • code-mixed" : ""} • ${full.length} chars${sawAudio ? " • ⚡streamed" : ""}`;
  live.busy = false;
  if (live.pendingFinal) { const t = live.pendingFinal; live.pendingFinal = null; runTurn(t); return; }
  backToListening();
}

// SSE reader for POST /api/brain/stream — resolves with final text
async function readBrainSSE(transcript, userInstructions, style, hooks) {
  const resp = await fetch("/api/brain/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript, language_code: "te-IN", sessionId, userInstructions: userInstructions || undefined, businessInstructions: getBizSafeRaw() || undefined, responseStyle: style }),
    signal: voiceAbort.signal,
  });
  if (!resp.ok || !resp.body) {
    let msg = "HTTP " + resp.status;
    try { msg = extractErr(await resp.json(), resp.status); } catch {}
    throw new Error(msg);
  }
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "", finalText = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, idx); buf = buf.slice(idx + 2);
      if (!frame.startsWith("data:")) continue;
      const payload = frame.slice(5).trim();
      if (payload === "[DONE]") continue;
      let obj; try { obj = JSON.parse(payload); } catch { continue; }
      if (obj.error) throw new Error(obj.error.message || "brain stream error");
      if (obj.delta) { hooks.onDelta(obj.delta, (hooks._acc = (hooks._acc || "") + obj.delta)); }
      if (obj.done) { finalText = obj.text || ""; }
    }
  }
  return finalText;
}

// Resolves when current streamed playback finishes; also used post-REST-fallback
function waitPlaybackDone(timeoutMs = 60000) {
  return new Promise((resolve) => {
    const t0 = performance.now();
    const iv = setInterval(() => {
      const ended = audioPlayer.ended || (audioPlayer.paused && audioPlayer.currentTime > 0);
      if (ended || voiceAbort.signal.aborted || performance.now() - t0 > timeoutMs) {
        clearInterval(iv);
        live.agentSpeaking = false;
        resolve();
      }
    }, 120);
  });
}

// hook used by openTtsStream on first audio chunk
let hooks_onAudioFirst = null;

function backToListening() {
  if (!live.active) return;
  // Detach finished MSE so the next turn builds a fresh stream
  if (!live.agentSpeaking) {
    live.mseQueue.length = 0; live.sb = null; live.mse = null; live.mseDone = false;
  }
  setState("Listening… (live — just speak)");
  partialsEl.textContent = "…listening…";
}

function doBargeIn(reason) {
  if (!live.agentSpeaking && !live.busy) return;
  const now = performance.now();
  console.log("[VOICE][AUDIO] PLAY_INTERRUPTED", reason, "turn_" + live.turnN);
  // 1) STOP PLAYBACK instantly (<150ms target)
  audioPlayer.pause();
  audioPlayer.removeAttribute("src");
  try { audioPlayer.load(); } catch {}
  if (outUrlRef()) { try { URL.revokeObjectURL(outUrlRef()); } catch {} setOutUrl(null); }
  // STEP 18: clear EVERYTHING stale so no old audio leaks into next turn
  live.mseQueue.length = 0; live.sb = null; live.mse = null; live.mseDone = false;
  live._ttsAllB64 = []; lastAudioBase64 = null;
  resetTtsAcc();
  hooks_onAudioFirst = null;
  stopAudioBtn.style.display = "none";
  // 2) STOP GENERATION
  if (voiceAbort) { try { voiceAbort.abort(); } catch {} }
  if (live.ttsSock && live.ttsSock.readyState === WebSocket.OPEN) { try { live.ttsSock.close(1000); } catch {} }
  live.ttsSock = null;
  // 3) STATE: keep heard-so-far; cooldown so residual echo doesn't re-trigger
  live.agentSpeaking = false;
  live.bargeCooldownUntil = now + live.COOLDOWN_MS;
  fetch("/api/session/interrupt", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sessionId }) }).catch(() => {});
  metricsEl.textContent += ` • ⚡barge-in#${live.turnN}(${reason})`;
  setState("Interrupted — listening…");
  partialsEl.textContent = "⚡ interrupted — keep talking…";
}

// TTS over /ws/tts — STREAMING mode for the live pipeline.
// Forensic fix notes (see audit):
//  BUG1: play() was fired on chunk arrival BEFORE SourceBuffer had any data
//        (readyState=HAVE_NOTHING) and its rejection was swallowed.
//  BUG2: sourceopen created the SourceBuffer but never pumped the queued first
//        chunk — single-sentence replies appended nothing → silence.
//  BUG3: no play() retry after data landed; no MSE-less fallback.
// New orchestration: append first → then start playback with explicit,
// logged, retried play(); diagnostics on every state change.
let ttsModelCache = "bulbul:v3";
let _perf = null;

function alog(tag, extra) {
  // [VOICE][AUDIO] diagnostic channel — safe fields only
  const d = audioPlayer ? {
    paused: audioPlayer.paused,
    readyState: audioPlayer.readyState,
    networkState: audioPlayer.networkState,
    muted: audioPlayer.muted,
    volume: audioPlayer.volume,
    msReady: live.mse ? live.mse.readyState : "-",
    sbUpdating: live.sb ? live.sb.updating : "-",
    queued: live.mseQueue.length,
    turn: live.turnN,
  } : {};
  console.log(`[VOICE][AUDIO] ${tag}`, d, extra || "");
}

function openTtsStream() {
  return new Promise((resolve, reject) => {
    const sel = document.getElementById("ttsModel");
    ttsModelCache = (sel && sel.value) || "bulbul:v3";
    const outCodec = "mp3"; // MSE-friendly
    const myTurn = live.turnN;                       // STEP 19: turn-id race guard
    const sock = new WebSocket(wsUrl("/ws/tts?model=" + encodeURIComponent(ttsModelCache)));
    live.ttsSock = sock;
    live._ttsAllB64 = [];
    live.mseDone = false;
    live._playAttempted = false;
    live._fallbackBytes = [];
    let settled = false;

    if (_perf) { _perf.t5_ttsStart = performance.now(); alog("TTS_START"); }

    const ok = () => { if (!settled) { settled = true; resolve(sock); } };
    const fail = (e) => {
      console.log("[VOICE][TTS] ERROR", String(e && e.message || e));
      if (!settled) { settled = true; try { sock.close(); } catch {} if (live.ttsSock === sock) live.ttsSock = null; reject(e); }
    };

    function ensureMSE() {
      if (live.mse) return true;
      if (!("MediaSource" in window)) return false;
      live.mse = new MediaSource();
      if (currentObjectUrl) { try { URL.revokeObjectURL(currentObjectUrl); } catch {} currentObjectUrl = null; }
      currentObjectUrl = URL.createObjectURL(live.mse);
      audioPlayer.src = currentObjectUrl;
      audioPlayer.style.display = "block"; noAudio.style.display = "none";
      stopAudioBtn.style.display = ""; ttsError.style.display = "none";
      live.mse.addEventListener("sourceopen", () => {
        try {
          live.sb = live.mse.addSourceBuffer("audio/mpeg");
          live.sb.mode = "sequence";
          // FIX(BUG2): pump the already-queued first chunk the moment the buffer exists
          live.sb.addEventListener("updateend", () => { pumpTts(); maybeStartPlayback(); });
          alog("SOURCEBUFFER_READY");
          pumpTts();               // ← was missing (BUG2)
        } catch (err) { fail(err); }
      }, { once: true });
      return true;
    }

    function pumpTts() {
      if (!live.sb || live.sb.updating) return;   // STEP 11 backpressure: queue, never drop
      if (live.mseQueue.length > 0) {
        const b = live.mseQueue.shift();
        try {
          live.sb.appendBuffer(b);
          if (_perf && !_perf.t7_firstAppend) _perf.t7_firstAppend = performance.now();
          console.log("[VOICE][AUDIO] CHUNK_APPENDED", b.byteLength);
        } catch (err) { fail(err); }
      } else if (live.mseDone) {
        try { live.mse.endOfStream(); } catch {}   // only after stream truly completed
      }
    }

    // FIX(BUG1+3): call play() AFTER data is in the buffer, await it, log it, retry
    async function maybeStartPlayback() {
      if (!live.sb) return;
      if (audioPlayer.paused && !live._playAttempted) {
        live._playAttempted = true;
        if (_perf && !_perf.t8_playReq) _perf.t8_playReq = performance.now();
        alog("PLAY_REQUEST");
        try {
          await audioPlayer.play();
          if (_perf && !_perf.t9_audioStarted) _perf.t9_audioStarted = performance.now();
          alog("PLAY_STARTED");
          logPerfSummary();
        } catch (err) {
          const name = err && err.name;
          alog(name === "NotAllowedError" ? "PLAY_BLOCKED" : "PLAY_ERROR", String(err.message || err));
          if (name === "NotAllowedError") {
            // Browser policy despite gesture — surface ONE unlock card (STEP 16)
            const u = document.getElementById("unlockAudio");
            if (u) u.style.display = "block";
            live._playAttempted = false;   // allow retry after unlock tap
          } else {
            // AbortError/NotSupportedError etc: reset so next chunk retries
            setTimeout(() => { live._playAttempted = false; pumpTts(); }, 120);
          }
        }
      } else if (!audioPlayer.paused && !live._playLoggedPlaying) {
        live._playLoggedPlaying = true;
      }
    }

    function logPerfSummary() {
      if (!_perf) return;
      const p = _perf;
      const rel = (t) => t == null ? null : Math.round(t - p.t0);
      console.log("[PERF]", JSON.stringify({
        turn: p.turn,
        STT_FINAL_MS: p.sttFinalMs,
        BRAIN_FIRST_DELTA_MS: p.brainFirstDelta != null ? Math.round(p.brainFirstDelta) : null,
        FIRST_SENTENCE_MS: p.firstSentence != null ? Math.round(p.firstSentence) : null,
        TTS_START_MS: rel(p.t5_ttsStart),
        TTS_FIRST_AUDIO_MS: p.t6_firstAudio != null ? Math.round(p.t6_firstAudio - p.t0) : null,
        AUDIO_PLAY_REQUEST_MS: rel(p.t8_playReq),
        AUDIO_STARTED_MS: rel(p.t9_audioStarted),
        TOTAL_TIME_TO_FIRST_AUDIO_MS: p.t9_audioStarted != null ? Math.round(p.t9_audioStarted - p.t0) : null,
      }));
    }

    sock.onopen = () => {
      const cfgData = ttsConfigFromConsole();
      cfgData.output_audio_codec = outCodec;
      if (ttsModelCache !== "bulbul:v3") delete cfgData.temperature; // v2: no temperature
      sock.send(JSON.stringify({ type: "config", data: cfgData }));
      ok(); // warm socket — brain deltas get pushed as they arrive
    };
    sock.onerror = () => fail(new Error("connection failed"));
    sock.onclose = () => { if (live.ttsSock === sock) live.ttsSock = null; };

    sock.onmessage = (ev) => {
      // STEP 19 race guard: ignore anything from a superseded socket/turn
      if (live.ttsSock !== sock || myTurn !== live.turnN) return;
      let m; try { m = JSON.parse(ev.data); } catch { return; }
      const type = m.type || m.event;
      const b64 = m.data && (m.data.audio || (typeof m.data === "string" ? m.data : null));

      if (b64) {
        if (_perf && !_perf.t6_firstAudio) { _perf.t6_firstAudio = performance.now(); console.log("[VOICE][TTS] FIRST_AUDIO"); }
        live._ttsAllB64.push(b64);
        lastAudioBase64 = live._ttsAllB64.join("");
        lastAudioMime = "audio/mpeg";
        replayBtn.disabled = false;
        const bin = atob(b64);
        const buf = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);

        const mseOk = ensureMSE();
        if (mseOk) {
          live.mseQueue.push(buf.buffer);
          pumpTts();                    // appends now if sb ready, else waits sourceopen/updateend
          maybeStartPlayback();
        } else {
          // No MSE support (rare): accumulate → single blob at end via shared engine
          live._fallbackBytes.push(buf.buffer);
        }
        if (!live.agentSpeaking) {
          live.agentSpeaking = true;
        }
        if (typeof hooks_onAudioFirst === "function") { const h = hooks_onAudioFirst; hooks_onAudioFirst = null; h(); }
      } else if ((m.data && m.data.event_type === "final") || type === "end_of_stream") {
        live.mseDone = true;
        live.agentSpeaking = false;
        ttsInfo.textContent = `• WS ${ttsModelCache} • ${live._ttsAllB64.length} chunks • streamed`;
        if (live._fallbackBytes.length) {
          const total = live._fallbackBytes.reduce((n, b) => n + b.byteLength, 0);
          const all = new Uint8Array(total);
          let o = 0; for (const b of live._fallbackBytes) { all.set(new Uint8Array(b), o); o += b.byteLength; }
          playBase64(all.buffer, "audio/mpeg").catch(() => {});
          live._fallbackBytes = [];
        } else {
          pumpTts();                    // drains queue then endOfStream
        }
        try { sock.close(1000); } catch {}
      } else if (type === "error") {
        live.agentSpeaking = false;
        fail(new Error(m.message || "tts ws error"));
      }
    };
  });
}

// ---- Sentence aggregator + send paths ----
// STEP 8: sentence boundaries are the trigger (not a char count).
// Telugu/English boundaries: . ! ? । … ; : newline. Hard cap 70 chars only as
// safety for punctuation-less streams, so first speech never waits unnecessarily.
let _ttsAcc = "";
const _SENT_END = /[.!?…।;:\n]\s*$|[…]\s*/u;
const TTS_CHUNK_MAX = 70;

function resetTtsAcc() { _ttsAcc = ""; }

function pushTtsText(delta) {
  if (!delta) return;
  _ttsAcc += delta;
  let piece = null;
  const boundary = _SENT_END.test(_ttsAcc);
  if (boundary) {
    // Emit everything up to & including the boundary; keep remainder buffering
    const m = _ttsAcc.match(/^[\s\S]*?[.!?…।;:\n](\s+|$)/u);
    if (m) { piece = m[0]; _ttsAcc = _ttsAcc.slice(m[0].length); }
    else { piece = _ttsAcc; _ttsAcc = ""; }
  } else if (_ttsAcc.length >= TTS_CHUNK_MAX) {
    piece = _ttsAcc; _ttsAcc = "";
  }
  if (!piece || !piece.trim()) return;
  if (_perf && !_perf.firstSentence) _perf.firstSentence = performance.now();
  console.log("[VOICE][BRAIN] SENTENCE_READY", JSON.stringify(piece.slice(0, 60)));
  if (live.ttsSock && live.ttsSock.readyState === WebSocket.OPEN) {
    try { live.ttsSock.send(JSON.stringify({ type: "text", data: { text: piece } })); } catch {}
  } else {
    speakViaHttpStream(piece); // WS died mid-turn → per-sentence HTTP stream
  }
}

async function speakViaHttpStream(text) {
  // Fallback when TTS WS died mid-turn: synthesize this sentence via HTTP stream.
  // If MSE session is active, append progressively; else accumulate then play blob.
  const parts = [];
  let appended = false;
  try {
    const r = await fetch("/api/tts/stream", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text.slice(0, 3500), language_code: "te-IN" }),
      signal: voiceAbort ? voiceAbort.signal : undefined,
    });
    if (!r.ok || !r.body) return;
    const reader = r.body.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (live.sb && !live.sb.updating && live.mse && !live.mseDone) {
        try { live.sb.appendBuffer(value.slice(0)); appended = true; } catch {}
      } else {
        parts.push(value);
      }
    }
    if (!appended && parts.length) {
      const total = parts.reduce((n, p) => n + p.length, 0);
      const all = new Uint8Array(total);
      let o = 0; for (const p of parts) { all.set(p, o); o += p.length; }
      const b64 = btoa(String.fromCharCode(...all));
      lastAudioBase64 = (lastAudioBase64 || "") + b64;
      lastAudioMime = "audio/mpeg";
      playBase64(lastAudioBase64, "audio/mpeg");
      await new Promise(res => { audioPlayer.onended = res; setTimeout(res, 30000); });
    }
  } catch {}
}

function closeTtsStream() {
  // Send any remaining buffered text, then flush the TTS socket
  const tail = _ttsAcc.trim(); _ttsAcc = "";
  if (tail && live.ttsSock && live.ttsSock.readyState === WebSocket.OPEN) {
    try { live.ttsSock.send(JSON.stringify({ type: "text", data: { text: tail } })); } catch {}
  }
  if (live.ttsSock && live.ttsSock.readyState === WebSocket.OPEN) {
    try { live.ttsSock.send(JSON.stringify({ type: "flush" })); } catch {}
  }
}

// Legacy one-shot helper kept for REST-fallback path
function playTtsOverWs(text) {
  return new Promise((resolve, reject) => {
    openTtsStream().then((sock) => {
      hooks_onAudioFirst = null;
      sock.addEventListener("message", function onceFinal(ev) {
        let m; try { m = JSON.parse(ev.data); } catch { return; }
        const t = m.type || m.event;
        if ((m.data && m.data.event_type === "final") || t === "end_of_stream" || t === "error") {
          sock.removeEventListener("message", onceFinal);
          resolve();
        }
      });
      sock.send(JSON.stringify({ type: "text", data: { text: text.slice(0, 2500) } }));
      sock.send(JSON.stringify({ type: "flush" }));
    }).catch(reject);
  });
}

function outUrlRef() { return currentObjectUrl; }
function setOutUrl(v) { currentObjectUrl = v; }

function cleanupLiveMedia() {
  try { live.stream && live.stream.getTracks().forEach(t => t.stop()); } catch {}
  try { live.worklet && live.worklet.disconnect(); } catch {}
  try { live.ctx && live.ctx.close(); } catch {}
  live.worklet = null; live.ctx = null; live.stream = null;
  live.mseQueue.length = 0; live.sb = null; live.mse = null; live.mseDone = false;
}

async function stopLiveSession() {
  live.active = false;
  live.busy = false;
  live.pendingFinal = null;
  live.agentSpeaking = false;
  if (voiceAbort) { try { voiceAbort.abort(); } catch {} voiceAbort = null; }
  if (live.ttsSock && live.ttsSock.readyState === WebSocket.OPEN) { try { live.ttsSock.close(1000); } catch {} }
  live.ttsSock = null;
  if (live.socket && live.socket.readyState === WebSocket.OPEN) {
    try { live.socket.send(JSON.stringify({ event: "end" })); } catch {}
    try { live.socket.close(1000); } catch {}
  }
  live.socket = null;
  cleanupLiveMedia();
  audioPlayer.pause();
  finishLiveUi("Ready — press mic to start a new session");
}

function finishLiveUi(msg) {
  isRecording = false;
  micBtn.classList.remove("recording");
  micBtn.textContent = "🎙️";
  micBtn.title = "Click to start/stop recording";
  liveBadge.style.display = "none";
  setState(msg);
}

async function startRecording() {
  // Barge-in / restart semantics
  if (!audioPlayer.paused) { stopAudio(); }
  if (voiceAbort) { try { voiceAbort.abort(); } catch {} voiceAbort = null; }
  if (realtimeMode.checked) {
    if (live.active) { await stopLiveSession(); return; }   // toggle OFF ends session
    await startLiveSession();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    streamRef = stream;
    chunks = [];
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
    mediaRecorder = new MediaRecorder(stream, { mimeType: mime });
    mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
    mediaRecorder.onstop = onRecordingStop;
    mediaRecorder.start(100);
    isRecording = true;
    micBtn.classList.add("recording");
    micBtn.textContent = "⏹️";
    setState("Listening…");
  } catch (e) {
    const name = e && e.name;
    if (name === "NotAllowedError") setState("Microphone permission denied — allow mic and reload");
    else if (name === "NotFoundError") setState("No microphone found");
    else setState("Mic error: " + (e.message || String(e)));
  }
}
function stopRecording() {
  if (realtimeMode.checked) {
    // Live session semantics:
    //  • While agent is SPEAKING → first click = barge-in (stops speech, keeps listening)
    //  • Otherwise → second click ends the whole live session
    if (live.agentSpeaking) { doBargeIn("manual-mic"); return; }
    if (live.active) { stopLiveSession(); }
    return;
  }
  if (mediaRecorder && isRecording) {
    mediaRecorder.stop();
    isRecording = false;
    micBtn.classList.remove("recording");
    micBtn.textContent = "🎙️";
    setState("Understanding…");
    if (streamRef) streamRef.getTracks().forEach((t) => t.stop());
  }
}
async function onRecordingStop() {
  if (chunks.length === 0) { setState("No audio — try again"); return; }
  const blob = new Blob(chunks, { type: chunks[0].type || "audio/webm" });
  if (blob.size < 800) { setState("Too short — speak a bit longer"); return; }
  if (voiceMode.checked) {
    await sendVoiceTurn(blob);
  } else {
    await sendSTT(blob);
  }
}

// Text-only path (Phase 2): STT then Brain
async function sendSTT(blob) {
  const fd = new FormData();
  const ext = blob.type.includes("webm") ? "webm" : "wav";
  fd.append("file", blob, `audio.${ext}`);
  fd.append("language_code", "te-IN");
  fd.append("mode", "transcribe");
  try {
    const r = await fetch("/api/stt", { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok) {
      const msg = (j.detail && j.detail.error && j.detail.error.message) || j.error || "STT failed";
      transcriptEl.textContent = "STT error: " + msg; transcriptEl.style.color = "#ff8a80";
      setState("Error — try again"); return;
    }
    const transcript = (j.transcript || "").trim();
    if (!transcript) {
      transcriptEl.textContent = "Didn't catch that. Please try again. (empty transcript)";
      transcriptEl.style.color = "#ff8a80"; setState("Ready — press mic again"); return;
    }
    transcriptEl.textContent = transcript; transcriptEl.style.color = "var(--text)";
    setState("Thinking…");
    await sendBrain(transcript, j.language_code || "te-IN");
  } catch (e) {
    transcriptEl.textContent = "Network error during STT: " + String(e);
    setState("Error — retry");
  }
}
async function sendBrain(transcript, language_code) {
  const userInstructions = getInstructionsSafe();
  const style = responseStyle.value;
  // Abort any prior
  if (voiceAbort) try { voiceAbort.abort(); } catch {}
  voiceAbort = new AbortController();
  try {
    const r = await fetch("/api/brain", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transcript, language_code, sessionId, userInstructions: userInstructions || undefined, responseStyle: style }),
      signal: voiceAbort.signal,
    });
    const j = await r.json();
    if (!r.ok) {
      const msg = (j.detail && j.detail.error && j.detail.error.message) || j.error || "Brain failed";
      responseEl.textContent = "Brain error: " + msg; responseEl.style.color = "#ff8a80";
      setState("Error — try again"); return;
    }
    const text = (j.text || "").trim();
    responseEl.textContent = text; responseEl.style.color = "var(--text)";
    lastBrainText = text;
    const lc = j.language_context || {};
    usageEl.textContent = `→ ${lc.responseLanguage || "te-IN"}${lc.isCodeMixed ? " • code-mixed" : ""} • ${j.usage ? JSON.stringify(j.usage) : ""}`;
    metricsEl.textContent = j.metrics ? `PERF text-only` : "";
    addBubble("user", transcript); addBubble("assistant", text);
    setState("Ready — press mic to continue");
  } catch (e) {
    if (e.name === "AbortError") { setState("Interrupted — press mic again"); return; }
    responseEl.textContent = "Network error during Brain: " + String(e);
    setState("Error — retry");
  } finally { voiceAbort = null; }
}

// Full voice loop: POST /api/voice/turn → transcript + brain_text + audio_base64 + metrics
async function sendVoiceTurn(blob) {
  const fd = new FormData();
  const ext = blob.type.includes("webm") ? "webm" : "wav";
  fd.append("file", blob, `audio.${ext}`);
  fd.append("language_code", "te-IN");
  fd.append("mode", "transcribe");
  fd.append("sessionId", sessionId);
  fd.append("userInstructions", getInstructionsSafe());
  fd.append("businessInstructions", getBizSafeRaw());
  // ttsSpeaker left empty → server picks via language resolver
  setState("Understanding… → Thinking…");
  const t0 = performance.now();
  if (voiceAbort) try { voiceAbort.abort(); } catch {}
  voiceAbort = new AbortController();
  try {
    const r = await fetch("/api/voice/turn", { method: "POST", body: fd, signal: voiceAbort.signal });
    const j = await r.json();
    if (!r.ok) {
      // 429 handling with Retry-After
      if (r.status === 429) {
        const retryAfter = r.headers.get("Retry-After") || "?";
        transcriptEl.textContent = `Rate limited — retry after ${retryAfter}s`; transcriptEl.style.color = "#ff8a80";
        setState(`Busy — retry in ${retryAfter}s`);
        return;
      }
      const msg = (j.detail && j.detail.error && j.detail.error.message) || j.error || "Voice turn failed";
      transcriptEl.textContent = "Voice error: " + msg; transcriptEl.style.color = "#ff8a80";
      setState("Error — try again");
      if (j.transcript) { transcriptEl.textContent = j.transcript; transcriptEl.style.color = "var(--text)"; }
      return;
    }
    const transcript = (j.transcript || "").trim();
    const brainText = (j.brain_text || "").trim();
    if (!transcript) {
      consecutiveEmpty++;
      transcriptEl.textContent = "Didn't catch that. Please try again."; transcriptEl.style.color = "#ff8a80";
      setState("Ready — press mic again");
      if ($("handsFree") && $("handsFree").checked && !realtimeMode.checked && consecutiveEmpty < 3) {
        setTimeout(() => { if (voiceMode.checked && !isRecording && !live.active) startRecording(); }, 600);
      }
      return;
    }
    consecutiveEmpty = 0;
    transcriptEl.textContent = transcript; transcriptEl.style.color = "var(--text)";
    responseEl.textContent = brainText || "— no response —"; responseEl.style.color = brainText ? "var(--text)" : "var(--muted)";
    lastBrainText = brainText;
    const lc = j.language_context || {};
    usageEl.textContent = `→ ${lc.responseLanguage || "te-IN"}${lc.isCodeMixed ? " • code-mixed" : ""} ${j.usage ? "• " + JSON.stringify(j.usage) : ""}`;
    const m = j.metrics || {};
    metricsEl.textContent = `PERF stt ${m.sttMs ?? "?"}ms • brain ${m.brainMs ?? "?"}ms • tts ${m.ttsMs ?? "?"}ms • e2e ${m.e2eMs ?? Math.round(performance.now()-t0)}ms • ${brainText.length} chars • ${j.audio_base64 ? Math.round(j.audio_base64.length*0.75) + "B audio" : "no audio"}`;
    addBubble("user", transcript);
    if (brainText) addBubble("assistant", brainText);
    if (j.audio_base64) {
      lastAudioBase64 = j.audio_base64;
      lastAudioMime = j.content_type || "audio/wav";
      ttsInfo.textContent = `• ${lastAudioMime} • ${Math.round(j.audio_base64.length*0.75)} bytes • AUTO`;
      await playBase64(j.audio_base64, lastAudioMime);   // auto-plays; onFinished reopens mic
    } else {
      setState("Ready — no audio returned (check TTS config)");
    }
  } catch (e) {
    if (e.name === "AbortError") { setState("Interrupted — press mic again"); return; }
    transcriptEl.textContent = "Network error during voice turn: " + String(e);
    setState("Error — retry");
  } finally { voiceAbort = null; }
}

micBtn.addEventListener("click", () => {
  playback.userGesture();   // any mic click doubles as autoplay unlock gesture
  if (isRecording) stopRecording(); else startRecording();
});
document.addEventListener("keydown", (e) => {
  if (e.code === "Space" && document.activeElement !== customInstructions) { e.preventDefault(); micBtn.click(); }
  if (e.code === "Escape" && !audioPlayer.paused) stopAudio();
});

// Test memory
testBtn.addEventListener("click", async () => {
  if (voiceMode.checked) {
    // Use text path for deterministic test without mic
    setState("Thinking… test 1/2");
    await sendBrainViaText("నా పేరు Sai.", "te-IN");
    setTimeout(async () => { setState("Thinking… test 2/2"); await sendBrainViaText("నా పేరు ఏమిటి?", "te-IN"); }, 900);
  } else {
    setState("Thinking… test 1/2");
    await sendBrainViaText("నా పేరు Sai.", "te-IN");
    setTimeout(async () => { setState("Thinking… test 2/2"); await sendBrainViaText("నా పేరు ఏమిటి?", "te-IN"); }, 900);
  }
});
async function sendBrainViaText(text, lang) {
  const userInstructions = getInstructionsSafe();
  const style = responseStyle.value;
  try {
    const r = await fetch("/api/brain", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ transcript: text, language_code: lang, sessionId, userInstructions: userInstructions || undefined, businessInstructions: getBizSafeRaw() || undefined, responseStyle: style }) });
    const j = await r.json();
    if (!r.ok) throw new Error(JSON.stringify(j));
    transcriptEl.textContent = text; transcriptEl.style.color = "var(--text)";
    responseEl.textContent = j.text; responseEl.style.color = "var(--text)";
    lastBrainText = j.text;
    addBubble("user", text); addBubble("assistant", j.text);
    usageEl.textContent = `→ ${j.language_context?.responseLanguage || "te-IN"}`;
    if (voiceMode.checked && j.text) {
      // Also get TTS for this test
      try {
        const tr = await fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: j.text.slice(0, 2500), language_code: "te-IN" }) });
        if (tr.ok) {
          const buf = await tr.arrayBuffer();
          const b64 = btoa(String.fromCharCode(...new Uint8Array(buf)));
          lastAudioBase64 = b64; lastAudioMime = tr.headers.get("content-type") || "audio/wav";
          playBase64(b64, lastAudioMime);
        } else setState("Ready — test done (TTS skipped)");
      } catch {}
    } else setState("Ready — test done");
  } catch (e) { responseEl.textContent = "Test error: " + String(e); }
}

// Preview custom instructions (ephemeral) — uses /api/brain/test (style included)
previewBtn.addEventListener("click", async () => {
  const instr = getInstructionsSafe();
  const style = responseStyle.value;
  if (!instr && style === "concise, conversational") { previewOutput.style.display = "block"; previewOutput.textContent = "Enter instructions or pick a non-default style, then Test."; return; }
  previewOutput.style.display = "block"; previewOutput.textContent = "Testing…";
  try {
    const r = await fetch("/api/brain/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ userInstructions: instr, businessInstructions: getBizSafeRaw(), testInput: "Python అంటే ఏమిటి?", responseStyle: style }) });
    const j = await r.json();
    if (!r.ok) previewOutput.textContent = "Error: " + JSON.stringify(j);
    else previewOutput.textContent = "→ " + j.text;
  } catch (e) { previewOutput.textContent = "Network error: " + String(e); }
});
