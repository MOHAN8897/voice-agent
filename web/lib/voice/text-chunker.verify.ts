/**
 * Manual verification helpers for StreamingTextChunker.
 * Run: npx tsx web/lib/voice/text-chunker.verify.ts
 */
import { StreamingTextChunker } from "./text-chunker";

function assert(cond: boolean, msg: string) {
  if (!cond) throw new Error(msg);
}

function testShortResponse() {
  const c = new StreamingTextChunker("t1");
  const mid = c.append("Yes, absolutely.");
  const end = c.flush();
  const chunks = [...mid, ...end];
  assert(chunks.length === 1, "short response should be one chunk");
  assert(chunks[0].text === "Yes, absolutely.", "full text preserved");
}

function testLongResponse() {
  const c = new StreamingTextChunker("t2");
  const s1 = "Hi Sai, thanks for calling HustleLabs.";
  const s2 = " I wanted to tell you about a property available in Gachibowli.";
  c.append(s1);
  let chunks = c.append(s2);
  if (chunks.length === 0) chunks = c.flush();
  const all = [...chunks, ...c.flush()];
  assert(all.length >= 1, "should produce chunks");
  const joined = all.map((x) => x.text).join(" ").replace(/\s+/g, " ").trim();
  assert(joined.includes("HustleLabs"), "sentence 1 present");
  assert(joined.includes("Gachibowli"), "sentence 2 present");
  assert(!all.some((x) => x.text === "Hi Sai"), "no tiny fragment");
}

function testOrdering() {
  const c = new StreamingTextChunker("t3");
  c.append("One. Two. Three.");
  const chunks = c.flush();
  assert(chunks.every((ch, i) => ch.sequenceNumber === i), "sequence order");
}

function testFirstSentenceBeforeDone() {
  const c = new StreamingTextChunker("t4");
  const mid = c.append("Hi Sai, thanks for calling HustleLabs. ");
  assert(mid.length >= 1, "first sentence should flush before the 140-char hold");
  assert(mid[0].text.includes("HustleLabs"), "first spoken sentence present");
}

testShortResponse();
testLongResponse();
testOrdering();
testFirstSentenceBeforeDone();
console.log("text-chunker.verify: ok");
