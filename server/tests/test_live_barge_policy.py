"""Barge-in policy tests — mirrors client/live-guards.js."""

BARGE_DEBOUNCE_MS = 800
THINK_CANCEL_MIN_MS = 350
THINK_CANCEL_MIN_WORDS = 2
SPEAK_BARGE_MIN_WORDS = 3
BARGE_HOLD_MS = 200


def should_debounce_barge_in(state: dict, now: float) -> bool:
    return (
        state.get("bargeHandledTurn") == state.get("turnN")
        and now - state.get("lastBargeInAt", 0) < BARGE_DEBOUNCE_MS
    )


def should_think_cancel(state: dict) -> bool:
    return (
        state.get("busy")
        and state.get("brainStreaming")
        and not state.get("agentSpeaking")
        and state.get("elapsedMs", 0) > THINK_CANCEL_MIN_MS
        and state.get("words", 0) >= THINK_CANCEL_MIN_WORDS
    )


def should_barge_while_speaking(state: dict, now: float) -> bool:
    if not state.get("agentSpeaking"):
        return False
    min_words = state.get("minWords", SPEAK_BARGE_MIN_WORDS)
    require_vad = state.get("requireVad", True)
    if state.get("words", 0) < min_words:
        return False
    if require_vad and not state.get("sawVadStart"):
        return False
    hold_ms = state.get("holdMs", BARGE_HOLD_MS)
    vad_started_at = state.get("vadStartedAt") or 0
    if vad_started_at and now - vad_started_at < hold_ms:
        return False
    return now > state.get("bargeCooldownUntil", 0)


def should_route_final_immediately(state: dict) -> bool:
    """Barge-in finals must never be queued behind the interrupted turn."""
    return bool(state.get("bargeActive") or state.get("awaitingUserAfterBarge"))


class TestThinkCancel:
    def test_fires_during_brain_streaming(self):
        assert should_think_cancel({
            "busy": True,
            "brainStreaming": True,
            "agentSpeaking": False,
            "elapsedMs": 400,
            "words": 2,
        })

    def test_blocked_during_tts_wait(self):
        """After brain completes, busy but not brainStreaming — no think-cancel."""
        assert not should_think_cancel({
            "busy": True,
            "brainStreaming": False,
            "agentSpeaking": False,
            "elapsedMs": 5000,
            "words": 5,
        })

    def test_blocked_while_agent_speaking(self):
        assert not should_think_cancel({
            "busy": True,
            "brainStreaming": True,
            "agentSpeaking": True,
            "elapsedMs": 400,
            "words": 2,
        })


class TestBargeDebounce:
    def test_debounces_same_turn(self):
        state = {"bargeHandledTurn": 1, "turnN": 1, "lastBargeInAt": 1000}
        assert should_debounce_barge_in(state, 1500)

    def test_allows_after_cooldown(self):
        state = {"bargeHandledTurn": 1, "turnN": 1, "lastBargeInAt": 1000}
        assert not should_debounce_barge_in(state, 2000)


class TestSpeakingBarge:
    def test_requires_vad_and_min_words(self):
        assert should_barge_while_speaking(
            {"agentSpeaking": True, "words": 3, "sawVadStart": True, "bargeCooldownUntil": 0},
            now=100,
        )

    def test_blocks_echo_partials_without_vad(self):
        """TTS echo may produce partials — must not barge without vad.speech_start."""
        assert not should_barge_while_speaking(
            {"agentSpeaking": True, "words": 5, "sawVadStart": False, "bargeCooldownUntil": 0},
            now=100,
        )

    def test_blocks_until_cooldown(self):
        assert not should_barge_while_speaking(
            {"agentSpeaking": True, "words": 3, "sawVadStart": True, "bargeCooldownUntil": 500},
            now=100,
        )

    def test_blocks_until_hold_elapses(self):
        assert not should_barge_while_speaking(
            {
                "agentSpeaking": True,
                "words": 3,
                "sawVadStart": True,
                "vadStartedAt": 90,
                "bargeCooldownUntil": 0,
            },
            now=100,
        )

    def test_allows_after_hold(self):
        assert should_barge_while_speaking(
            {
                "agentSpeaking": True,
                "words": 3,
                "sawVadStart": True,
                "vadStartedAt": 1,
                "bargeCooldownUntil": 0,
            },
            now=250,
        )

    def test_respects_custom_min_words(self):
        assert not should_barge_while_speaking(
            {"agentSpeaking": True, "words": 2, "sawVadStart": True, "minWords": 3, "bargeCooldownUntil": 0},
            now=100,
        )


class TestBargeFinalRouting:
    def test_routes_immediately_after_barge(self):
        assert should_route_final_immediately({"bargeActive": True, "busy": True})

    def test_normal_busy_queues(self):
        assert not should_route_final_immediately({"bargeActive": False, "awaitingUserAfterBarge": False, "busy": True})
