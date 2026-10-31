import { expect, test } from "@playwright/test";
import { buildWsTtsConfig } from "../lib/voice/tts-config";

for (const model of ["bulbul:v2", "bulbul:v3", "bulbul:v4-flash"]) {
  test(`${model} sends only its accepted delivery controls`, () => {
    const result = buildWsTtsConfig({ model, language_code: "te-IN", pace: 1.15,
      temperature: 0.45, pitch: 0, loudness: 1.2 });
    expect(result.pace).toBe(1.15);
    if (model === "bulbul:v2") {
      expect(result).not.toHaveProperty("temperature");
      expect(result.pitch).toBe(0);
      expect(result.volume).toBe(1.2);
    } else {
      expect(result.temperature).toBe(0.45);
      expect(result).not.toHaveProperty("pitch");
      expect(result).not.toHaveProperty("volume");
    }
  });
}

test("v2 maps universal volume to the wire field while v4 drops it", () => {
  expect(buildWsTtsConfig({ model: "bulbul:v2", language_code: "te-IN",
    volume: 0.1, loudness: 1.7 }).volume).toBe(0.1);
  const v4 = buildWsTtsConfig({ model: "bulbul:v4-flash", language_code: "te-IN",
    volume: 0.1, loudness: 1.7 });
  expect(v4).not.toHaveProperty("volume");
  expect(v4).not.toHaveProperty("loudness");
});

test("Cartesia browser transport preserves speed emotion and volume", () => {
  const result = buildWsTtsConfig({ provider: "cartesia", model: "sonic-3.5",
    language_code: "en-IN", pace: 0.8, speed: 1.2, emotion: "happy", volume: 1.1,
    temperature: 0.7, pitch: 0.2 });
  expect(result).toMatchObject({ pace: 1.2, emotion: "happy", volume: 1.1 });
  expect(result).not.toHaveProperty("temperature");
  expect(result).not.toHaveProperty("pitch");
});
