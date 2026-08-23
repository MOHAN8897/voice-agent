/**
 * settings.js — Fine-tune Console
 * Loads /api/settings/catalog → renders selects/sliders → loads /api/settings/runtime
 * Save → POST /api/settings/runtime (+ instructions + style via /api/instructions)
 */
const $ = (id) => document.getElementById(id);
const statusOut = $("statusOut");

let sessionId = localStorage.getItem("telugu_session_id") || (() => {
  const s = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());
  localStorage.setItem("telugu_session_id", s);
  return s;
})();
const sessionEl = $("sessionInfo");
if (sessionEl) sessionEl.textContent = "session " + sessionId.slice(0, 8);

let catalog = null;
let defaults = {};

function show(msg) {
  if (!statusOut) return;
  statusOut.style.display = "block";
  statusOut.textContent = typeof msg === "string" ? msg : JSON.stringify(msg, null, 2);
}

function safeGet(id) {
  const el = document.getElementById(id);
  if (!el) console.warn("[settings] missing element:", id);
  return el;
}

async function init() {
  try {
    catalog = await (await fetch("/api/settings/catalog")).json();
    const rt = await (await fetch("/api/settings/runtime?sessionId=" + encodeURIComponent(sessionId))).json();
    defaults = rt.defaults || {};
    render();
    loadRuntime(rt.values || {});
    const instr = await (await fetch("/api/instructions?sessionId=" + encodeURIComponent(sessionId))).json();
    const behavEl = safeGet("behaviourInstructions");
    const bizEl = safeGet("businessInstructions");
    const styleEl = safeGet("responseStyle");
    const behavCount = safeGet("behavCount");
    const bizCountEl = safeGet("bizCount");
    if (instr.behaviour && behavEl) { behavEl.value = instr.behaviour; if (behavCount) behavCount.textContent = instr.behaviour.length; }
    if (instr.business && bizEl) { bizEl.value = instr.business; if (bizCountEl) bizCountEl.textContent = instr.business.length; }
    if (instr.style && styleEl) styleEl.value = instr.style;
    const dot = safeGet("healthDot");
    const txt = safeGet("healthText");
    if (dot) dot.className = "dot ok";
    if (txt) txt.textContent = "Catalog loaded — tune anything below";
  } catch (e) {
    const dot = safeGet("healthDot");
    const txt = safeGet("healthText");
    if (dot) dot.className = "dot bad";
    if (txt) txt.textContent = "Server not reachable";
    show("Init error: " + e);
  }
}

function fillSelect(el, options, selected) {
  if (!el) return;
  el.innerHTML = "";
  for (const opt of options) {
    const value = typeof opt === "object" ? opt.value : opt;
    const label = typeof opt === "object" ? opt.label : opt;
    const o = document.createElement("option");
    o.value = value; o.textContent = label;
    if (String(selected) !== "undefined" && String(value) === String(selected)) o.selected = true;
    el.appendChild(o);
  }
}

function render() {
  fillSelect(safeGet("sttModel"), catalog.stt.models.map(m => ({ value: m.id, label: m.label })), defaults.sttModel);
  fillSelect(safeGet("sttMode"), catalog.stt.modes, "transcribe");
  fillSelect(safeGet("sttLanguage"), catalog.stt.languages, "te-IN");
  fillSelect(safeGet("sttStreamType"), catalog.stt.streamTypes.map(s => ({ value: s, label: s + (s === "fast" ? " (voice agents)" : s === "balanced" ? " (default)" : " (no partials)") })), "fast");
  fillSelect(safeGet("ttsModel"), catalog.tts.models.map(m => ({ value: m.id, label: m.label })), defaults.ttsModel);
  fillSpeakers();
  fillSelect(safeGet("ttsCodec"), catalog.tts.codecs, "mp3");
  fillSelect(safeGet("ttsSampleRate"), catalog.tts.sampleRates, 24000);
  fillSelect(safeGet("openaiModel"), catalog.openai.allowedModels.map(m => ({ value: m, label: m + (m === catalog.openai.currentModel ? " (env default)" : "") })), catalog.openai.currentModel);

  const bind = (id, out, fmt) => {
    const el = safeGet(id); const oel = safeGet(out);
    if (el && oel) el.addEventListener("input", () => oel.textContent = fmt(el.value));
  };
  bind("sttSilenceMs", "sttSilenceVal", v => v);
  bind("sttThreshold", "sttThreshVal", v => Number(v).toFixed(2));
  bind("ttsPace", "ttsPaceVal", v => Number(v).toFixed(2));
  bind("ttsTemperature", "ttsTempVal", v => Number(v).toFixed(2));
  bind("openaiTemperature", "oaiTempVal", v => Number(v).toFixed(1));
  bind("openaiMaxTokens", "oaiTokVal", v => v);

  const behavEl = safeGet("behaviourInstructions");
  const bizEl = safeGet("businessInstructions");
  const behavCount = safeGet("behavCount");
  const bizCountEl2 = safeGet("bizCount");
  if (behavEl && behavCount) behavEl.addEventListener("input", () => behavCount.textContent = behavEl.value.length);
  if (bizEl && bizCountEl2) bizEl.addEventListener("input", () => bizCountEl2.textContent = bizEl.value.length);
}

function fillSpeakers() {
  const modelEl = safeGet("ttsModel");
  if (!modelEl || !catalog) return;
  const model = modelEl.value;
  const list = model === "bulbul:v3" ? catalog.tts.speakersV3 : catalog.tts.speakersV2;
  const preferred = defaults.ttsSpeaker || "shubh";
  fillSelect(safeGet("ttsSpeaker"), list, list.includes(preferred) ? preferred : list[0]);
}
const ttsModelEl = safeGet("ttsModel");
if (ttsModelEl) ttsModelEl.addEventListener("change", fillSpeakers);

function loadRuntime(values) {
  const map = {
    sttModel: "sttModel", sttMode: "sttMode", sttLanguage: "sttLanguage", sttStreamType: "sttStreamType",
    sttSilenceMs: "sttSilenceMs", sttThreshold: "sttThreshold",
    ttsModel: "ttsModel", ttsSpeaker: "ttsSpeaker", ttsPace: "ttsPace", ttsTemperature: "ttsTemperature",
    ttsCodec: "ttsCodec", ttsSampleRate: "ttsSampleRate",
    openaiModel: "openaiModel", openaiTemperature: "openaiTemperature", openaiMaxTokens: "openaiMaxTokens",
  };
  for (const [key, id] of Object.entries(map)) {
    if (values[key] !== undefined && values[key] !== null) {
      const el = safeGet(id);
      if (el) { el.value = values[key]; el.dispatchEvent(new Event("input")); if (id === "ttsModel") fillSpeakers(); }
    }
  }
}

async function saveAll() {
  try {
    const getVal = (id) => { const el = safeGet(id); return el ? el.value : ""; };
    const getNum = (id) => { const el = safeGet(id); return el ? Number(el.value) : 0; };
    const patch = {
      sessionId,
      sttModel: getVal("sttModel"),
      sttMode: getVal("sttMode"),
      sttLanguage: getVal("sttLanguage"),
      sttStreamType: getVal("sttStreamType"),
      sttSilenceMs: getNum("sttSilenceMs"),
      sttThreshold: parseFloat(getVal("sttThreshold") || "0.3"),
      ttsModel: getVal("ttsModel"),
      ttsSpeaker: getVal("ttsSpeaker"),
      ttsPace: getNum("ttsPace"),
      ttsTemperature: getNum("ttsTemperature"),
      ttsCodec: getVal("ttsCodec"),
      ttsSampleRate: getNum("ttsSampleRate"),
      openaiModel: getVal("openaiModel"),
      openaiTemperature: parseFloat(getVal("openaiTemperature") || "0.7"),
      openaiMaxTokens: getNum("openaiMaxTokens"),
    };
    const r1 = await fetch("/api/settings/runtime", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
    const j1 = await r1.json();
    if (!r1.ok) throw new Error(j1.detail?.error?.message || JSON.stringify(j1));

    const behavVal = getVal("behaviourInstructions");
    const bizVal = getVal("businessInstructions");
    const styleVal = getVal("responseStyle");
    const r2 = await fetch("/api/instructions", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId, behaviourInstructions: behavVal, businessInstructions: bizVal, responseStyle: styleVal }),
    });
    const j2 = await r2.json();
    if (!r2.ok) throw new Error(j2.detail?.error?.message || JSON.stringify(j2));
    localStorage.setItem("telugu_behaviour", behavVal);
    localStorage.setItem("telugu_business", bizVal);
    localStorage.setItem("telugu_response_style", styleVal);

    show("✅ Saved — voice turns now use these settings.\n"
      + `Behaviour ${(j2.behaviourLength ?? behavVal.length)}/10000 • Business ${(j2.businessLength ?? bizVal.length)}/10000\n\n`
      + JSON.stringify(j1.values || {}, null, 2));
  } catch (e) {
    show("❌ Save failed: " + (e.message || e));
  }
}
const saveBtn = safeGet("saveAllBtn");
if (saveBtn) saveBtn.addEventListener("click", saveAll);

const resetBtn = safeGet("resetBtn");
if (resetBtn) resetBtn.addEventListener("click", async () => {
  try {
    await fetch("/api/settings/runtime?sessionId=" + encodeURIComponent(sessionId), { method: "DELETE" });
    await fetch("/api/instructions?sessionId=" + encodeURIComponent(sessionId), { method: "DELETE" });
    ["telugu_behaviour","telugu_business","telugu_custom_instructions","telugu_response_style"].forEach(k => localStorage.removeItem(k));
    location.reload();
  } catch (e) { show("Reset failed: " + e); }
});

const viewBtn = safeGet("viewPromptBtn");
if (viewBtn) viewBtn.addEventListener("click", async () => {
  try {
    const r = await fetch("/api/prompt/effective?sessionId=" + encodeURIComponent(sessionId));
    show(await r.json());
  } catch (e) { show(String(e)); }
});

const testBtn = safeGet("testTtsBtn");
if (testBtn) testBtn.addEventListener("click", async () => {
  const st = safeGet("ttsTestStatus");
  if (st) { st.style.display = "block"; st.textContent = "Synthesizing…"; }
  try {
    const r = await fetch("/api/tts", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: "హాయ్! ఇది మీ fine-tune console test voice.",
        language_code: "te-IN",
        speaker: safeGet("ttsSpeaker")?.value || "shubh",
        pace: Number(safeGet("ttsPace")?.value || 1),
        temperature: Number(safeGet("ttsTemperature")?.value || 0.6),
        model: safeGet("ttsModel")?.value || "bulbul:v3",
      }),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      throw new Error((j.detail && j.detail.error && j.detail.error.message) || r.statusText);
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = safeGet("testAudio");
    if (a) { a.src = url; a.style.display = "block"; a.play().catch(() => {}); }
    if (st) st.textContent = `✅ Played ${Math.round(blob.size)} bytes • ${safeGet("ttsSpeaker")?.value} • ${safeGet("ttsModel")?.value}`;
  } catch (e) {
    if (st) st.textContent = "❌ TTS test failed: " + (e.message || e);
  }
});

init();
