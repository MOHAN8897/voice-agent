import httpx

from server.app import app


async def test_public_and_denied_api_responses_have_safe_headers():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://isolated.test") as client:
        for path in ("/api/campaigns", "/api/contacts/lists", "/not-an-existing-route"):
            response = await client.get(path)
            assert response.status_code in (401, 403, 404)
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["x-frame-options"] == "DENY"
            assert "no-store" in response.headers["cache-control"]
            assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


async def test_json_body_limit_handles_chunked_and_declared_sizes():
    from fastapi import FastAPI, Request
    from server.middleware.request_limits import JsonBodyLimitMiddleware
    isolated = FastAPI()
    isolated.add_middleware(JsonBodyLimitMiddleware, max_bytes=32)
    @isolated.post("/body")
    async def body(request: Request):
        return {"size": len(await request.body())}
    async def chunks():
        yield b"a" * 20
        yield b"b" * 20
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=isolated), base_url="http://isolated.test") as client:
        assert (await client.post("/body", content=chunks(), headers={"content-type": "application/json"})).status_code == 413
        assert (await client.post("/body", content=b"a" * 40, headers={"content-type": "application/json"})).status_code == 413
        assert (await client.post("/body", content=b"{}", headers={"content-type": "application/json"})).json()["size"] == 2


async def test_zap_boolean_payloads_do_not_bypass_auth_or_reach_sql():
    # Reproduce the eight SQLi heuristics from the isolated unauthenticated scan.
    # The test DB is deliberately unavailable; SQL cannot execute in this run.
    cases = [
        ("/api/auth/change-password", "newPassword", {"currentPassword": "isolated"}),
        ("/api/auth/delete-account", "confirm", {"password": "isolated"}),
        ("/api/auth/onboarding-survey", "companyName", {"fullName": "Audit"}),
        ("/api/auth/reset-password", "newPassword", {"token": "isolated-invalid"}),
        ("/api/auth/signup", "password", {"email": "audit@example.invalid", "fullName": "Audit", "orgName": "Audit"}),
        ("/api/campaigns/validate-variables", "contacts", {"agentId": "isolated-agent"}),
        ("/api/contacts/templates", "sourceHeaders", {"templateName": "Audit", "mapping": {"phone": "phone"}}),
        ("/api/dnc", "reason", {"phoneE164": "+12025550101"}),
    ]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://isolated.test") as client:
        for path, param, base in cases:
            responses = []
            for condition in ("AND", "OR"):
                value = f"John Doe' {condition} '1'='1' -- "
                response = await client.post(path, json={**base, param: [value] if param in ("contacts", "sourceHeaders") else value})
                assert response.status_code in (400, 401, 403, 503), path
                responses.append((response.status_code, response.json()))
            assert responses[0] == responses[1], path
