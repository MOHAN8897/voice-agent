from server.utils.token_usage import normalize_usage


class _Details:
    cached_tokens = 1200
    cache_write_tokens = 0


class _Usage:
    input_tokens = 1500
    output_tokens = 60
    total_tokens = 1560
    input_tokens_details = _Details()


def test_normalize_usage_object():
    u = normalize_usage(_Usage())
    assert u["input_tokens"] == 1500
    assert u["output_tokens"] == 60
    assert u["cached_tokens"] == 1200
    assert u["cache_write_tokens"] == 0


def test_normalize_usage_dict():
    u = normalize_usage({
        "input_tokens": 100,
        "output_tokens": 20,
        "total_tokens": 120,
        "input_tokens_details": {"cached_tokens": 80, "cache_write_tokens": 10},
    })
    assert u["cached_tokens"] == 80
    assert u["cache_write_tokens"] == 10
