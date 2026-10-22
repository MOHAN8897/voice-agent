import { test, expect } from "@playwright/test";

test("PSTN diagnostics show live stages, purge the selected call, and surface lost connectivity", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/dev/telephony/status", route => route.fulfill({ json: {
    active_provider: "telnyx",
    providers: [{ id: "telnyx", enabled: true, ready: true, configured: true }],
  } }));
  await page.route("**/api/dev/telephony/calls", route => route.fulfill({ json: { calls: [] } }));
  let offline = false;
  let purged = "";
  await page.route("**/api/dev/telephony/media-flow**", route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/purge")) {
      purged = url.searchParams.get("call_id") || "";
      return route.fulfill({ json: { ok: true, detail: "Playback stopped" } });
    }
    if (offline) return route.fulfill({ status: 503, json: { error: "offline" } });
    return route.fulfill({ json: { flow: {
      active: true, external_id: "pstn-smoke-control", call_id: "pstn-smoke-call", started_at: 100,
      diagnostics: { direction: "inbound", agent_id: "smoke-agent", phase: "speaking", stt: "ready", realtime: "ready", model: "gpt-realtime-2.1-mini", turn_id: "turn-2", generation_id: "generation-2" },
      configured: { codec: "L16", sample_rate: 16000, channels: 1 },
      negotiated: { codec: "L16", sample_rate: 16000, channels: 1 },
      metrics: { inbound_frames: 50, outbound_sent_frames: 25, queue_size: 3 },
      events: [
        { seq: 1, timestamp: 100.1, stage: "stt_final", direction: "inbound", detail: "I need a plot near Shamshabad" },
        { seq: 2, timestamp: 100.4, stage: "llm_first_token", direction: "outbound", detail: "Latest turn response" },
      ],
    } } });
  });
  const agents = await page.request.get("/api/agents");
  const agentId = (await agents.json()).agents[0].agent_id;
  await page.goto(`/dev/test-studio/${agentId}`);
  await page.getByTestId("test-mode-pstn").click();
  await expect(page.getByText("Live call media flow", { exact: true })).toBeVisible();
  await expect(page.getByText("Streaming STT", { exact: true })).toBeVisible();
  await expect(page.getByText("turn-2 / generation-2", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Purge playback" }).click();
  await expect.poll(() => purged).toBe("pstn-smoke-control");
  await expect(page.getByText("Playback stopped", { exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/pstn-diagnostics-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByText("Live call media flow", { exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/pstn-diagnostics-mobile.png", fullPage: true });
  offline = true;
  await expect(page.getByRole("alert").filter({ hasText: "Diagnostics unavailable" })).toBeVisible();
  expect(errors).toEqual([]);
});
