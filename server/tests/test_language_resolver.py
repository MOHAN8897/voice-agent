from server.agent.language_resolver import is_code_mixed, resolve_language


def test_code_mixed_detection():
    assert is_code_mixed("నా laptop slow గా ఉంది") is True
    assert is_code_mixed("హైదరాబాద్ గురించి చెప్పు") is False
    assert is_code_mixed("hello world") is False

def test_resolve_always_te_in_phase1():
    ctx = resolve_language("te-IN", "నా phone లో notifications రావడం లేదు")
    assert ctx["responseLanguage"] == "te-IN"
    assert ctx["isCodeMixed"] is True

def test_resolve_pure_telugu():
    ctx = resolve_language("te-IN", "హైదరాబాద్ గురించి చెప్పు")
    assert ctx["responseLanguage"] == "te-IN"
    assert ctx["isCodeMixed"] is False
