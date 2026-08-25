"""CD-016 — spoken_response streams before memory_update is applied."""
from __future__ import annotations

import json

from server.call.live_turn_schema import SpokenResponseExtractor
from server.agent.instruction_builder import build_live_input
from server.services.prompt_cache_key import compute_cache_key_versioned


def test_extractor_yields_spoken_before_memory_tail():
    extractor = SpokenResponseExtractor()
    prefix = extractor.feed('{"spoken_response": "')
    assert prefix == ""
    spoken = extractor.feed("నమస్కారం")
    assert spoken == "నమస్కారం"
    more = extractor.feed('", "memory_update": {"operations": [{"op": "set_fact", "key": "name", "value": "Ravi"}]}}')
    assert more == ""
    assert extractor.spoken_text == "నమస్కారం"
    update = extractor.parse_memory_update()
    assert update["operations"][0]["value"] == "Ravi"


def test_extractor_plain_text_passthrough():
    extractor = SpokenResponseExtractor()
    out = extractor.feed("hello there")
    assert out == "hello there"
    assert extractor.parse_memory_update() == {"operations": []}
    assert extractor.structured_parse_failed() is True


def test_extractor_valid_json_empty_ops_is_not_parse_failure():
    extractor = SpokenResponseExtractor()
    extractor.feed('{"spoken_response": "ok", "memory_update": {"operations": []}}')
    assert extractor.parse_memory_update() == {"operations": []}
    assert extractor.structured_parse_failed() is False


def test_extractor_truncated_json_is_parse_failure():
    extractor = SpokenResponseExtractor()
    extractor.feed('{"spoken_response": "ok", "memory_update":')
    assert extractor.structured_parse_failed() is True


def test_extractor_unescape():
    extractor = SpokenResponseExtractor()
    extractor.feed('{"spoken_response": "line\\nnext", "memory_update": {"operations": []}}')
    assert extractor.spoken_text == "line\nnext"


def test_projection_outside_cached_developer_block():
    msgs = build_live_input(
        compiled_brain_text="STABLE BRAIN",
        history=[],
        transcript="hi",
        enable_cache=True,
        memory_projection="name: Ravi",
        rolling_summary="Caller is Ravi",
    )
    assert msgs[0]["role"] == "developer"
    assert msgs[0]["content"][0]["text"] == "STABLE BRAIN"
    assert "prompt_cache_breakpoint" in msgs[0]["content"][0]
    joined = json.dumps(msgs[1:])
    assert "name: Ravi" in joined
    assert "[Rolling summary]" in joined
    assert "STABLE BRAIN" not in joined
    k1 = compute_cache_key_versioned("v1", 2000)
    k2 = compute_cache_key_versioned("v1", 2000)
    assert k1 == k2
