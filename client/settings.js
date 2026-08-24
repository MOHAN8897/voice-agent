/**
 * settings.js — Fine-tune console (IIFE — no conflict with app.js)
 */
(function () {
  const statusOut = document.getElementById("statusOut");
  let sessionId = localStorage.getItem("telugu_session_id");
  if (!sessionId) {
    sessionId = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());
    localStorage.setItem("telugu_session_id", sessionId);
  }
  const sessionEl = document.getElementById("sessionInfo");
  if (sessionEl) sessionEl.textContent = "session " + sessionId.slice(0, 8);

  let catalog = null;
  let defaults = {};
  let runtimeValues = {};

  function show(msg, target) {
    const el = target || statusOut;
    if (!el) return;
    el.style.display = "block";
    el.textContent = typeof msg === "string" ? msg : JSON.stringify(msg, null, 2);
  }

  function safeGet(id) {
    return document.getElementById(id);
  }

  function fillSelect(el, options, selected) {
    if (!el) return;
    el.innerHTML = "";
    for (const opt of options) {
      const value = typeof opt === "object" ? opt.value : opt;
      const label = typeof opt === "object" ? opt.label : opt;
      const o = document.createElement("option");
      o.value = value;
      o.textContent = label;
      if (String(selected) !== "undefined" && String(value) === String(selected)) o.selected = true;
      el.appendChild(o);
    }
  }

  function updateRuntimeSummary() {
    const el = safeGet("runtimeSummary");
    if (!el) return;
    const m = safeGet("openaiModel")?.value || runtimeValues.openaiModel || defaults.openaiModel || "—";
    const spk = safeGet("ttsSpeaker")?.value || runtimeValues.ttsSpeaker || defaults.ttsSpeaker || "—";
    const ttsM = safeGet("ttsModel")?.value || runtimeValues.ttsModel || defaults.ttsModel || "—";
    el.textContent = `Active config → Brain: ${m} • TTS: ${ttsM}/${spk} • session ${sessionId.slice(0, 8)}`;
  }

  async function init() {
    try {
      catalog = await (await fetch("/api/settings/catalog")).json();
      const rt = await (await fetch("/api/settings/runtime?sessionId=" + encodeURIComponent(sessionId))).json();
      const oaiDefaults = catalog.openai?.defaults || {};
      defaults = { ...oaiDefaults, ...rt.defaults };
      runtimeValues = rt.values || {};
      render();
      loadRuntime(runtimeValues);

      const instr = await (await fetch("/api/instructions?sessionId=" + encodeURIComponent(sessionId))).json();
      const brainEl = safeGet("brainPrompt");
      if (brainEl) {
        if (instr.brainPrompt) {
          brainEl.value = instr.brainPrompt;
        } else {
          try {
            const d = await (await fetch("/api/instructions/default")).json();
            brainEl.value = d.brainPrompt || "";
          } catch {}
        }
        if (safeGet("brainCharCount")) safeGet("brainCharCount").textContent = brainEl.value.length;
      }

      applyCatalogDefaults(oaiDefaults);

      const dot = safeGet("healthDot");
      const txt = safeGet("healthText");
      if (dot) dot.className = "dot ok";
      if (txt) txt.textContent = "Ready";
      updateRuntimeSummary();

      const hint = safeGet("modelGroupHint");
      if (hint && catalog.openai.allowedModels) {
        updateBrainModelUi();
      }
    } catch (e) {
      if (safeGet("healthDot")) safeGet("healthDot").className = "dot bad";
      if (safeGet("healthText")) safeGet("healthText").textContent = "Server not reachable";
      show("Init error: " + e);
    }
  }

  function applyCatalogDefaults(oaiDefaults) {
    if (!oaiDefaults) return;
    const pairs = [
      ["openaiMaxTokens", "openaiMaxTokens"],
      ["brainPromptBudgetTokens", "brainPromptBudgetTokens"],
      ["openaiReasoningEffort", "openaiReasoningEffort"],
      ["voicePresetId", "voicePresetId"],
    ];
    for (const [id, key] of pairs) {
      if (runtimeValues[key] != null) continue;
      const el = safeGet(id);
      const val = oaiDefaults[key];
      if (el && val != null) {
        el.value = val;
        el.dispatchEvent(new Event("input"));
      }
    }
  }

  function getVoicePresets() {
    return catalog?.tts?.voicePresets || {};
  }

  function applyVoicePresetToForm(presetId, { silent = false } = {}) {
    const presets = getVoicePresets();
    const pid = presets[presetId] ? presetId : (catalog?.tts?.defaultVoicePresetId || "natural");
    const preset = presets[pid];
    if (!preset) return false;
    const setVal = (id, val) => {
      const el = safeGet(id);
      if (el && val != null) el.value = val;
    };
    const v = preset.values || {};
    setVal("voicePresetId", pid);
    setVal("ttsPace", v.ttsPace);
    setVal("ttsTemperature", v.ttsTemperature);
    setVal("sttSilenceMs", v.sttSilenceMs);
    setVal("sttThreshold", v.sttThreshold);
    setVal("sttStreamType", v.sttStreamType);
    setVal("bargeMinWords", v.bargeMinWords);
    setVal("bargeRequireVad", v.bargeRequireVad ? "true" : "false");
    setVal("ttsMinBuffer", v.ttsMinBuffer);
    setVal("ttsMaxChunk", v.ttsMaxChunk);
    const hint = safeGet("voicePresetHint");
    if (hint) hint.textContent = preset.hint || "";
    const summary = safeGet("voicePresetSummary");
    if (summary) {
      summary.innerHTML = [
        `Pace: <b>${v.ttsPace}×</b>`,
        `Temperature: <b>${v.ttsTemperature}</b>`,
        `VAD silence: <b>${v.sttSilenceMs} ms</b>`,
        `Barge-in: <b>${v.bargeMinWords} words + VAD</b>`,
      ].map((x) => `<li>${x}</li>`).join("");
    }
    updateRuntimeSummary();
    if (!silent) show(`Applied voice profile: ${preset.name || pid}`);
    return true;
  }

  let _voicePresetBound = false;

  function renderVoicePresets() {
    const presets = getVoicePresets();
    const ids = Object.keys(presets);
    const def = catalog?.tts?.defaultVoicePresetId || "natural";
    const selected = runtimeValues.voicePresetId || defaults.voicePresetId || def;
    fillSelect(
      safeGet("voicePresetId"),
      ids.map((id) => ({ value: id, label: presets[id].name || id })),
      selected
    );
    applyVoicePresetToForm(selected, { silent: true });
    const sel = safeGet("voicePresetId");
    if (sel && !_voicePresetBound) {
      sel.addEventListener("change", () => applyVoicePresetToForm(sel.value));
      _voicePresetBound = true;
    }
  }

  function getModelPreset(model) {
    return catalog?.openai?.modelPresets?.[model] || null;
  }

  function applyModelPreset(model, { silent = false } = {}) {
    const preset = getModelPreset(model);
    if (!preset) return false;
    const setVal = (id, val) => {
      const el = safeGet(id);
      if (el && val != null) {
        el.value = val;
        el.dispatchEvent(new Event("input"));
        el.dispatchEvent(new Event("change"));
      }
    };
    setVal("openaiReasoningEffort", preset.openaiReasoningEffort);
    setVal("openaiMaxTokens", preset.openaiMaxTokens);
    setVal("brainPromptBudgetTokens", preset.brainPromptBudgetTokens);
    if (preset.openaiTemperature != null) setVal("openaiTemperature", preset.openaiTemperature);
    const summary = safeGet("brainPresetSummary");
    if (summary) {
      summary.innerHTML = [
        `Max tokens: <b>${preset.openaiMaxTokens}</b>`,
        `Prompt budget: <b>${preset.brainPromptBudgetTokens}</b>`,
        `Reasoning: <b>${preset.openaiReasoningEffort || "—"}</b>`,
      ].map((x) => `<li>${x}</li>`).join("");
    }
    updateBrainModelUi();
    updateRuntimeSummary();
    if (!silent && typeof window.updatePromptMeter === "function") window.updatePromptMeter();
    const hint = safeGet("modelGroupHint");
    if (hint) {
      hint.innerHTML = `<b>${preset.name || model}</b> — ${preset.hint || ""}`;
    }
    return true;
  }

  function updateBrainModelUi() {
    const model = safeGet("openaiModel")?.value || "";
    const hint = safeGet("modelGroupHint");
    const preset = getModelPreset(model);
    if (hint) {
      hint.innerHTML = preset
        ? `<b>${preset.name}</b> — ${preset.hint}`
        : `${model} — pick a model and use Apply recommended settings.`;
    }
  }

  function render() {
    fillSelect(safeGet("sttModel"), catalog.stt.models.map((m) => ({ value: m.id, label: m.label })), defaults.sttModel);
    fillSelect(safeGet("sttMode"), catalog.stt.modes, "transcribe");
    fillSelect(safeGet("sttLanguage"), catalog.stt.languages, "te-IN");
    fillSelect(safeGet("ttsModel"), catalog.tts.models.map((m) => ({ value: m.id, label: m.label })), defaults.ttsModel);
    renderVoicePresets();
    fillSpeakers();
    fillSelect(safeGet("ttsCodec"), catalog.tts.codecs, "mp3");
    fillSelect(safeGet("ttsSampleRate"), catalog.tts.sampleRates, 24000);
    fillSelect(safeGet("ttsBitrate"), catalog.tts.bitrates || ["64k", "128k"], "128k");
    const labels = catalog.openai.modelLabels || {};
    fillSelect(
      safeGet("openaiModel"),
      catalog.openai.allowedModels.map((m) => ({
        value: m,
        label: (labels[m] || m) + (m === catalog.openai.currentModel ? " ★ env" : ""),
      })),
      runtimeValues.openaiModel || catalog.openai.currentModel || catalog.openai.defaultModel
    );

    const bind = (id, out, fmt) => {
      const el = safeGet(id);
      const oel = safeGet(out);
      if (el && oel) el.addEventListener("input", () => { oel.textContent = fmt(el.value); updateRuntimeSummary(); });
    };

    const brainEl = safeGet("brainPrompt");
    if (brainEl && safeGet("brainCharCount")) {
      brainEl.addEventListener("input", () => { safeGet("brainCharCount").textContent = brainEl.value.length; });
    }

    ["openaiModel", "ttsModel", "ttsSpeaker"].forEach((id) => {
      const el = safeGet(id);
      if (el) el.addEventListener("change", () => {
        updateRuntimeSummary();
        if (id === "openaiModel") {
          updateBrainModelUi();
          applyModelPreset(el.value, { silent: true });
        }
      });
    });
    if (safeGet("applyModelPresetBtn")) {
      safeGet("applyModelPresetBtn").addEventListener("click", () => {
        const model = safeGet("openaiModel")?.value || "";
        if (applyModelPreset(model)) {
          show("Applied recommended settings for " + model);
        } else {
          show("No preset found for " + model);
        }
      });
    }
    updateBrainModelUi();
  }

  function fillSpeakers() {
    const modelEl = safeGet("ttsModel");
    if (!modelEl || !catalog) return;
    const list = modelEl.value === "bulbul:v3" ? catalog.tts.speakersV3 : catalog.tts.speakersV2;
    const preferred = runtimeValues.ttsSpeaker || defaults.ttsSpeaker || "shubh";
    fillSelect(safeGet("ttsSpeaker"), list, list.includes(preferred) ? preferred : list[0]);
    updateRuntimeSummary();
  }
  if (safeGet("ttsModel")) safeGet("ttsModel").addEventListener("change", fillSpeakers);

  function loadRuntime(values) {
    runtimeValues = values || {};
    const map = {
      voicePresetId: "voicePresetId",
      sttModel: "sttModel", sttMode: "sttMode", sttLanguage: "sttLanguage", sttStreamType: "sttStreamType",
      sttSilenceMs: "sttSilenceMs", sttThreshold: "sttThreshold",
      bargeMinWords: "bargeMinWords",
      ttsModel: "ttsModel", ttsSpeaker: "ttsSpeaker", ttsPace: "ttsPace", ttsTemperature: "ttsTemperature",
      ttsCodec: "ttsCodec", ttsSampleRate: "ttsSampleRate", ttsMinBuffer: "ttsMinBuffer", ttsMaxChunk: "ttsMaxChunk",
      ttsBitrate: "ttsBitrate",
      openaiModel: "openaiModel", openaiTemperature: "openaiTemperature", openaiReasoningEffort: "openaiReasoningEffort",
      openaiMaxTokens: "openaiMaxTokens",
      brainPromptBudgetTokens: "brainPromptBudgetTokens",
      crmProvider: "crmProvider", crmWebhook: "crmWebhook", crmFields: "crmFields", crmNotes: "crmNotes",
    };
    for (const [key, id] of Object.entries(map)) {
      if (values[key] !== undefined && values[key] !== null) {
        const el = safeGet(id);
        if (el) { el.value = values[key]; el.dispatchEvent(new Event("input")); if (id === "ttsModel") fillSpeakers(); }
      }
    }
    if (safeGet("crmEnabled")) safeGet("crmEnabled").checked = !!values.crmEnabled;
    if (safeGet("crmAutoSync")) safeGet("crmAutoSync").checked = !!values.crmAutoSync;
    if (values.voicePresetId) applyVoicePresetToForm(values.voicePresetId, { silent: true });
    else if (values.ttsPace != null || values.ttsTemperature != null) {
      const summary = safeGet("voicePresetSummary");
      if (summary) summary.innerHTML = "<li><b>Legacy custom values detected</b> — applying <b>Natural</b> profile. Click Save to persist.</li>";
      applyVoicePresetToForm("natural", { silent: true });
    }
    const model = values.openaiModel || safeGet("openaiModel")?.value;
    if (model) applyModelPreset(model, { silent: true });
  }

  async function saveAll() {
    try {
      const liveActive = typeof window.isVoiceLiveActive === "function" && window.isVoiceLiveActive();
      const getVal = (id) => safeGet(id)?.value ?? "";
      const getNum = (id) => Number(safeGet(id)?.value || 0);
      const getCheck = (id) => !!(safeGet(id)?.checked);
      const patch = {
        sessionId,
        voicePresetId: getVal("voicePresetId") || "natural",
        sttModel: getVal("sttModel"), sttMode: getVal("sttMode"), sttLanguage: getVal("sttLanguage"),
        ttsModel: getVal("ttsModel"), ttsSpeaker: getVal("ttsSpeaker"),
        ttsCodec: getVal("ttsCodec"), ttsSampleRate: getNum("ttsSampleRate"),
        ttsBitrate: getVal("ttsBitrate") || "128k",
        openaiModel: getVal("openaiModel"), openaiTemperature: parseFloat(getVal("openaiTemperature") || "0.7"),
        openaiReasoningEffort: getVal("openaiReasoningEffort") || undefined,
        openaiMaxTokens: getNum("openaiMaxTokens"),
        brainPromptBudgetTokens: getNum("brainPromptBudgetTokens") || 2500,
        crmEnabled: getCheck("crmEnabled"), crmAutoSync: getCheck("crmAutoSync"),
        crmProvider: getVal("crmProvider"), crmWebhook: getVal("crmWebhook"),
        crmFields: getVal("crmFields"), crmNotes: getVal("crmNotes"),
      };
      const r1 = await fetch("/api/settings/runtime", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
      const j1 = await r1.json();
      if (!r1.ok) throw new Error(j1.detail?.error?.message || JSON.stringify(j1));
      runtimeValues = j1.values || {};
      window.dispatchEvent(new CustomEvent("runtime-settings-saved", { detail: runtimeValues }));

      const r2 = await fetch("/api/instructions", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sessionId,
          brainPrompt: getVal("brainPrompt"),
          brainPromptBudgetTokens: getNum("brainPromptBudgetTokens") || 2500,
        }),
      });
      const j2 = await r2.json();
      if (!r2.ok) throw new Error(j2.detail?.error?.message || JSON.stringify(j2));

      updateRuntimeSummary();
      const cfgR = await fetch("/api/settings/tts-config?sessionId=" + encodeURIComponent(sessionId));
      const cfgJ = cfgR.ok ? await cfgR.json() : {};

      show(`✅ Saved!${liveActive ? "\n🔄 Live session: STT + TTS reconnected with new settings." : ""}\nTokens: ${j2.estimatedTokens}/${j2.budgetTokens} · cache ${j2.cacheEligible ? "ON" : "OFF"}\nBrain model: ${patch.openaiModel}\nTTS speaker: ${cfgJ.ttsConfig?.speaker || patch.ttsSpeaker}\n\n` + JSON.stringify(j1.values, null, 2));
      const cacheBadge = safeGet("cacheBadge");
      if (cacheBadge && j2.cacheEligible != null) {
        cacheBadge.textContent = j2.cacheEligible ? "✅ Caching ON" : "⚠️ Caching OFF (<1024 tokens)";
        cacheBadge.className = j2.cacheEligible ? "badge badge-green" : "badge badge-warn";
      }
    } catch (e) {
      show("❌ Save failed: " + (e.message || e));
    }
  }

  if (safeGet("saveAllBtn")) safeGet("saveAllBtn").addEventListener("click", saveAll);

  if (safeGet("resetBtn")) safeGet("resetBtn").addEventListener("click", async () => {
    await fetch("/api/settings/runtime?sessionId=" + encodeURIComponent(sessionId), { method: "DELETE" });
    await fetch("/api/instructions?sessionId=" + encodeURIComponent(sessionId), { method: "DELETE" });
    location.reload();
  });

  if (safeGet("viewPromptBtn")) safeGet("viewPromptBtn").addEventListener("click", async () => {
    try {
      const r = await fetch("/api/prompt/effective?sessionId=" + encodeURIComponent(sessionId));
      show(await r.json(), safeGet("diagOut"));
    } catch (e) { show(String(e), safeGet("diagOut")); }
  });

  if (safeGet("testBrainBtn")) safeGet("testBrainBtn").addEventListener("click", async () => {
    const diag = safeGet("diagOut");
    show("Testing brain…", diag);
    try {
      await saveAll();
      const r = await fetch("/api/brain", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript: "Python అంటే ఏమిటి?", language_code: "te-IN", sessionId }),
      });
      const j = await r.json();
      show(r.ok ? "Brain OK:\n" + j.text : "Error: " + JSON.stringify(j), diag);
    } catch (e) { show(String(e), diag); }
  });

  if (safeGet("testTtsBtn")) safeGet("testTtsBtn").addEventListener("click", async () => {
    const st = safeGet("ttsTestStatus");
    if (st) { st.style.display = "block"; st.textContent = "Synthesizing…"; }
    try {
      const r = await fetch("/api/tts", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: "హాయ్! ఇది మీ test voice.",
          language_code: "te-IN", sessionId,
          speaker: safeGet("ttsSpeaker")?.value,
          model: safeGet("ttsModel")?.value,
        }),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        throw new Error(j.detail?.error?.message || r.statusText);
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = safeGet("testAudio");
      if (a) { a.src = url; a.style.display = "block"; await a.play(); }
      if (st) st.textContent = `✅ ${Math.round(blob.size)} bytes • speaker=${r.headers.get("x-speaker")}`;
    } catch (e) {
      if (st) st.textContent = "❌ " + (e.message || e);
    }
  });

  init();
})();
