/**
 * calls_view.js — server-authoritative calls list (localStorage is cache only)
 */
(function () {
  function el(id) {
    return document.getElementById(id);
  }

  function fmt(ts) {
    if (!ts) return "—";
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return String(ts);
    }
  }

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  async function loadList() {
    const list = el("callsList");
    const detail = el("callDetail");
    if (!list) return;
    list.textContent = "Loading…";
    try {
      const r = await fetch("/api/calls?limit=30");
      const j = await r.json();
      const calls = j.calls || [];
      if (!calls.length) {
        list.innerHTML = "<p class='hint'>No server calls yet. Start a live session to create one.</p>";
        return;
      }
      list.innerHTML = "";
      calls.forEach((c) => {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "calls-row";
        const disp = c.disposition ? " · " + c.disposition : "";
        row.innerHTML =
          "<span class='mono'>" +
          (c.call_id || "").slice(0, 8) +
          "</span> · " +
          (c.channel || "browser") +
          " · " +
          (c.finalization_status || c.status || "active") +
          esc(disp) +
          "<br><span class='hint'>" +
          fmt(c.started_at) +
          "</span>";
        row.addEventListener("click", () => showDetail(c.call_id, detail));
        list.appendChild(row);
      });
    } catch (e) {
      list.textContent = "Could not load calls.";
    }
  }

  function tabBar(active) {
    return (
      "<div class='call-tabs'>" +
      ["transcript", "memory", "outcome"]
        .map((name) => {
          const label = name[0].toUpperCase() + name.slice(1);
          return (
            "<button type='button' class='call-tab" +
            (active === name ? " active" : "") +
            "' data-tab='" +
            name +
            "'>" +
            label +
            "</button>"
          );
        })
        .join("") +
      "</div>"
    );
  }

  function factsBlock(memory) {
    const facts = memory.facts || {};
    const prefs = memory.preferences || {};
    const factLines = Object.keys(facts).length
      ? Object.entries(facts)
          .map(([k, v]) => k + ": " + v)
          .join("\n")
      : "(none)";
    const prefLines = Object.keys(prefs).length
      ? Object.entries(prefs)
          .map(([k, v]) => k + ": " + v)
          .join("\n")
      : "(none)";
    return (
      "<div class='label'>Facts</div><pre class='status-out'>" +
      esc(factLines) +
      "</pre>" +
      "<div class='label'>Preferences</div><pre class='status-out'>" +
      esc(prefLines) +
      "</pre>" +
      "<div class='label'>Context</div><pre class='status-out'>" +
      esc(memory.important_context || "(empty)") +
      "</pre>" +
      "<div class='label'>Summary</div><pre class='status-out'>" +
      esc(memory.summary || "(empty)") +
      "</pre>"
    );
  }

  async function showDetail(callId, detail) {
    if (!detail) return;
    detail.style.display = "";
    detail.dataset.callId = callId;
    detail.dataset.tab = "transcript";
    detail.textContent = "Loading " + callId + "…";
    await renderDetail(callId, detail, "transcript");
  }

  async function renderDetail(callId, detail, tab) {
    try {
      const [metaR, txR, memR, outR] = await Promise.all([
        fetch("/api/call/" + callId),
        fetch("/api/call/" + callId + "/transcript"),
        fetch("/api/call/" + callId + "/memory"),
        fetch("/api/call/" + callId + "/outcome"),
      ]);
      const meta = await metaR.json();
      const tx = await txR.json();
      const mem = memR.ok ? await memR.json() : { memory: {} };
      const outBody = await outR.json();
      const lines = (tx.lines || [])
        .map((l) => (l.role || "") + ": " + (l.text || ""))
        .join("\n");
      const outcome = outBody.outcome;
      let body = "";
      if (tab === "memory") {
        const projR = await fetch("/api/call/" + callId + "/memory/projection");
        const proj = projR.ok ? await projR.json() : {};
        body =
          factsBlock(mem.memory || {}) +
          "<div class='label'>Live projection (debug)</div><pre class='status-out'>" +
          esc(proj.projection || "(empty)") +
          "</pre>";
      } else if (tab === "outcome") {
        if (!outcome) {
          body = "<p class='hint'>Outcome pending or not generated yet.</p>";
        } else {
          body =
            "<p><span class='call-disposition'>" +
            esc(outcome.disposition || "no_outcome") +
            "</span> · confidence " +
            (outcome.disposition_confidence != null ? outcome.disposition_confidence : "—") +
            "</p>" +
            "<div class='label'>English summary</div><pre class='status-out'>" +
            esc(outcome.summary_en || "(empty)") +
            "</pre>" +
            "<div class='label'>Telugu summary</div><pre class='status-out'>" +
            esc(outcome.summary_te || "(empty)") +
            "</pre>" +
            "<div class='label'>Extracted fields</div><pre class='status-out'>" +
            esc(JSON.stringify(outcome.extracted_fields || {}, null, 2)) +
            "</pre>" +
            "<div class='label'>Next action</div><p class='hint'>" +
            esc(outcome.next_action || "—") +
            "</p>";
        }
      } else {
        body =
          "<pre class='status-out'>" +
          esc(lines || "(empty transcript)") +
          "</pre>" +
          "<a class='btn btn-sm' href='/api/call/" +
          callId +
          "/audio/mix'>Download mix.wav</a>";
      }
      detail.innerHTML =
        "<div class='label'>Call " +
        callId.slice(0, 8) +
        "</div>" +
        "<p class='hint'>status " +
        esc(meta.finalization_status || (meta.finalization && meta.finalization.status) || "—") +
        " · brain " +
        esc(meta.compiled_brain_version || "—") +
        " · stack " +
        esc(meta.combination_id || "—") +
        "</p>" +
        tabBar(tab) +
        "<div class='call-tab-body'>" +
        body +
        "</div>";
      detail.querySelectorAll(".call-tab").forEach((btn) => {
        btn.addEventListener("click", () => {
          renderDetail(callId, detail, btn.getAttribute("data-tab"));
        });
      });
    } catch {
      detail.textContent = "Failed to load call detail.";
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const refreshBtn = el("callsRefreshBtn");
    if (refreshBtn) refreshBtn.addEventListener("click", loadList);
  });

  window.CallsView = { refresh: loadList };
})();
