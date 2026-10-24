import { test, expect } from "@playwright/test";

test.use({ storageState: process.env.VOICE_CATALOG_AUTH_STATE || "e2e/.auth/user.json" });

const evidence = { sarvamModelAccess: true, sttVerified: true, ttsCatalogVerified: true, toolsVerified: true, capacityVerified: true, mediaFormatsVerified: true, credentialRefConfigured: true };
const voices = Array.from({ length: 60 }, (_, index) => ({ id: `voice-${index}`, providerVoiceId: `persona_${index}`, label: `Supplier ${index}`, languages: ["te-IN"], category: index % 2 ? "Conversational" : "Normal" }));

test("admin catalog scrolls full model inventory, filters styles and saves exact provider voice IDs", async ({ page }) => {
  let profile = { schemaVersion: 1, enabled: false, supportedLanguages: ["te-IN"], stt: { provider: "sarvam", model: "saaras:v3-realtime" },
    llm: { provider: "sarvam", modelId: "sarvam-105b-conversations", apiMode: "chat_completions_v1" }, evidence,
    engines: [{ id: "engine", label: "Speech", models: [{ id: "model", label: "Speech model", provider: "sarvam", model: "bulbul:v4-flash", apiMode: "websocket", voices }] }] };
  const writes: any[] = [];
  const gnani = [{ id: "g-1", providerVoiceId: "Shivani", label: "Shivani", languages: ["te-IN"], category: "Conversational" }];
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let data: any = { ok: true, items: [] };
    if (path.endsWith("/auth/dev-me")) data = { authenticated: true, subject: "catalog-test", csrf_token: "test-csrf" };
    if (path.endsWith("/stack/catalog")) data = { providers: [
      { id: "sarvam", label: "Sarvam", enabled: true, configured: true, models: { stt: [{ id: "saaras:v3-realtime" }], llm: [{ id: "sarvam-105b-conversations", api_mode: "chat_completions_v1" }], tts: [{ id: "bulbul:v4-flash", api_mode: "websocket", voices }] } },
      { id: "gnani", label: "Gnani", enabled: true, configured: true, models: { tts: [{ id: "timbre-v3.0", api_mode: "websocket", voices: gnani }] } },
    ] };
    if (path.endsWith("/voice-profiles")) data = { environment: "test", profiles: [{ tier: "low", profileRevision: 2, composedProfile: profile, readiness: { ready: true, enabled: false, blockers: [] }, retailRate: null }] };
    if (path.endsWith("/voice-profiles/low") && route.request().method() === "PUT") {
      const body = route.request().postDataJSON(); writes.push(body); profile = body.composedProfile;
    }
    await route.fulfill({ json: data });
  });
  await page.goto("/dev/stack");
  const region = page.getByRole("region", { name: "Available model voices", exact: true });
  await expect(region.getByText("Voice 60", { exact: true })).toBeAttached();
  expect(await region.evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true);
  await page.getByRole("combobox", { name: "Voice style", exact: true }).selectOption("Conversational");
  await expect(region.getByText("Voice 1", { exact: true })).toHaveCount(0);
  await expect(region.getByText("Voice 60", { exact: true })).toBeAttached();
  await page.getByRole("combobox", { name: "TTS provider", exact: true }).selectOption("gnani");
  await expect(region.getByText("Voice 1", { exact: true })).toBeVisible();
  await expect(region.getByText("Voice 60", { exact: true })).toHaveCount(0);
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].composedProfile.engines[0].models[0]).toMatchObject({ provider: "gnani", model: "timbre-v3.0", voices: [{ providerVoiceId: "Shivani", languages: ["te-IN"] }] });
});
