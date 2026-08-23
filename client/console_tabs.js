/**
 * console_tabs.js — single-page sidebar navigation (no global conflicts)
 */
(function () {
  const panelTitles = {
    agent: "Voice Agent",
    pipeline: "Voice Pipeline",
    brain: "AI Brain",
    prompt: "Prompting",
    crm: "CRM & Tools",
    advanced: "Advanced",
  };

  function el(id) {
    return document.getElementById(id);
  }

  function switchConsoleTab(panelId) {
    if (!panelTitles[panelId]) panelId = "agent";
    document.querySelectorAll(".console-tab").forEach((b) => {
      b.classList.toggle("active", b.dataset.panel === panelId);
    });
    document.querySelectorAll(".console-panel").forEach((p) => {
      p.classList.toggle("active", p.id === "panel-" + panelId);
    });
    const title = el("panelTitle");
    if (title) title.textContent = panelTitles[panelId];
    const isAgent = panelId === "agent";
    const savebar = el("consoleSavebar");
    const hintBar = el("consoleHintBar");
    const summary = el("runtimeSummary");
    if (savebar) savebar.style.display = isAgent ? "none" : "flex";
    if (hintBar) hintBar.style.display = isAgent ? "none" : "block";
    if (summary) summary.style.display = isAgent ? "none" : "block";
    if (history.replaceState) {
      history.replaceState(null, "", panelId === "agent" ? "/" : "/?tab=" + panelId);
    }
  }

  document.querySelectorAll(".console-tab").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      switchConsoleTab(btn.dataset.panel);
    });
  });

  const params = new URLSearchParams(location.search);
  const tab = params.get("tab") || (location.hash ? location.hash.slice(1) : "agent");
  switchConsoleTab(panelTitles[tab] ? tab : "agent");

  window.switchConsoleTab = switchConsoleTab;
})();
