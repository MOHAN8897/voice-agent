/**
 * Voice guard verification — run: npx tsx web/lib/voice/voice-guards.verify.ts
 */
import { isLikelyEcho, isLikelyEchoPartial } from "@/lib/echo-guard";
import { micGateConfig, rmsAllowsSpeakBarge, shouldSendMicToStt } from "@/lib/voice/mic-gate";
import { labelLooksLikeHeadphones, headphonesFromStream } from "@/lib/voice/headphone-detect";
import { mobileModeFromPreset, resolveVoiceAudioProfile } from "@/lib/voice/mobile-audio";
import { shouldThinkCancel } from "@/lib/live-guards";

function assert(cond: boolean, msg: string) {
  if (!cond) throw new Error(msg);
}

function testPartialEcho() {
  const agent = "Hello there how can I help you today";
  assert(isLikelyEchoPartial("how can I help", agent), "partial overlap");
  assert(!isLikelyEchoPartial("totally unrelated phrase", agent), "no overlap");
}

function testMobileProfile() {
  const handset = resolveVoiceAudioProfile({ mobileMode: "handset" });
  const speaker = resolveVoiceAudioProfile({ mobileMode: "speakerphone" });
  assert(handset.mobileMode === "handset", "handset mode");
  assert(speaker.mobileMode === "speakerphone", "speakerphone mode");
  assert(speaker.playbackTailMs > handset.playbackTailMs, "speakerphone longer tail");
  assert(speaker.bargeMinWordsBonus > handset.bargeMinWordsBonus, "speakerphone stricter barge");
  assert(mobileModeFromPreset("speakerphone") === "speakerphone", "preset map");
  assert(mobileModeFromPreset("mobile_handset") === "handset", "handset preset");
  const hp = resolveVoiceAudioProfile({ headphones: true });
  assert(hp.headphones, "headphones flag");
}

function testRmsBargeGate() {
  const cfg = micGateConfig(resolveVoiceAudioProfile({ headphones: false }));
  const floor = cfg.rmsSpeakingThreshold * cfg.speakingRmsMultiplier;
  assert(!rmsAllowsSpeakBarge(floor * 0.5, cfg), "low rms blocked");
  assert(rmsAllowsSpeakBarge(floor * 1.1, cfg), "loud rms allowed");
}

function testMicHalfDuplex() {
  const cfg = micGateConfig(resolveVoiceAudioProfile({ headphones: false }));
  const state = {
    agentSpeaking: true,
    brainStreaming: false,
    awaitingUserAfterBarge: false,
    speakCooldownUntil: 0,
    speakStartedAt: Date.now() - 5000,
  };
  assert(!shouldSendMicToStt(state, Date.now(), 0.01, cfg), "quiet mic muted during TTS");
  assert(shouldSendMicToStt(state, Date.now(), 0.05, cfg), "loud mic passes during TTS");
}

function testThinkCancel() {
  assert(
    shouldThinkCancel(
      {
        bargeHandledTurn: 0,
        lastBargeInAt: 0,
        busy: true,
        brainStreaming: true,
        agentSpeaking: false,
        elapsedMs: 400,
        words: 3,
        sawVadStart: false,
        bargeCooldownUntil: 0,
        turnN: 1,
      },
      2
    ),
    "think cancel after min ms + words"
  );
}

function testHeadphoneLabels() {
  assert(labelLooksLikeHeadphones("AirPods Pro"), "airpods");
  assert(!labelLooksLikeHeadphones("MacBook Pro Microphone"), "built-in mic");
}

function testHeadphonesFromStream() {
  const stream = {
    getAudioTracks: () => [{ label: "Bluetooth Headset" }],
  } as MediaStream;
  assert(headphonesFromStream(stream), "stream label");
}

function main() {
  testPartialEcho();
  testMobileProfile();
  testRmsBargeGate();
  testMicHalfDuplex();
  testThinkCancel();
  testHeadphoneLabels();
  testHeadphonesFromStream();
  console.log("voice-guards.verify: OK");
}

main();
