/** Tests for transcript-gate — run: npx tsx web/lib/voice/transcript-gate.verify.ts */
import { effectiveWordCount, isSubstantiveTranscript, looksIncompleteReply } from "@/lib/voice/transcript-gate";

function assert(cond: boolean, msg: string) {
  if (!cond) throw new Error(msg);
}

assert(isSubstantiveTranscript("Hello there"), "two words ok");
assert(!isSubstantiveTranscript("and plot", { fromSpeechQueue: true }), "fragment blocked");
assert(isSubstantiveTranscript("నాకు ప్లాట్ కావాలి"), "telugu substantive");
assert(effectiveWordCount("నాకు ప్లాట్ కావాలి") >= 2, "telugu word estimate");
assert(looksIncompleteReply("I can't give"), "incomplete english");
assert(!looksIncompleteReply("Plot prices start at forty lakhs."), "complete sentence");

console.log("transcript-gate.verify: OK");
