from server.agent.conversation_manager import ConversationManager


def test_history_and_trim():
    cm = ConversationManager(max_messages=4)
    sid = "test-sid"
    cm.add_turn(sid, "నా పేరు Sai.", "Nice to meet you Sai!")
    cm.add_turn(sid, "నా పేరు ఏమిటి?", "మీ పేరు Sai.")
    history = cm.get_history(sid)
    # Should have 4 messages (2 turns)
    assert len(history) == 4
    assert history[-1]["content"] == "మీ పేరు Sai."
    # Add one more turn -> should trim to 4
    cm.add_turn(sid, "hello", "hi")
    assert len(cm.get_history(sid)) == 4
    # Oldest should be evicted
    assert cm.get_history(sid)[0]["content"] == "నా పేరు ఏమిటి?"

def test_clear():
    cm = ConversationManager(max_messages=10)
    cm.add_turn("s1", "hi", "hello")
    cm.clear("s1")
    assert cm.get_history("s1") == []
