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

// Brain prompt editor (single document)
const brainPromptEl = $("brainPrompt");
const brainCharCount = $("brainCharCount");
const brainTokenEst = $("brainTokenEst");
const brainTokenBudget = $("brainTokenBudget");
const brainTokenFill = $("brainTokenFill");
const brainCacheStatus = $("brainCacheStatus");
const loadDefaultPromptBtn = $("loadDefaultPrompt");
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

// Runtime settings cache (Fine-tune Console → backend → all TTS paths)
let runtimeSettings = { values: {}, defaults: {} };
let voiceConfig = { httpTtsFallback: false, persistentTtsWs: true };
let clientLogging = { enabled: true, client: true, perf: true };

async function refreshVoiceConfig() {
  try {
    const c = await (await fetch("/api/settings/catalog")).json();
    if (c.voice) voiceConfig = { ...voiceConfig, ...c.voice };
    if (c.logging) clientLogging = { ...clientLogging, ...c.logging };
  } catch {}
}

function clientLog(kind, ...args) {
  if (!clientLogging.enabled) return;
  if (kind === "perf" && !clientLogging.perf) return;
  if (kind !== "perf" && !clientLogging.client) return;
  console.log(...args);
}

async function refreshRuntimeSettings() {
  try {
    const r = await fetch("/api/settings/runtime?sessionId=" + encodeURIComponent(sessionId));
    if (r.ok) runtimeSettings = await r.json();
    _cachedTtsConfig = null;
  } catch {}
  return runtimeSettings;
}

/** Canonical TTS config — same resolver as REST / WS / voice turn on the server. */
let _cachedTtsConfig = null;
let _cachedTtsConfigTs = 0;

async function getResolvedTtsConfig(lang = "te-IN", force = false) {
  const now = Date.now();
  if (!force && _cachedTtsConfig && now - _cachedTtsConfigTs < 120000) {
    return _cachedTtsConfig;
  }
  try {
    const r = await fetch(
      "/api/settings/tts-config?sessionId=" + encodeURIComponent(sessionId) + "&language_code=" + encodeURIComponent(lang)
    );
    if (r.ok) {
      const j = await r.json();
      _cachedTtsConfig = j.ttsConfig;
      _cachedTtsConfigTs = now;
      console.log("[VOICE][CONFIG]", j.ttsConfig);
      clientLog("voice", "[VOICE][CONFIG]", j.ttsConfig);
      return j.ttsConfig;
    }
  } catch (e) {
    console.warn("[VOICE][CONFIG] fetch failed", e);
  }
  const v = runtimeSettings.values || {};
  const d = runtimeSettings.defaults || {};
  return {
    model: v.ttsModel || d.ttsModel || "bulbul:v3",
    speaker: v.ttsSpeaker || d.ttsSpeaker || "shubh",
    pace: v.ttsPace ?? d.ttsPace ?? 1.08,
    language_code: lang,
    min_buffer_size: v.ttsMinBuffer ?? 30,
    max_chunk_length: v.ttsMaxChunk ?? 80,
    output_audio_codec: v.ttsCodec || "mp3",
    output_audio_bitrate: v.ttsBitrate || "128k",
    temperature: v.ttsTemperature ?? d.ttsTemperature ?? 0.4,
  };
}

/** On-screen TTS/playback debug log (last 30 lines). */
const audioDebugLog = $("audioDebugLog");
function logPlayback(tag, detail) {
  if (!clientLogging.enabled || !clientLogging.client) return;
  const ts = new Date().toLocaleTimeString();
  const line = `[${ts}] ${tag}` + (detail ? " " + (typeof detail === "string" ? detail : JSON.stringify(detail)) : "");
  console.log("[VOICE][PLAYBACK]", tag, detail || "");
  for (const id of ["audioDebugLog", "audioDebugLogVisible"]) {
    const el = $(id);
    if (el) {
      el.textContent = (el.textContent + line + "\n").split("\n").slice(-30).join("\n");
      el.scrollTop = el.scrollHeight;
    }
  }
}

function saveConversationTurn(userText, assistantText) {
  if (!window.ConversationStore) return;
  window.ConversationStore.appendTurn({
    user: userText || "",
    assistant: assistantText || "",
    audioBase64: lastAudioBase64,
    mime: lastAudioMime,
    speaker: ttsInfo?.textContent || null,
  });
  updateHistoryCount();
}

/** Tear down MSE streaming so AudioPlaybackManager can use the same element. */
function teardownMse() {
  live.mseQueue.length = 0;
  live.sb = null;
  live.mseDone = false;
  if (live.mse) {
    try {
      if (live.mse.readyState === "open") live.mse.endOfStream();
    } catch {}
    live.mse = null;
  }
  if (currentObjectUrl) {
    try { URL.revokeObjectURL(currentObjectUrl); } catch {}
    currentObjectUrl = null;
  }
  try { audioPlayer.pause(); audioPlayer.removeAttribute("src"); audioPlayer.load(); } catch {}
  logPlayback("MSE_TEARDOWN", {});
}

/** Low-latency PCM stream player — schedules linear16 chunks via Web Audio (no MSE buffer wait). */
function createPcmStreamPlayer(ctx, sampleRate = 24000) {
  let nextTime = 0;
  const sources = new Set();
  let hadAudio = false;
  return {
    sampleRate,
    hadAudio() { return hadAudio; },
    idle() { return sources.size === 0; },
    reset() {
      nextTime = 0;
      for (const s of sources) { try { s.stop(); } catch {} }
      sources.clear();
      hadAudio = false;
    },
    appendPcm16(arrayBuffer) {
      if (!arrayBuffer || !arrayBuffer.byteLength) return;
      hadAudio = true;
      const int16 = new Int16Array(arrayBuffer);
      const floats = new Float32Array(int16.length);
      for (let i = 0; i < int16.length; i++) floats[i] = int16[i] / 32768;
      const buf = ctx.createBuffer(1, floats.length, sampleRate);
      buf.getChannelData(0).set(floats);
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(ctx.destination);
      const now = ctx.currentTime;
      if (nextTime < now + 0.02) nextTime = now + 0.02;
      src.start(nextTime);
      nextTime += buf.duration;
      sources.add(src);
      src.onended = () => sources.delete(src);
    },
  };
}

function stopPcmPlayback() {
  if (live.pcmPlayer) live.pcmPlayer.reset();
  live.pcmPlayer = null;
}

/** Unlock speaker output on first user gesture (mic click). */
async function unlockAudioPlayback() {
  playback.userGesture();
  try {
    audioPlayer.muted = true;
    audioPlayer.src = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";
    await audioPlayer.play();
    audioPlayer.pause();
    audioPlayer.muted = false;
    audioPlayer.removeAttribute("src");
    logPlayback("UNLOCK_SUCCESS", {});
  } catch (e) {
    logPlayback("UNLOCK_BLOCKED", { name: e && e.name });
  }
}

/** Play raw audio buffer — Web Audio first (auto-speak), HTML audio fallback (manual). */
async function playArrayBuffer(buffer, mime = "audio/wav") {
  if (!buffer || !buffer.byteLength) {
    logPlayback("EMPTY_BUFFER", {});
    return false;
  }
  teardownMse();
  audioPlayer.style.display = "block";
  noAudio.style.display = "none";
  replayBtn.disabled = false;
  if (window.AudioUtils) {
    lastAudioBase64 = window.AudioUtils.arrayBufferToBase64(buffer);
  }
  lastAudioMime = mime;
  logPlayback("PLAY_ARRAY_BUFFER", { bytes: buffer.byteLength, mime });
  try {
    await playViaWebAudio(buffer, mime);
    return true;
  } catch (webErr) {
    logPlayback("WEBAUDIO_FAILED", { message: String(webErr.message || webErr) });
    playback.userGesture();
    return playback.enqueueBytes(buffer, mime);
  }
}

/** Shared REST TTS + auto/manual playback. */
async function speakTextViaRest(text, lang = "te-IN") {
  const trimmed = (text || "").trim();
  if (!trimmed) { logPlayback("TTS_SKIP_EMPTY", {}); return false; }
  if (_speakInFlight) { logPlayback("TTS_SKIP_DUPLICATE", {}); return false; }
  _speakInFlight = true;
  setState("Speaking…");
  ttsError.style.display = "none";
  try {
    await ensurePlaybackContext();
    const cfg = await getResolvedTtsConfig(lang);
    logPlayback("TTS_REQUEST", { speaker: cfg.speaker, model: cfg.model, chars: trimmed.length });
    const r = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: trimmed.slice(0, 2500),
        language_code: lang,
        sessionId,
        speaker: cfg.speaker,
        pace: cfg.pace,
        model: cfg.model,
        temperature: cfg.temperature,
      }),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      const msg = (j.detail && j.detail.error && j.detail.error.message) || r.statusText;
      logPlayback("TTS_HTTP_ERROR", { status: r.status, msg });
      throw new Error(msg);
    }
    const buf = await r.arrayBuffer();
    if (!buf.byteLength) {
      logPlayback("TTS_EMPTY_RESPONSE", {});
      throw new Error("TTS returned empty audio — check Sarvam API key and speaker settings");
    }
    const speaker = r.headers.get("x-speaker") || cfg.speaker;
    const mime = r.headers.get("content-type") || "audio/wav";
    ttsInfo.textContent = `• ${speaker} • ${buf.byteLength} bytes • AUTO`;
    logPlayback("TTS_OK", { speaker, bytes: buf.byteLength, mime });
    await playArrayBuffer(buf, mime);
    return true;
  } catch (e) {
    ttsError.style.display = "block";
    ttsError.textContent = "TTS error: " + String(e.message || e);
    logPlayback("TTS_ERROR", { message: String(e.message || e) });
    return false;
  } finally {
    _speakInFlight = false;
  }
}

refreshRuntimeSettings();
refreshVoiceConfig();
if (realtimeMode) realtimeMode.checked = true;
if ($("handsFree")) $("handsFree").checked = true;

// Playback state
let lastAudioBase64 = null;
let lastAudioMime = "audio/wav";
let lastBrainText = "";
let currentObjectUrl = null;
let consecutiveEmpty = 0;
let playbackCtx = null;          // unlocked on mic click — survives async brain delay
let _speakInFlight = false;      // prevent duplicate auto-speak
let currentWebAudioSource = null; // for barge-in stop

/** Shared AudioContext resumed on mic gesture — browsers allow playback through this after STT. */
async function ensurePlaybackContext() {
  const existing = (live.active && live.ctx) ? live.ctx : playbackCtx;
  if (existing) {
    if (existing.state === "suspended") await existing.resume();
    playbackCtx = existing;
    return existing;
  }
  playbackCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (playbackCtx.state === "suspended") await playbackCtx.resume();
  return playbackCtx;
}

/** Play via Web Audio API (works after async brain delay when HTML audio.play() is blocked). */
async function playViaWebAudio(buffer, mime = "audio/wav") {
  const ctx = await ensurePlaybackContext();
  const copy = buffer.slice(0);
  const audioBuffer = await ctx.decodeAudioData(copy);
  if (currentWebAudioSource) { try { currentWebAudioSource.stop(); } catch {} currentWebAudioSource = null; }
  return new Promise((resolve, reject) => {
    const source = ctx.createBufferSource();
    currentWebAudioSource = source;
    source.buffer = audioBuffer;
    source.connect(ctx.destination);
    live.agentSpeaking = true;
    stopAudioBtn.style.display = "";
    source.onended = () => {
      currentWebAudioSource = null;
      live.agentSpeaking = false;
      logPlayback("WEBAUDIO_ENDED", { duration: audioBuffer.duration });
      if (playback.onFinished) playback.onFinished({ via: "webaudio" });
      resolve(true);
    };
    try {
      source.start(0);
      logPlayback("WEBAUDIO_STARTED", { duration: audioBuffer.duration, mime });
      if (playback.onStarted) playback.onStarted({ via: "webaudio" });
    } catch (e) {
      live.agentSpeaking = false;
      reject(e);
    }
  });
}

// ---- Hands-free AudioPlaybackManager (auto-play, queue, no overlap) ----
const playback = new AudioPlaybackManager(audioPlayer);
playback.onLog = (tag, extra) => logPlayback(tag, extra);

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

$("unlockAudio")?.addEventListener("click", () => {
  const u = $("unlockAudio");
  if (u) u.style.display = "none";
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

// -- Helpers: audio play (auto via Web Audio + manager fallback) --
async function playBase64(base64, mime = "audio/wav") {
  let buffer;
  try {
    buffer = window.AudioUtils
      ? window.AudioUtils.base64ToArrayBuffer(base64)
      : (() => { const b = atob(base64); const u = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u.buffer; })();
  } catch (e) {
    logPlayback("BASE64_DECODE_ERROR", { message: String(e.message || e) });
    return false;
  }
  lastAudioBase64 = base64;
  lastAudioMime = mime;
  return playArrayBuffer(buffer, mime);
}
function stopAudio() {
  live.agentSpeaking = false;
  _speakInFlight = false;
  stopPcmPlayback();
  if (currentWebAudioSource) { try { currentWebAudioSource.stop(); } catch {} currentWebAudioSource = null; }
  playback.stopAll();
  audioPlayer.style.display = "none";
  if (voiceAbort) { try { voiceAbort.abort(); } catch {} voiceAbort = null; }
  // Fire interrupt to server (barge-in)
  try { fetch("/api/session/interrupt", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sessionId }) }); } catch {}
  setState(live.active ? "Interrupted — listening…" : "Stopped");
}
stopAudioBtn.addEventListener("click", stopAudio);
replayBtn.addEventListener("click", async () => {
  if (lastAudioBase64) await playBase64(lastAudioBase64, lastAudioMime);
});
ttsOnlyBtn.addEventListener("click", async () => {
  playback.userGesture();
  await unlockAudioPlayback();
  const text = (responseEl.textContent || "").trim();
  if (!text || text.startsWith("—")) { ttsError.style.display = "block"; ttsError.textContent = "No response text to synthesize yet — ask something first."; return; }
  await speakTextViaRest(text);
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

const CACHE_MIN_TOKENS = 1024;
const BUDGET_MIN_TOKENS = 1500;
const BRAIN_PROMPT_MAX_CHARS = 20000;

function estimatePromptTokens(text) {
  const len = (text || "").length;
  return len ? Math.max(1, Math.ceil(len / 4)) : 0;
}

function getBrainBudgetTokens() {
  const el = $("brainPromptBudgetTokens");
  const n = el ? Number(el.value) : 1500;
  return Number.isFinite(n) ? n : 1500;
}

function updatePromptMeter() {
  if (!brainPromptEl) return;
  const text = brainPromptEl.value || "";
  const est = estimatePromptTokens(text);
  const budget = getBrainBudgetTokens();
  const pct = Math.min(100, (est / budget) * 100);
  const cachePct = Math.min(100, (CACHE_MIN_TOKENS / budget) * 100);
  if (brainCharCount) brainCharCount.textContent = String(text.length);
  if (brainTokenEst) brainTokenEst.textContent = String(est);
  if (brainTokenBudget) brainTokenBudget.textContent = String(budget);
  if (brainTokenFill) {
    brainTokenFill.style.width = pct + "%";
    brainTokenFill.classList.toggle("over", est > budget);
    brainTokenFill.classList.toggle("warn", est <= budget && est < CACHE_MIN_TOKENS);
  }
  const cacheMin = $("brainTokenCacheMin");
  if (cacheMin) cacheMin.style.left = cachePct + "%";
  if (brainCacheStatus) {
    if (est > budget) {
      brainCacheStatus.textContent = "Over budget";
      brainCacheStatus.className = "badge badge-warn";
    } else if (est < CACHE_MIN_TOKENS) {
      brainCacheStatus.textContent = "Cache OFF (<1024)";
      brainCacheStatus.className = "badge badge-warn";
    } else {
      brainCacheStatus.textContent = "Cache ON";
      brainCacheStatus.className = "badge badge-green";
    }
  }
  const cacheBadge = $("cacheBadge");
  if (cacheBadge) {
    cacheBadge.textContent = est >= CACHE_MIN_TOKENS ? "✅ Caching ON" : "⚠️ Caching OFF (<1024 tokens)";
    cacheBadge.className = est >= CACHE_MIN_TOKENS ? "badge badge-green" : "badge badge-warn";
  }
}

async function fetchDefaultBrainPrompt() {
  const r = await fetch("/api/instructions/default");
  if (!r.ok) throw new Error("Could not load default prompt");
  return r.json();
}

async function loadInstructions() {
  let defaultPrompt = "";
  try {
    const d = await fetchDefaultBrainPrompt();
    defaultPrompt = d.brainPrompt || "";
  } catch {}
  const local = localStorage.getItem("telugu_brain_prompt") || "";
  if (brainPromptEl) brainPromptEl.value = local || defaultPrompt;
  try {
    const r = await fetch("/api/instructions?sessionId=" + encodeURIComponent(sessionId));
    if (r.ok) {
      const j = await r.json();
      if (j.brainPrompt) {
        brainPromptEl.value = j.brainPrompt;
        localStorage.setItem("telugu_brain_prompt", j.brainPrompt);
      }
      if (j.customBrainPrompt || j.present) updateActiveBadge();
    }
  } catch {}
  promptsDirty = false;
  updatePromptMeter();
  updateActiveBadge();
}

function updateActiveBadge() {
  const has = brainPromptEl && (brainPromptEl.value || "").trim().length > 0;
  if (activeBadge) activeBadge.style.display = has ? "" : "none";
}

if (brainPromptEl) {
  brainPromptEl.addEventListener("input", () => {
    localStorage.setItem("telugu_brain_prompt", brainPromptEl.value);
    markPromptsDirty();
    updatePromptMeter();
  });
}
const budgetSlider = $("brainPromptBudgetTokens");
if (budgetSlider) budgetSlider.addEventListener("input", updatePromptMeter);

loadInstructions();

if (loadDefaultPromptBtn) loadDefaultPromptBtn.addEventListener("click", async () => {
  try {
    const d = await fetchDefaultBrainPrompt();
    if (brainPromptEl) brainPromptEl.value = d.brainPrompt || "";
    markPromptsDirty();
    updatePromptMeter();
    saveStatus.style.display = "block";
    saveStatus.textContent = "Default prompt loaded — click Save prompt to apply.";
    setTimeout(() => saveStatus.style.display = "none", 3000);
  } catch (e) {
    saveStatus.style.display = "block";
    saveStatus.textContent = "Failed to load default: " + e;
  }
});

saveBtn.addEventListener("click", async () => {
  saveStatus.style.display = "block";
  saveStatus.textContent = "Saving…";
  try {
    const text = getBrainPromptSafe();
    const r = await fetch("/api/instructions", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sessionId,
        brainPrompt: text,
        brainPromptBudgetTokens: getBrainBudgetTokens(),
      }),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail ? JSON.stringify(j.detail) : r.statusText);
    localStorage.setItem("telugu_brain_prompt", text);
    saveStatus.textContent = `Saved ✓ ${j.estimatedTokens}/${j.budgetTokens} tokens · cache ${j.cacheEligible ? "ON" : "OFF"} · headroom ${j.headroom}`;
    promptsDirty = false;
    updatePromptMeter();
    updateActiveBadge();
    setTimeout(() => saveStatus.style.display = "none", 4000);
  } catch (e) {
    saveStatus.textContent = "Save failed: " + String(e.message || e);
  }
});

resetBtn.addEventListener("click", async () => {
  try {
    const d = await fetchDefaultBrainPrompt();
    if (brainPromptEl) brainPromptEl.value = d.brainPrompt || "";
  } catch {}
  localStorage.removeItem("telugu_brain_prompt");
  updatePromptMeter();
  updateActiveBadge();
  saveStatus.style.display = "block";
  saveStatus.textContent = "Clearing saved prompt…";
  try {
    await fetch("/api/instructions?sessionId=" + encodeURIComponent(sessionId), { method: "DELETE" });
    promptsDirty = false;
    saveStatus.textContent = "Cleared ✓ — showing factory default (not saved until you click Save)";
  } catch { saveStatus.textContent = "Cleared locally ✓"; }
  setTimeout(() => saveStatus.style.display = "none", 3000);
});
function updateHistoryCount() {
  const domTurns = conversationEl
    ? Math.floor(conversationEl.querySelectorAll(".chat-msg.user").length)
    : 0;
  const stored = window.ConversationStore ? window.ConversationStore.turnCount() : 0;
  const turns = Math.max(domTurns, stored);
  if (historyCount) historyCount.textContent = turns ? `${turns} turn${turns === 1 ? "" : "s"} saved` : "No turns yet";
}

function restoreConversationFromStore() {
  if (!window.ConversationStore || !conversationEl) return;
  const data = window.ConversationStore.load();
  if (!data.turns.length) return;
  conversationEl.innerHTML = "";
  for (const t of data.turns) {
    if (t.user) addBubble("user", t.user);
    if (t.assistant) addBubble("assistant", t.assistant);
  }
  const last = data.turns[data.turns.length - 1];
  if (last) {
    if (last.user) { transcriptEl.textContent = last.user; transcriptEl.style.color = "var(--text)"; }
    if (last.assistant) { responseEl.textContent = last.assistant; responseEl.style.color = "var(--text)"; }
    if (last.audio && last.audio.base64) {
      lastAudioBase64 = last.audio.base64;
      lastAudioMime = last.audio.mime || "audio/wav";
    }
  }
  updateHistoryCount();
}
// View effective prompt (transparency)
if (viewPromptBtn) viewPromptBtn.addEventListener("click", async () => {
  effectivePrompt.style.display = "block";
  effectivePrompt.textContent = "Loading effective prompt…";
  try {
    const r = await fetch("/api/prompt/effective?sessionId=" + encodeURIComponent(sessionId) + "&transcript=" + encodeURIComponent("Python అంటే ఏమిటి?"));
    const j = await r.json();
    effectivePrompt.textContent = [
      `Tokens: ${j.estimatedTokens} / ${j.budgetTokens} (headroom ${j.headroom})`,
      `Cache: ${j.cacheEligible ? "ON" : "OFF"}`,
      `Sections: ${JSON.stringify(j.sections || {}, null, 2)}`,
      "",
      j.brainPrompt || "",
    ].join("\n");
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
const metricsBtnVisible = $("metricsBtnVisible");
const interruptBtnVisible = $("interruptBtnVisible");
if (metricsBtnVisible) metricsBtnVisible.addEventListener("click", () => metricsBtn?.click());
if (interruptBtnVisible) interruptBtnVisible.addEventListener("click", () => interruptBtn?.click());

function setMicUi(active, title) {
  if (!micBtn) return;
  micBtn.classList.toggle("recording", !!active);
  const t = title || (active ? "Stop voice session" : "Start voice session");
  micBtn.title = t;
  micBtn.setAttribute("aria-label", t);
}

// State
function setState(s) {
  if (!stateLabel) return;
  stateLabel.textContent = s.replace(/^Ready — /, "").replace(/^Listening… \(live.*\)/, "Listening");
  const low = s.toLowerCase();
  let cls = "state-pill";
  if (low.includes("listen")) cls += " is-listening";
  else if (low.includes("understand") || low.includes("processing") || low.includes("think")) cls += " is-thinking";
  else if (low.includes("speak") || low.includes("generating")) cls += " is-speaking";
  else cls += " is-ready";
  stateLabel.className = cls;
  if (micBtn) {
    const on = low.includes("listen") || low.includes("speak") || low.includes("think") || low.includes("understand");
    micBtn.classList.toggle("recording", on && (live.active || isRecording));
  }
}

// Conversation
function addBubble(role, text) {
  const d = document.createElement("div");
  d.className = "chat-msg " + role;
  const meta = document.createElement("div");
  meta.className = "chat-meta";
  meta.textContent = role === "user" ? "You" : "Agent";
  const body = document.createElement("div");
  body.className = "chat-body";
  body.textContent = text;
  d.appendChild(meta);
  d.appendChild(body);
  conversationEl.appendChild(d);
  conversationEl.scrollTop = conversationEl.scrollHeight;
  updateHistoryCount();
}
clearBtn.addEventListener("click", async () => {
  conversationEl.innerHTML = "";
  transcriptEl.textContent = "— waiting for speech —"; transcriptEl.style.color = "var(--muted)";
  responseEl.textContent = "— waiting —"; responseEl.style.color = "var(--muted)";
  usageEl.textContent = ""; metricsEl.textContent = "";
  if (ttsInfo) ttsInfo.textContent = ""; stopAudio();
  lastAudioBase64 = null; lastBrainText = "";
  if (replayBtn) replayBtn.disabled = true;
  setState("Ready — press mic and speak Telugu");
  if (window.ConversationStore) window.ConversationStore.clear();
  updateHistoryCount();
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
  ttsStreamCodec: "linear16",
  ttsTurnEnded: false,
  _flushAcked: false,
  _ttsPingTimer: null,
  ttsSampleRate: 24000,
  pcmPlayer: null,
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
  await refreshRuntimeSettings();
  await refreshVoiceConfig();
  await unlockAudioPlayback();
  // Pre-warm TTS WebSocket + config (Sarvam: connect once, stream many turns)
  if (voiceMode.checked) {
    ensureTtsStream(true).catch((e) => clientLog("voice", "[VOICE][TTS] pre-warm failed", e));
  }

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
    setMicUi(true, "Stop live session");
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

// Track unsaved prompt edits — brain calls omit overrides when saved (uses stored brainPrompt + cache).
let promptsDirty = false;

function markPromptsDirty() {
  promptsDirty = true;
  updateActiveBadge();
}

/** Build brain API body — only sends instruction overrides when user has unsaved edits. */
function buildBrainBody(transcript, extras = {}) {
  const body = {
    transcript,
    language_code: extras.language_code || "te-IN",
    sessionId,
  };
  if (promptsDirty && brainPromptEl) {
    const prompt = getBrainPromptSafe();
    if (prompt) body.brainPrompt = prompt;
  }
  return body;
}

function getBrainPromptSafe() {
  if (!brainPromptEl) return "";
  const raw = brainPromptEl.value.trim();
  if (raw.length > BRAIN_PROMPT_MAX_CHARS) {
    saveStatus.style.display = "block";
    saveStatus.textContent = `⚠️ Brain prompt too long (${raw.length}/${BRAIN_PROMPT_MAX_CHARS}) — using first ${BRAIN_PROMPT_MAX_CHARS}.`;
    setTimeout(() => saveStatus.style.display = "none", 4000);
    return raw.slice(0, BRAIN_PROMPT_MAX_CHARS);
  }
  return raw;
}

// ---------- STREAMING TURN (industry cascaded pipeline) ----------
// Brain SSE deltas → forwarded into Sarvam TTS WS as they arrive (Sarvam buffers
// and sentence-splits server-side via min_buffer_size/max_chunk_length) → audio
// chunks stream back → MediaSource plays from the FIRST sentence. No waiting for
// the full brain response. Barge-in aborts SSE + closes TTS + kills audio.

function ttsConfigFromConsole() {
  const v = runtimeSettings.values || {};
  const d = runtimeSettings.defaults || {};
  return {
    speaker: v.ttsSpeaker || d.ttsSpeaker || "shubh",
    language_code: v.sttLanguage || "te-IN",
    pace: v.ttsPace ?? d.ttsPace ?? 1.08,
    min_buffer_size: v.ttsMinBuffer ?? 30,
    max_chunk_length: v.ttsMaxChunk ?? 80,
    output_audio_codec: "linear16",
    output_audio_bitrate: v.ttsBitrate || "128k",
    temperature: v.ttsTemperature ?? d.ttsTemperature ?? 0.4,
    model: v.ttsModel || d.ttsModel || "bulbul:v3",
  };
}

function cleanupTtsTurn() {
  stopPcmPlayback();
  teardownMse();
  resetTtsAcc();
  live.mseDone = false;
  live.ttsTurnEnded = false;
  live._flushAcked = false;
  live._playAttempted = false;
  live._ttsAllB64 = [];
  if (currentWebAudioSource) {
    try { currentWebAudioSource.stop(); } catch {}
    currentWebAudioSource = null;
  }
  _speakInFlight = false;
}

function closeTtsSocket() {
  stopTtsPing();
  if (live.ttsSock) {
    try { live.ttsSock.close(1000); } catch {}
    live.ttsSock = null;
  }
  _ttsStreamReady = false;
  _ttsStreamInitPromise = null;
}

function startTtsPing() {
  stopTtsPing();
  live._ttsPingTimer = setInterval(() => {
    if (live.ttsSock && live.ttsSock.readyState === WebSocket.OPEN) {
      try { live.ttsSock.send(JSON.stringify({ type: "ping" })); } catch {}
    }
  }, 20000);
}

function stopTtsPing() {
  if (live._ttsPingTimer) { clearInterval(live._ttsPingTimer); live._ttsPingTimer = null; }
}

async function runTurn(text, sttFinalMs) {
  live.busy = true;
  live.turnN++;
  cleanupTtsTurn();
  await refreshRuntimeSettings();
  await refreshVoiceConfig();
  const autoEnabled = !!(voiceMode.checked || ($("handsFree") && $("handsFree").checked));
  console.log("[VOICE][AUTO] enabled=" + autoEnabled + " voiceLoop=" + voiceMode.checked + " handsFree=" + ($("handsFree") && $("handsFree").checked));
  addBubble("user", text);
  setState("Thinking…");
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
  let sseFailed = null;
  let usedStreamingTts = false;
  let ttsReady = false;
  const pendingTtsDeltas = [];

  // Open TTS WebSocket in parallel with brain — speak first sentence while brain still streams
  const ttsOpenP = (voiceMode.checked && autoEnabled)
    ? ensureTtsStream(true)
        .then(() => {
          usedStreamingTts = true;
          ttsReady = true;
          flushTtsPendingSend();
          flushTtsAccToSocket();
          for (const d of pendingTtsDeltas) pushTtsText(d);
          pendingTtsDeltas.length = 0;
        })
        .catch((e) => {
          clientLog("voice", "[VOICE][TTS] stream open failed", e);
          usedStreamingTts = false;
          ttsReady = false;
          pendingTtsDeltas.length = 0;
        })
    : Promise.resolve();

  const pipeline = readBrainSSE(text, {
    onDelta(delta, fullSoFar) {
      if (_perf && !_perf.brainFirstDelta) { _perf.brainFirstDelta = performance.now() - _perf.t0; console.log("[VOICE][BRAIN] FIRST_DELTA"); }
      full = fullSoFar;
      responseEl.textContent = full;
      responseEl.style.color = "var(--text)";
      if (voiceMode.checked && autoEnabled) {
        if (ttsReady) pushTtsText(delta);
        else pendingTtsDeltas.push(delta);
      }
    },
  })
    .then((finalText) => { full = finalText || full; })
    .catch((e) => { sseFailed = e; });

  await Promise.all([pipeline, ttsOpenP]);

  // Interrupted mid-think/mid-speech by user speech? Yield without fallback spam.
  if (voiceAbort.signal.aborted) {
    live.busy = false;
    backToListening();
    return;
  }

  if (sseFailed) {
    cleanupTtsTurn();
    // Fallback: one-shot JSON brain + single TTS (still keeps session live)
    live.busy = false;
    try {
      const br = await fetch("/api/brain", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildBrainBody(text)),
      });
      const bj = await br.json().catch(() => ({}));
      if (!br.ok) throw new Error(extractErr(bj, br.status));
      full = (bj.text || "").trim();
      responseEl.textContent = full; responseEl.style.color = "var(--text)";
      addBubble("assistant", full);
      setState("Speaking…");
      if (voiceConfig.httpTtsFallback) {
        await speakTextViaRest(full);
      } else {
        clientLog("voice", "[VOICE][TTS] Brain SSE failed — HTTP fallback disabled");
        responseEl.textContent = "Brain error: " + (sseFailed.message || sseFailed);
        responseEl.style.color = "#ff8a80";
      }
    } catch (e2) {
      responseEl.textContent = "Brain error: " + (e2.message || e2); responseEl.style.color = "#ff8a80";
      backToListening(); return;
    }
  } else {
    if (!full.trim()) { full = "క్షమించండి, నాకు అర్థం కాలేదు."; responseEl.textContent = full; }
    addBubble("assistant", full);
    if (full.trim() && voiceMode.checked && autoEnabled) {
      if (usedStreamingTts) {
        closeTtsStream();
        setState("Speaking…");
        live.agentSpeaking = true;
        const gotAudio = await waitForStreamingAudio(10000);
        if (gotAudio) {
          logPlayback("AUTO_SPEAK_STREAMING", { chars: full.length });
          await waitStreamingPlaybackDone();
        } else if (voiceConfig.httpTtsFallback) {
          cleanupTtsTurn();
          logPlayback("AUTO_SPEAK_REST_FALLBACK", { chars: full.length, reason: "no_ws_audio" });
          await speakTextViaRest(full);
        } else {
          clientLog("voice", "[VOICE][TTS] STREAM_NO_AUDIO — HTTP fallback disabled (set VOICE_HTTP_TTS_FALLBACK=true to enable)");
          ttsError.style.display = "block";
          ttsError.textContent = "Streaming TTS produced no audio — check server [WS] logs";
        }
        live.agentSpeaking = false;
      } else if (voiceConfig.httpTtsFallback) {
        cleanupTtsTurn();
        logPlayback("AUTO_SPEAK_REST_FALLBACK", { chars: full.length, reason: "ws_unavailable" });
        live.agentSpeaking = true;
        await speakTextViaRest(full);
        live.agentSpeaking = false;
      } else {
        clientLog("voice", "[VOICE][TTS] WS unavailable — HTTP fallback disabled");
        ttsError.style.display = "block";
        ttsError.textContent = "TTS WebSocket unavailable — restart live session";
      }
    } else {
      cleanupTtsTurn();
    }
  }

  usageEl.textContent = `→ te-IN${/[A-Za-z]/.test(full) && /[\u0C00-\u0C7F]/.test(full) ? " • code-mixed" : ""} • ${full.length} chars`;
  saveConversationTurn(text, full);
  live.busy = false;
  if (live.pendingFinal) { const t = live.pendingFinal; live.pendingFinal = null; runTurn(t); return; }
  backToListening();
}

// SSE reader for POST /api/brain/stream — resolves with final text
async function readBrainSSE(transcript, hooks) {
  const resp = await fetch("/api/brain/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildBrainBody(transcript)),
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

// Resolves when streamed TTS delivers first audio chunk (after flush)
function waitForStreamingAudio(timeoutMs = 10000) {
  return new Promise((resolve) => {
    if (live.pcmPlayer?.hadAudio() || live._ttsAllB64?.length > 0 || live.mseQueue.length > 0) {
      resolve(true);
      return;
    }
    const t0 = performance.now();
    const iv = setInterval(() => {
      if (live.pcmPlayer?.hadAudio() || live._ttsAllB64?.length > 0 || live.mseQueue.length > 0) {
        clearInterval(iv);
        resolve(true);
      } else if (performance.now() - t0 > timeoutMs) {
        clearInterval(iv);
        resolve(false);
      }
    }, 40);
  });
}

// Resolves when current streamed playback finishes (PCM or MSE)
function waitStreamingPlaybackDone(timeoutMs = 120000) {
  return new Promise((resolve) => {
    const finish = () => resolve();
    const timer = setTimeout(finish, timeoutMs);
    const poll = setInterval(() => {
      if (voiceAbort?.signal?.aborted) { clearInterval(poll); clearTimeout(timer); finish(); return; }
      if (live.ttsStreamCodec === "linear16") {
        const pcmDone = live.pcmPlayer?.hadAudio() && live.pcmPlayer.idle();
        if (pcmDone && (live.ttsTurnEnded || live._flushAcked)) {
          clearInterval(poll); clearTimeout(timer); live.agentSpeaking = false; finish();
        }
        return;
      }
      if (!live.ttsTurnEnded && !live.mseDone) return;
      const sockDone = !live.ttsSock || live.ttsSock.readyState >= WebSocket.CLOSING;
      if (!live.mseDone || !sockDone) return;
      if (audioPlayer.ended) { clearInterval(poll); clearTimeout(timer); live.agentSpeaking = false; finish(); return; }
      if (!audioPlayer.paused && audioPlayer.currentTime > 0) {
        audioPlayer.onended = () => { clearInterval(poll); clearTimeout(timer); live.agentSpeaking = false; finish(); };
        return;
      }
      if (live.mseQueue.length === 0 && !live.sb?.updating && audioPlayer.paused) {
        clearInterval(poll); clearTimeout(timer); live.agentSpeaking = false; finish();
      }
    }, 60);
  });
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
  stopPcmPlayback();
  resetTtsAcc();
  live.mseDone = false;
  live.ttsTurnEnded = false;
  live._flushAcked = false;
  hooks_onAudioFirst = null;
  stopAudioBtn.style.display = "none";
  // 2) STOP GENERATION
  if (voiceAbort) { try { voiceAbort.abort(); } catch {} }
  if (live.ttsSock && live.ttsSock.readyState === WebSocket.OPEN) {
    try { live.ttsSock.send(JSON.stringify({ type: "flush" })); } catch {}
  }
  // Keep persistent TTS WebSocket open — do NOT close on barge-in (fix.md Issue #4)
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
let _ttsStreamReady = false;
let _ttsStreamInitPromise = null;

/** Reuse one TTS WebSocket for the whole live session; re-send config each turn. */
function ensureTtsStream(reconfigure = false) {
  const rs = live.ttsSock?.readyState;
  if (rs === WebSocket.OPEN && _ttsStreamReady && !reconfigure) {
    return Promise.resolve(live.ttsSock);
  }
  if (rs === WebSocket.OPEN && (reconfigure || !_ttsStreamReady)) {
    return sendTtsConfigOnSocket(live.ttsSock).then(() => {
      _ttsStreamReady = true;
      startTtsPing();
      return live.ttsSock;
    });
  }
  if (rs === WebSocket.CONNECTING && _ttsStreamInitPromise) {
    return _ttsStreamInitPromise;
  }
  if (live.ttsSock && rs !== WebSocket.OPEN) {
    try { live.ttsSock.close(); } catch {}
    live.ttsSock = null;
    _ttsStreamReady = false;
  }
  if (_ttsStreamInitPromise) return _ttsStreamInitPromise;
  _ttsStreamInitPromise = openTtsStream().finally(() => { _ttsStreamInitPromise = null; });
  return _ttsStreamInitPromise;
}

async function sendTtsConfigOnSocket(sock) {
  const cfg = await getResolvedTtsConfig("te-IN");
  ttsModelCache = cfg.model || "bulbul:v3";
  const outCodec = "linear16";
  live.ttsStreamCodec = outCodec;
  live.ttsSampleRate = cfg.sample_rate || 24000;
  const minBuf = Math.max(30, Math.min(200, cfg.min_buffer_size ?? 30));
  const maxChunk = Math.max(50, Math.min(500, cfg.max_chunk_length ?? 80));
  const cfgData = {
    language_code: cfg.language_code || "te-IN",
    pace: cfg.pace,
    min_buffer_size: minBuf,
    max_chunk_length: maxChunk,
    output_audio_codec: outCodec,
    output_audio_bitrate: cfg.output_audio_bitrate || "128k",
    sample_rate: live.ttsSampleRate,
  };
  if (cfg.temperature != null && ttsModelCache === "bulbul:v3") cfgData.temperature = cfg.temperature;
  clientLog("voice", "[VOICE][TTS] CONFIG", cfgData);
  sock.send(JSON.stringify({ type: "config", data: cfgData }));
}

function markStreamingSpeechStarted() {
  if (!live.agentSpeaking) {
    live.agentSpeaking = true;
    setState("Speaking…");
    stopAudioBtn.style.display = "";
    ttsError.style.display = "none";
  }
}

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
  return new Promise(async (resolve, reject) => {
    const cfg = await getResolvedTtsConfig("te-IN");
    ttsModelCache = cfg.model || "bulbul:v3";
    // linear16 + Web Audio scheduling = lowest time-to-first-audio (Sarvam WS docs)
    const outCodec = "linear16";
    live.ttsStreamCodec = outCodec;
    live.ttsSampleRate = cfg.sample_rate || 24000;
    const sock = new WebSocket(
      wsUrl("/ws/tts?model=" + encodeURIComponent(ttsModelCache) + "&sessionId=" + encodeURIComponent(sessionId))
    );
    live.ttsSock = sock;
    live._ttsAllB64 = [];
    live.mseDone = false;
    live.ttsTurnEnded = false;
    live._playAttempted = false;
    live._fallbackBytes = [];
    let settled = false;

    if (_perf) { _perf.t5_ttsStart = performance.now(); alog("TTS_START"); }

    const ok = () => { if (!settled) { settled = true; _ttsStreamReady = true; resolve(sock); } };
    const fail = (e) => {
      console.log("[VOICE][TTS] ERROR", String(e && e.message || e));
      _ttsStreamReady = false;
      if (!settled) { settled = true; try { sock.close(); } catch {} if (live.ttsSock === sock) live.ttsSock = null; reject(e); }
    };

    async function playPcmChunk(arrayBuffer) {
      const ctx = await ensurePlaybackContext();
      if (!live.pcmPlayer) live.pcmPlayer = createPcmStreamPlayer(ctx, live.ttsSampleRate);
      live.pcmPlayer.appendPcm16(arrayBuffer);
      if (_perf && !_perf.t9_audioStarted) {
        _perf.t9_audioStarted = performance.now();
        logPerfSummary();
      }
      markStreamingSpeechStarted();
    }

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
      clientLog("perf", "[PERF]", JSON.stringify({
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
      sendTtsConfigOnSocket(sock).then(() => {
        startTtsPing();
        ok();
      }).catch(fail);
    };
    sock.onerror = () => fail(new Error("connection failed"));
    sock.onclose = (ev) => {
      _ttsStreamReady = false;
      stopTtsPing();
      if (live.ttsSock === sock) live.ttsSock = null;
      clientLog("voice", "[VOICE][TTS] WS closed", { code: ev.code, reason: ev.reason });
    };

    sock.onmessage = (ev) => {
      if (live.ttsSock !== sock) return;
      let m; try { m = JSON.parse(ev.data); } catch { return; }
      const type = m.type || m.event;

      if (type === "upstream_reset") {
        _ttsStreamReady = false;
        clientLog("voice", "[VOICE][TTS] upstream_reset — reconfig on next turn", m.reason);
        return;
      }

      const b64 = m.data && (m.data.audio || (typeof m.data === "string" ? m.data : null));

      if (b64) {
        if (_perf && !_perf.t6_firstAudio) { _perf.t6_firstAudio = performance.now(); console.log("[VOICE][TTS] FIRST_AUDIO"); }
        live._ttsAllB64.push(b64);
        lastAudioBase64 = live._ttsAllB64.join("");
        lastAudioMime = live.ttsStreamCodec === "linear16" ? "audio/pcm" : "audio/mpeg";
        replayBtn.disabled = false;
        const bin = atob(b64);
        const buf = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);

        if (live.ttsStreamCodec === "linear16") {
          playPcmChunk(buf.buffer).catch((e) => alog("PCM_PLAY_ERROR", String(e.message || e)));
        } else {
          const mseOk = ensureMSE();
          if (mseOk) {
            live.mseQueue.push(buf.buffer);
            pumpTts();
            maybeStartPlayback();
          } else {
            live._fallbackBytes.push(buf.buffer);
          }
          if (!live.agentSpeaking) markStreamingSpeechStarted();
        }
        if (typeof hooks_onAudioFirst === "function") { const h = hooks_onAudioFirst; hooks_onAudioFirst = null; h(); }
      } else if ((m.data && m.data.event_type === "final") || type === "end_of_stream") {
        live.mseDone = true;
        live.ttsTurnEnded = true;
        live._flushAcked = true;
        ttsInfo.textContent = `• WS ${ttsModelCache} • ${live._ttsAllB64.length} chunks • live`;
        if (live.ttsStreamCodec !== "linear16") {
          if (live._fallbackBytes.length) {
            const total = live._fallbackBytes.reduce((n, b) => n + b.byteLength, 0);
            const all = new Uint8Array(total);
            let o = 0; for (const b of live._fallbackBytes) { all.set(new Uint8Array(b), o); o += b.byteLength; }
            playBase64(all.buffer, "audio/mpeg").catch(() => {});
            live._fallbackBytes = [];
          } else {
            pumpTts();
          }
        }
        // Keep socket open for next turn — only flush, do not close
      } else if (type === "error") {
        live.agentSpeaking = false;
        fail(new Error(m.message || "tts ws error"));
      }
    };
  });
}

// ---- Live streaming text → TTS (forward brain tokens immediately; Sarvam buffers min_buffer_size) ----
let _ttsAcc = "";
const _ttsPendingSend = [];

function resetTtsAcc() {
  _ttsAcc = "";
  _ttsPendingSend.length = 0;
}

function flushTtsPendingSend() {
  if (!live.ttsSock || live.ttsSock.readyState !== WebSocket.OPEN) return;
  while (_ttsPendingSend.length) {
    const piece = _ttsPendingSend.shift();
    if (!piece) continue;
    try {
      live.ttsSock.send(JSON.stringify({ type: "text", data: { text: piece } }));
    } catch {}
  }
}

function flushTtsAccToSocket() {
  if (!_ttsAcc || !live.ttsSock || live.ttsSock.readyState !== WebSocket.OPEN) return;
  const text = _ttsAcc;
  _ttsAcc = "";
  try {
    live.ttsSock.send(JSON.stringify({ type: "text", data: { text } }));
    if (_perf && !_perf.firstSentence) _perf.firstSentence = performance.now();
  } catch {
    _ttsAcc = text + _ttsAcc;
  }
}

function sendTtsTextImmediate(text) {
  if (!text) return;
  if (live.ttsSock && live.ttsSock.readyState === WebSocket.OPEN) {
    try {
      live.ttsSock.send(JSON.stringify({ type: "text", data: { text } }));
      if (_perf && !_perf.firstSentence) {
        _perf.firstSentence = performance.now();
        clientLog("perf", "[VOICE][TTS] FIRST_SENTENCE", text.slice(0, 40));
      }
    } catch {
      _ttsPendingSend.push(text);
    }
  } else if (live.ttsSock && live.ttsSock.readyState === WebSocket.CONNECTING) {
    _ttsPendingSend.push(text);
  } else {
    _ttsAcc += text;
  }
}

/** Stream brain tokens → Sarvam WS. Flush on sentence boundaries for lower latency. */
const _SENT_END_RE = /[।.!?…\n]/;

function pushTtsText(delta) {
  if (!delta) return;
  _ttsAcc += delta;
  let cut = -1;
  for (let i = 0; i < _ttsAcc.length; i++) {
    if (_SENT_END_RE.test(_ttsAcc[i])) { cut = i; break; }
  }
  if (cut >= 0) {
    const sentence = _ttsAcc.slice(0, cut + 1);
    _ttsAcc = _ttsAcc.slice(cut + 1);
    if (sentence.trim().length >= 4) sendTtsTextImmediate(sentence);
  }
  if (_ttsAcc.length >= 40) {
    sendTtsTextImmediate(_ttsAcc);
    _ttsAcc = "";
  }
}

async function speakViaHttpStream(text) {
  const parts = [];
  let appended = false;
  try {
    const cfg = await getResolvedTtsConfig("te-IN");
    const r = await fetch("/api/tts/stream", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: text.slice(0, 3500),
        language_code: "te-IN",
        sessionId,
        speaker: cfg.speaker,
        pace: cfg.pace,
        model: cfg.model,
        temperature: cfg.temperature,
      }),
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
      await playArrayBuffer(all.buffer, "audio/mpeg");
      await new Promise(res => { audioPlayer.onended = res; setTimeout(res, 30000); });
    }
  } catch {}
}

function closeTtsStream() {
  flushTtsPendingSend();
  // Send any remaining buffered text, then flush the TTS socket
  const tail = _ttsAcc.trim(); _ttsAcc = "";
  if (tail && live.ttsSock && live.ttsSock.readyState === WebSocket.OPEN) {
    try { live.ttsSock.send(JSON.stringify({ type: "text", data: { text: tail } })); } catch {}
  }
  if (live.ttsSock && live.ttsSock.readyState === WebSocket.OPEN) {
    try { live.ttsSock.send(JSON.stringify({ type: "flush" })); } catch {}
    live._flushAcked = false;
    live.ttsTurnEnded = false;
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
  closeTtsStream();
  closeTtsSocket();
  stopPcmPlayback();
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
  setMicUi(false);
  liveBadge.style.display = "none";
  setState(msg);
}

async function startRecording() {
  if (!audioPlayer.paused) { stopAudio(); }
  if (voiceAbort) { try { voiceAbort.abort(); } catch {} voiceAbort = null; }
  await unlockAudioPlayback();
  await ensurePlaybackContext();
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
    setMicUi(true, "Stop recording");
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
    setMicUi(false);
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
  if (voiceAbort) try { voiceAbort.abort(); } catch {}
  voiceAbort = new AbortController();
  try {
    const r = await fetch("/api/brain", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildBrainBody(transcript, { language_code })),
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
    saveConversationTurn(transcript, text);
    if (voiceMode.checked && text) {
      console.log("[VOICE][AUTO] brain-only path → auto TTS");
      await speakTextViaRest(text, language_code);
    }
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
  if (promptsDirty && brainPromptEl) {
    fd.append("brainPrompt", getBrainPromptSafe());
  }
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
      lastAudioMime = j.content_type || "audio/wav";
      ttsInfo.textContent = `• ${lastAudioMime} • ${Math.round(j.audio_base64.length * 0.75)} bytes • AUTO`;
      logPlayback("VOICE_TURN_AUDIO", { bytes: j.audio_base64.length, mime: lastAudioMime });
      await playBase64(j.audio_base64, lastAudioMime);
    } else if (brainText) {
      logPlayback("VOICE_TURN_NO_AUDIO", { ttsMs: m.ttsMs });
      ttsError.style.display = "block";
      ttsError.textContent = "Server returned no audio — trying REST TTS fallback…";
      await speakTextViaRest(brainText);
    } else {
      logPlayback("VOICE_TURN_NO_TEXT", {});
      setState("Ready — no audio returned (check TTS config)");
    }
    saveConversationTurn(transcript, brainText);
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
  if (e.code === "Space" && document.activeElement !== brainPromptEl) { e.preventDefault(); micBtn.click(); }
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
  try {
    const r = await fetch("/api/brain", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(buildBrainBody(text, { language_code: lang })) });
    const j = await r.json();
    if (!r.ok) throw new Error(JSON.stringify(j));
    transcriptEl.textContent = text; transcriptEl.style.color = "var(--text)";
    responseEl.textContent = j.text; responseEl.style.color = "var(--text)";
    lastBrainText = j.text;
    addBubble("user", text); addBubble("assistant", j.text);
    saveConversationTurn(text, j.text);
    usageEl.textContent = `→ ${j.language_context?.responseLanguage || "te-IN"}`;
    if (voiceMode.checked && j.text) {
      await speakTextViaRest(j.text, "te-IN");
    } else setState("Ready — test done");
  } catch (e) { responseEl.textContent = "Test error: " + String(e); }
}

// Preview brain prompt (ephemeral) — uses /api/brain with current editor text
previewBtn.addEventListener("click", async () => {
  const prompt = getBrainPromptSafe();
  if (!prompt) { previewOutput.style.display = "block"; previewOutput.textContent = "Enter a brain prompt, then Test."; return; }
  previewOutput.style.display = "block"; previewOutput.textContent = "Testing…";
  try {
    const r = await fetch("/api/brain", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transcript: "Python అంటే ఏమిటి?", language_code: "te-IN", sessionId, brainPrompt: prompt }),
    });
    const j = await r.json();
    if (!r.ok) previewOutput.textContent = "Error: " + JSON.stringify(j);
    else previewOutput.textContent = "→ " + j.text;
  } catch (e) { previewOutput.textContent = "Network error: " + String(e); }
});

// Export conversation (TXT / JSON / WAV)
function bindExport(id, fn) {
  const btn = $(id);
  if (!btn || !window.ConversationStore) return;
  btn.addEventListener("click", () => {
    const n = window.ConversationStore.turnCount();
    if (!n) { alert("No conversation to export yet — start talking first."); return; }
    const result = fn();
    if (result === false || result === 0) alert("No audio available for this export yet.");
  });
}
bindExport("exportTxtBtn", () => window.ConversationStore.exportTxt());
bindExport("exportJsonBtn", () => window.ConversationStore.exportJson());
bindExport("exportWavBtn", () => window.ConversationStore.exportLastWav());
bindExport("exportAllWavBtn", () => window.ConversationStore.exportAllWav());

restoreConversationFromStore();
setState("Ready — press mic and speak Telugu");
updateHistoryCount();
