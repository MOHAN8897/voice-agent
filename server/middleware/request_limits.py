"""Bound JSON bodies before FastAPI buffers them, including chunked requests."""
from __future__ import annotations
import asyncio
import time

from starlette.responses import JSONResponse


class JsonBodyLimitMiddleware:
    def __init__(self, app, max_bytes=32 * 1024 * 1024, timeout_seconds=30):
        self.app, self.max_bytes, self.timeout_seconds = app, max_bytes, timeout_seconds

    async def __call__(self, scope, receive, send):
        headers = dict(scope.get("headers", []))
        content_type = headers.get(b"content-type", b"").lower().split(b";", 1)[0].strip()
        if scope["type"] != "http" or not (content_type == b"application/json" or content_type.endswith(b"+json")):
            return await self.app(scope, receive, send)
        async def reject(status, message):
            await JSONResponse({"error": {"code": "request_limit", "message": message}}, status_code=status,
                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})(scope, receive, send)
        try:
            if int(headers.get(b"content-length", b"0")) > self.max_bytes:
                return await reject(413, "JSON request exceeds the 32 MB limit")
        except ValueError:
            return await reject(400, "Invalid Content-Length")
        messages, size = [], 0
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return await reject(408, "Request body timed out")
            try:
                message = await asyncio.wait_for(receive(), timeout=remaining)
            except asyncio.TimeoutError:
                return await reject(408, "Request body timed out")
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > self.max_bytes:
                return await reject(413, "JSON request exceeds the 32 MB limit")
            messages.append(message)
            if not message.get("more_body", False):
                break
        iterator = iter(messages)
        async def replay():
            try:
                return next(iterator)
            except StopIteration:
                return await receive()
        await self.app(scope, replay, send)
