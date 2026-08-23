"""Streaming pipeline check v2 — scripts/stream_pipeline_check.py [port]

A) Brain SSE deltas -> accumulate to sentences/clauses (~80 chars or punctuation)
   -> push into warm WS /ws/tts -> flush -> streamed mp3 chunks.
B) Fallback path proof: same sentences via POST /api/tts/stream (HTTP binary).
"""
import asyncio
import base64
import json
import os
import re
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RESULTS = []
SENT_END = re.compile(r"[.!?\u0964;:\n]\s*$")


def record(name, ok, detail):
    RESULTS.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name:<46} {detail[:120]}")


class Acc:
    """SentenceAggregator - emit on punctuation or size threshold."""

    def __init__(self, max_len=80):
        self.buf = ""
        self.max_len = max_len

    def feed(self, delta):
        self.buf += delta
        out = None
        if SENT_END.search(self.buf) or len(self.buf) >= self.max_len:
            out, self.buf = self.buf, ""
        return out

    def flush(self):
        out, self.buf = self.buf, ""
        return out


async def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "8000"
    base = f"http://localhost:{port}"
    import websockets

    transcript = "హైదరాబాద్ గురించి సంక్షిప్తంగా చెప్పు."
    print("=" * 100)
    print("STREAMING PIPELINE CHECK v2 — sentence-aggregated Brain->TTS")
    print("=" * 100)

    # ---- A) WS path with accumulation ----
    ws = await websockets.connect(
        f"ws://localhost:{port}/ws/tts?model=bulbul:v3", max_size=None, open_timeout=10
    )
    await ws.send(json.dumps({"type": "config", "data": {
        "speaker": "shubh", "language_code": "te-IN", "pace": 1.0,
        "min_buffer_size": 50, "max_chunk_length": 200,
        "output_audio_codec": "mp3", "output_audio_bitrate": "128k"}}))

    acc = Acc(80)
    sent_msgs = 0
    delta_count = 0
    first_delta_at = None
    sse_err = None
    ws_dead = False
    t0 = time.perf_counter()

    async def drain_audio(ws_ref, first_at_box, stop_after_final=True, budget=45):
        chunks, nbytes, final = 0, 0, False
        t1 = time.perf_counter()
        while time.perf_counter() - t1 < budget:
            try:
                raw = await asyncio.wait_for(ws_ref.recv(), timeout=12)
            except asyncio.TimeoutError:
                break
            except Exception:
                break
            ev = json.loads(raw) if isinstance(raw, str) else {}
            etype = ev.get("type") or ev.get("event")
            data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
            b64 = data.get("audio")
            if b64:
                chunks += 1
                nbytes += len(base64.b64decode(b64))
                if first_at_box[0] is None:
                    first_at_box[0] = time.perf_counter() - t0
            elif data.get("event_type") == "final":
                final = True
                if stop_after_final:
                    break
            elif etype == "error":
                break
        return chunks, nbytes, final

    audio_box = [None]

    async def push_deltas_and_feed():
        nonlocal delta_count, first_delta_at, sse_err, ws_dead, sent_msgs
        async with httpx.AsyncClient(timeout=90) as c:
            async with c.stream(
                "POST", f"{base}/api/brain/stream",
                json={"transcript": transcript, "language_code": "te-IN",
                      "sessionId": "stream-check2", "responseStyle": "concise, conversational"},
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    sse_err = f"HTTP {resp.status_code}: {body[:150].decode(errors='ignore')}"
                    return
                buf = ""
                async for chunk in resp.aiter_text():
                    if ws_dead:
                        break
                    buf += chunk
                    while "\n\n" in buf:
                        frame, buf = buf.split("\n\n", 1)
                        if not frame.startswith("data:"):
                            continue
                        payload = frame[5:].strip()
                        if payload == "[DONE]":
                            continue
                        try:
                            obj = json.loads(payload)
                        except Exception:
                            continue
                        if obj.get("error"):
                            sse_err = obj["error"].get("message", "stream error")
                            return
                        d = obj.get("delta")
                        if d:
                            delta_count += 1
                            if first_delta_at is None:
                                first_delta_at = time.perf_counter() - t0
                            piece = acc.feed(d)
                            if piece and piece.strip():
                                try:
                                    await ws.send(json.dumps({"type": "text", "data": {"text": piece}}))
                                    sent_msgs += 1
                                except Exception:
                                    ws_dead = True
                                    return

    await push_deltas_and_feed()
    stream_s = time.perf_counter() - t0

    tail = acc.flush()
    if tail.strip() and not ws_dead:
        try:
            await ws.send(json.dumps({"type": "text", "data": {"text": tail}}))
            sent_msgs += 1
        except Exception:
            pass

    if sse_err is None and not ws_dead:
        try:
            await ws.send(json.dumps({"type": "flush"}))
        except Exception:
            pass

    if not ws_dead:
        c1, n1, f1 = await drain_audio(ws, audio_box)
        record("A) WS path: brain deltas→sentences→TTS",
               (sse_err is None) and c1 >= 1 and n1 > 1500,
               f"deltas={delta_count} sent={sent_msgs} chunks={c1} bytes={n1} final={'y' if f1 else 'n'} "
               f"firstΔ@{first_delta_at and round(first_delta_at,2)}s err={sse_err}")
    else:
        record("A) WS path: brain deltas→sentences→TTS", False, "socket closed mid-stream")
    try:
        await ws.close()
    except Exception:
        pass

    # ---- B) Per-sentence HTTP-stream fallback ----
    async def tts_stream_sentence(text):
        total = 0
        async with httpx.AsyncClient(timeout=40) as c:
            async with c.stream("POST", f"{base}/api/tts/stream",
                                json={"text": text, "language_code": "te-IN"}) as r:
                if r.status_code != 200:
                    return 0
                async for b in r.aiter_bytes():
                    total += len(b)
        return total

    sents = ["హైదరాబాద్ భారతదేశంలోని తెలంగాణ రాష్ట్రానికి రాజధాని.",
             "ఇది చారిత్రక నగరం, ప్రపంచ ప్రసిద్ధమైన చార్మినార్ ఇక్కడ ఉంది."]
    t2 = time.perf_counter()
    per_first = None
    okb, bytes_total = True, 0
    for s_ in sents:
        nb = await tts_stream_sentence(s_)
        if nb == 0:
            okb = False
        else:
            bytes_total += nb
            if per_first is None:
                per_first = time.perf_counter() - t2
    record("B) HTTP-stream per-sentence fallback", okb and bytes_total > 3000,
           f"first sentence audio in {per_first and round(per_first,2)}s • total {bytes_total}B")

    print("=" * 100)
    failed = [r for r in RESULTS if not r]
    print(f"TOTAL {len(RESULTS)} — {len(RESULTS)-len(failed)} PASS, {len(failed)} FAIL")
    sys.exit(1 if failed else 0)


asyncio.run(main())
