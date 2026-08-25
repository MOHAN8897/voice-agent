/**
 * conversation_store.js — persist turns as structured JSON + export TXT / WAV
 */
(function () {
  function sid() {
    return localStorage.getItem("telugu_session_id") || "default";
  }

  function key() {
    return "telugu_conversation_" + sid();
  }

  function load() {
    try {
      const raw = localStorage.getItem(key());
      if (!raw) return { sessionId: sid(), turns: [] };
      const data = JSON.parse(raw);
      return { sessionId: sid(), turns: Array.isArray(data.turns) ? data.turns : [] };
    } catch {
      return { sessionId: sid(), turns: [] };
    }
  }

  function save(data) {
    data.updatedAt = new Date().toISOString();
    data.sessionId = sid();
    localStorage.setItem(key(), JSON.stringify(data));
  }

  function appendTurn({ user, assistant, audioBase64, mime, speaker }) {
    const data = load();
    if (!user && !assistant) return data;
    data.turns.push({
      id: "turn_" + String(data.turns.length + 1).padStart(3, "0"),
      timestamp: new Date().toISOString(),
      user: user || "",
      assistant: assistant || "",
      audio: audioBase64
        ? { base64: audioBase64, mime: mime || "audio/wav", speaker: speaker || null }
        : null,
    });
    save(data);
    return data;
  }

  function clear() {
    save({ sessionId: sid(), turns: [] });
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 500);
  }

  function exportTxt() {
    const data = load();
    const lines = data.turns.map((t) => {
      const ts = t.timestamp || "";
      return `[${ts}]\nUSER: ${t.user}\nAGENT: ${t.assistant}\n`;
    });
    const body = `Telugu Voice Agent — Conversation Export\nSession: ${data.sessionId}\nTurns: ${data.turns.length}\n\n` + lines.join("\n---\n\n");
    downloadBlob(new Blob([body], { type: "text/plain;charset=utf-8" }), `conversation_${sid().slice(0, 8)}.txt`);
  }

  function exportJson() {
    const data = load();
    downloadBlob(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }), `conversation_${sid().slice(0, 8)}.json`);
  }

  function b64ToBlob(b64, mime) {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: mime || "audio/wav" });
  }

  function exportAllWav() {
    const data = load();
    const withAudio = data.turns.filter((t) => t.audio && t.audio.base64);
    if (!withAudio.length) return 0;
    withAudio.forEach((t, i) => {
      const ext = (t.audio.mime || "").includes("mpeg") ? "mp3" : "wav";
      downloadBlob(b64ToBlob(t.audio.base64, t.audio.mime), `${t.id || "turn_" + (i + 1)}.${ext}`);
    });
    return withAudio.length;
  }

  function exportLastWav() {
    const data = load();
    for (let i = data.turns.length - 1; i >= 0; i--) {
      const t = data.turns[i];
      if (t.audio && t.audio.base64) {
        const ext = (t.audio.mime || "").includes("mpeg") ? "mp3" : "wav";
        downloadBlob(b64ToBlob(t.audio.base64, t.audio.mime), `${t.id || "last"}.${ext}`);
        return true;
      }
    }
    return false;
  }

  window.ConversationStore = {
    load,
    appendTurn,
    clear,
    exportTxt,
    exportJson,
    exportAllWav,
    exportLastWav,
    turnCount: () => load().turns.length,
    setCallId(callId) {
      const data = load();
      data.callId = callId || null;
      save(data);
    },
    async refreshFromServer() {
      try {
        const r = await fetch("/api/calls?limit=20");
        if (!r.ok) return null;
        return await r.json();
      } catch {
        return null;
      }
    },
  };
})();
