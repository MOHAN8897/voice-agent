"""HTTP-only transport for operator scripts, with finite timeouts and no redirects."""
from contextlib import contextmanager
import io
import urllib.error

import httpx


class Response:
    def __init__(self, response):
        self._response = response
        self.status = response.status_code

    def read(self):
        return self._response.read()

    def __iter__(self):
        for line in self._response.iter_lines():
            yield (line + "\n").encode("utf-8")


@contextmanager
def safe_urlopen(request, timeout=30):
    url = httpx.URL(str(getattr(request, "full_url", request)))
    if url.scheme not in ("http", "https") or not url.host or url.username or url.password:
        raise ValueError("Operator requests require an HTTP(S) URL without embedded credentials")
    method = request.get_method() if hasattr(request, "get_method") else "GET"
    headers = dict(getattr(request, "headers", {}))
    content = getattr(request, "data", None)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            with client.stream(method, url, headers=headers, content=content) as response:
                if response.status_code >= 300:
                    raise urllib.error.HTTPError(str(url), response.status_code, response.reason_phrase,
                                                 response.headers, io.BytesIO(response.read()))
                yield Response(response)
    except httpx.RequestError as exc:
        raise urllib.error.URLError("HTTP request failed") from exc
