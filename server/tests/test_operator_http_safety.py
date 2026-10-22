import urllib.error
import urllib.request

import httpx
import pytest

from scripts.http_transport import safe_urlopen


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://localhost/file", "http://user:pass@example.test", "data:text/plain,unsafe"])
def test_rejects_unsafe_schemes_and_credentials(url):
    with pytest.raises(ValueError):
        with safe_urlopen(url):
            pytest.fail("transport accepted unsafe URL")


def test_maintains_json_stream_and_errors(monkeypatch):
    client_class = httpx.Client
    requests = []
    def handler(request):
        requests.append(request)
        if request.url.path == "/redirect":
            return httpx.Response(302, headers={"Location": "file:///etc/passwd"})
        return httpx.Response(200, content=b"data: one\ndata: two\n")
    monkeypatch.setattr(httpx, "Client", lambda **kw: client_class(transport=httpx.MockTransport(handler), **kw))
    with safe_urlopen(urllib.request.Request("https://example.test/stream", method="POST", data=b"{}"), timeout=3) as response:
        assert response.status == 200
        assert list(response) == [b"data: one\n", b"data: two\n"]
    with pytest.raises(urllib.error.HTTPError) as error:
        with safe_urlopen("https://example.test/redirect"):
            pytest.fail("redirect followed")
    assert error.value.code == 302 and len(requests) == 2
