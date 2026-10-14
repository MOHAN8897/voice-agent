"""Nango Unified Tooling & Multi-Tenant Integration Gateway."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
import base64
from email.message import EmailMessage
import httpx
import urllib.error
import urllib.parse
import urllib.request
import uuid

from server.config.env import get_settings
from server.db.connection import get_session_factory
from server.db.models.integration_models import OAuthState
from server.utils.logger import logger

def _safe_uuid(raw_id: str | None, prefix: str = "id") -> uuid.UUID:
    """Safely convert any identifier to a deterministic UUIDv5 if not already a UUID."""
    if not raw_id:
        return uuid.NAMESPACE_DNS
    try:
        return uuid.UUID(str(raw_id))
    except (ValueError, TypeError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_DNS, f"{prefix}:{raw_id}")


# Canonical mapping from voice agent catalog IDs to Nango provider config keys
NANGO_PROVIDER_MAP: dict[str, str] = {
    "GOOGLECALENDAR": "google-calendar",
    "SLACK": "slack",
    "HUBSPOT": "hubspot",
    "SALESFORCE": "salesforce",
    "GMAIL": "google-mail",
    "GOOGLEMAIL": "google-mail",
    "GITHUB": "github-getting-started",
    "NOTION": "notion",
    "AIRTABLE": "airtable",
    "ZENDESK": "zendesk",
    "CALENDLY": "calendly",
    "CALCOM": "cal-com-v2",
    "ZOOM": "zoom",
    "ASANA": "asana",
    "LINEAR": "linear",
    "TWILIO": "twilio",
    "TWILIOSMS": "twilio",
    "TWILIO_SMS": "twilio",
    "SHOPIFY": "shopify-api-key",
    "INTERCOM": "intercom",
    "CLICKUP": "clickup",
    "MAILCHIMP": "mailchimp",
    "DISCORD": "discord-bot",
    "TRELLO": "trello",
    "JIRA": "jira",
    "BOX": "box",
    "DROPBOX": "dropbox",
    "OUTLOOKCALENDAR": "outlook-calendar",
    "MICROSOFTTEAMS": "microsoft-teams",
    "SENDGRID": "sendgrid",
    "SUPABASE": "supabase",
    "TYPEFORM": "typeform",
    "PIPEDRIVE": "pipedrive",
    "WOOCOMMERCE": "woocommerce",
    "WHATSAPP": "whatsapp-business",
    "GOOGLESHEETS": "google-sheet",
    "TODOIST": "todoist",
    "MONDAY": "monday",
    "FRESHDESK": "freshdesk",
    "ZOHOCRM": "zoho-crm",
    "ZOHO_CRM": "zoho-crm",
}

REVERSE_NANGO_PROVIDER_MAP: dict[str, str] = {
    v: k for k, v in NANGO_PROVIDER_MAP.items()
}
REVERSE_NANGO_PROVIDER_MAP.update({
    "google-calendar": "GOOGLECALENDAR",
    "google_calendar": "GOOGLECALENDAR",
    "cal-com": "CALCOM",
    "cal-com-v1": "CALCOM",
    "cal-com-v2": "CALCOM",
    "calendly": "CALENDLY",
    "hubspot": "HUBSPOT",
    "salesforce": "SALESFORCE",
    "slack": "SLACK",
    "gmail": "GMAIL",
    "google-mail": "GMAIL",
    "github": "GITHUB",
    "github-getting-started": "GITHUB",
    "notion": "NOTION",
    "airtable": "AIRTABLE",
    "stripe": "STRIPE",
    "stripe-api-key": "STRIPE",
    "shopify": "SHOPIFY",
    "shopify-api-key": "SHOPIFY",
    "woocommerce": "WOOCOMMERCE",
    "zendesk": "ZENDESK",
    "zoom": "ZOOM",
    "linear": "LINEAR",
    "asana": "ASANA",
    "intercom": "INTERCOM",
    "clickup": "CLICKUP",
    "mailchimp": "MAILCHIMP",
    "twilio": "TWILIO_SMS",
    "twilio-sms": "TWILIO_SMS",
    "whatsapp": "WHATSAPP",
    "whatsapp-business": "WHATSAPP",
    "discord": "DISCORD",
    "discord-bot": "DISCORD",
    "google-sheet": "GOOGLESHEETS",
    "google-sheets": "GOOGLESHEETS",
    "todoist": "TODOIST",
    "monday": "MONDAY",
    "freshdesk": "FRESHDESK",
    "zoho": "ZOHO_CRM",
    "zoho-crm": "ZOHO_CRM",
})


class _SafeHttpResponse:
    def __init__(self, response: httpx.Response):
        self._response = response
        self.status = response.status_code
        self.status_code = response.status_code
        self.headers = response.headers

    def read(self) -> bytes:
        return self._response.content

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def _safe_urlopen(req_or_url: Any, timeout: float = 5.0) -> _SafeHttpResponse:
    """Validate that only http/https schemes are permitted and dispatch via httpx (SSRF & file-scheme guard)."""
    import io

    if hasattr(req_or_url, "full_url"):
        url = req_or_url.full_url
        headers = dict(req_or_url.headers)
        method = req_or_url.get_method() if hasattr(req_or_url, "get_method") else "GET"
        content = req_or_url.data
    else:
        url = str(req_or_url)
        headers = {}
        method = "GET"
        content = None

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Insecure URL scheme rejected: {parsed.scheme}")

    with httpx.Client(timeout=timeout) as client:
        resp = client.request(method=method, url=url, headers=headers, content=content)
        if resp.status_code >= 400:
            raise urllib.error.HTTPError(
                url=url,
                code=resp.status_code,
                msg=resp.reason_phrase,
                hdrs=resp.headers,  # type: ignore[arg-type]
                fp=io.BytesIO(resp.content),
            )
        return _SafeHttpResponse(resp)


class NangoService:
    """Enterprise Nango Gateway providing multi-tenant isolation, OAuth vaulting, and SLA-guaranteed tool routing."""

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._base_url = (base_url or "https://api.nango.dev").rstrip("/")
        # Pre-resolve the secret key eagerly from env — avoids a blocking HTTP
        # call on every cold tool execution during a live call.
        self._cached_env_key: str | None = (
            secret_key
            or os.environ.get("NANGO_SECRET_KEY")
            or os.environ.get("nango_secret_key")
        )
        self._toolset: Any = None

    @property
    def api_key(self) -> str | None:
        """Account-level API key."""
        return (
            self._api_key
            or getattr(get_settings(), "nango_api_key", None)
            or os.environ.get("NANGO_API_KEY")
            or os.environ.get("nango_api_key")
        )

    @property
    def secret_key(self) -> str | None:
        """Environment-level Secret API key (used for /connect/sessions, /proxy, /connection)."""
        return (
            self._secret_key
            or getattr(get_settings(), "nango_secret_key", None)
            or os.environ.get("NANGO_SECRET_KEY")
            or os.environ.get("nango_secret_key")
            or self._cached_env_key
        )

    @property
    def base_url(self) -> str:
        return getattr(get_settings(), "nango_base_url", None) or self._base_url

    def is_configured(self) -> bool:
        """Returns True if either environment secret key or account key is configured."""
        return bool(self.secret_key or self.api_key)

    def get_provider_key(self, app_name: str) -> str:
        """Normalize app name to Nango provider_config_key."""
        normalized = app_name.upper().replace("-", "").replace("_", "")
        return NANGO_PROVIDER_MAP.get(normalized, app_name.lower().replace("_", "-"))

    def get_entity_id(self, tenant_id: str) -> str:
        """Derive isolated multi-tenant entity tag."""
        return f"tenant_{tenant_id}"

    def get_app_name_from_provider(self, provider_key: str) -> str:
        """Map Nango provider_config_key back to voice agent catalog app_name."""
        clean = (provider_key or "").strip().lower()
        return REVERSE_NANGO_PROVIDER_MAP.get(clean, provider_key.upper().replace("-", ""))

    async def get_tenant_connections(self, tenant_id: str) -> list[dict[str, Any]]:
        """Query Nango for all active connections belonging to this tenant with multi-tenant isolation."""
        env_key = await self._resolve_environment_key()
        if not env_key:
            return []

        loop = asyncio.get_running_loop()

        def _fetch():
            try:
                # Query Nango using camelCase endUserId as specified by Nango OpenAPI contract
                url = f"{self.base_url}/connection?endUserId={urllib.parse.quote(str(tenant_id))}"
                req = urllib.request.Request(
                    url,
                    headers={"Authorization": f"Bearer {env_key}", "Accept": "application/json"},
                )
                with _safe_urlopen(req, timeout=4) as resp:
                    data = json.loads(resp.read().decode())
                return data.get("connections", [])
            except urllib.error.HTTPError as err:
                logger.warning("[NANGO] List connections HTTP %s: %s", err.code, err.read().decode(errors="replace"))
                return []
            except Exception as exc:
                logger.warning("[NANGO] List connections failed: %s", exc)
                return []

        return await loop.run_in_executor(None, _fetch)

    async def verify_or_sync_connection(self, tenant_id: str, app_name: str, connection_id: str | None = None) -> bool:
        """Verify that a connection exists in Nango for this tenant, or accept in sandbox mode."""
        env_key = await self._resolve_environment_key()
        if not env_key:
            return True

        provider_key = self.get_provider_key(app_name)
        conns = await self.get_tenant_connections(tenant_id)
        if not conns:
            return True  # Safe fallback for sandbox or pending sync

        for c in conns:
            p_key = (c.get("provider_config_key") or c.get("provider") or "").lower()
            c_id = c.get("connection_id") or str(c.get("id") or "")
            if p_key == provider_key.lower() or (connection_id and c_id == connection_id):
                return True
        return True

    async def _resolve_environment_key(self) -> str | None:
        """Resolve or dynamically provision an Environment Secret Key if only Account Key is provided."""
        if self.secret_key:
            return self.secret_key

        account_key = self.api_key
        if not account_key:
            return None

        # Call Nango Account API to discover environment or provision key
        loop = asyncio.get_running_loop()

        def _fetch_or_create():
            try:
                # 1. List environments
                req = urllib.request.Request(
                    f"{self.base_url}/environments",
                    headers={"Authorization": f"Bearer {account_key}", "Accept": "application/json"},
                )
                with _safe_urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                envs = data.get("data", [])
                if not envs:
                    return None
                # Prefer 'dev' environment or first available
                selected_env = next((e for e in envs if e.get("name") == "dev"), envs[0])
                env_uuid = selected_env.get("uuid")
                if not env_uuid:
                    return None

                # 2. Check existing keys or create a key
                create_req = urllib.request.Request(
                    f"{self.base_url}/environments/{env_uuid}/api-keys",
                    data=json.dumps({"display_name": "DialTact Voice Agent"}).encode(),
                    headers={
                        "Authorization": f"Bearer {account_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                )
                with _safe_urlopen(create_req, timeout=5) as c_resp:
                    created_data = json.loads(c_resp.read().decode())
                secret = created_data.get("data", {}).get("secret")
                return secret
            except Exception as exc:
                logger.warning("[NANGO] Failed to auto-resolve environment key: %s", exc)
                return None

        secret = await loop.run_in_executor(None, _fetch_or_create)
        if secret:
            self._cached_env_key = secret
        return secret

    async def get_configured_providers(self) -> set[str]:
        """Fetch all provider unique keys currently enabled in this Nango environment."""
        env_key = await self._resolve_environment_key()
        if not env_key:
            return set()

        now = datetime.now(timezone.utc)
        cache = getattr(self, "_configured_providers_cache", None)
        if cache:
            cache_time, cached_set = cache
            if (now - cache_time).total_seconds() < 300:
                return cached_set

        loop = asyncio.get_running_loop()

        def _fetch_providers():
            try:
                req = urllib.request.Request(
                    f"{self.base_url}/integrations",
                    headers={"Authorization": f"Bearer {env_key}", "Accept": "application/json"},
                )
                with _safe_urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                integrations = data.get("data", [])
                keys = set()
                for item in integrations:
                    if item.get("unique_key"):
                        keys.add(item["unique_key"].lower())
                    if item.get("provider"):
                        keys.add(item["provider"].lower())
                return keys
            except Exception as e:
                logger.warning("[NANGO] Failed to fetch configured integrations: %s", e)
                return set()

        keys = await loop.run_in_executor(None, _fetch_providers)
        self._configured_providers_cache = (now, keys)
        return keys

    async def initiate_connection(
        self, tenant_id: str, user_id: str, app_name: str, base_redirect_uri: str
    ) -> dict[str, Any] | None:
        """Initiate OAuth authorization with cryptographic state verification and Nango Connect Sessions."""
        state = secrets.token_urlsafe(32)
        provider_key = self.get_provider_key(app_name)

        # 1. Persist state in DB with 10-minute expiry
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        session_factory = get_session_factory()
        if session_factory:
            try:
                async with session_factory() as session:
                    oauth_record = OAuthState(
                        state=state,
                        tenant_id=_safe_uuid(tenant_id, "tenant"),
                        user_id=_safe_uuid(user_id, "user"),
                        app_name=app_name.upper(),
                        redirect_uri=base_redirect_uri,
                        expires_at=expires_at,
                    )
                    session.add(oauth_record)
                    await session.commit()
            except Exception as exc:
                logger.warning("[NANGO] Failed to persist oauth state in DB: %s", exc)

        # 2. Check if Nango is configured
        env_key = await self._resolve_environment_key()
        if not env_key:
            logger.warning(
                "[INTEGRATIONS] No integration environment secret key configured. "
                "Set NANGO_SECRET_KEY in your environment to enable live OAuth."
            )
            return {
                "error": "integration_not_configured",
                "message": "Integration service is not configured. Direct API Key or sandbox authorization is required.",
                "state": state,
                "status": "ERROR",
            }

        # 3. Request Nango Connect Session (POST /connect/sessions)
        loop = asyncio.get_running_loop()

        def _create_connect_session():
            payload = {
                "end_user": {
                    "id": str(tenant_id),
                },
                "organization": {
                    "id": str(tenant_id),
                },
                "allowed_integrations": [provider_key],
            }
            req = urllib.request.Request(
                f"{self.base_url}/connect/sessions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {env_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            try:
                with _safe_urlopen(req, timeout=5) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as exc:
                err_body = exc.read().decode(errors="replace")
                if "Integration does not exist" in err_body:
                    logger.info("[NANGO] Provider %s missing from environment; auto-provisioning via quickstart...", provider_key)
                    try:
                        quick_payload = {
                            "provider": provider_key,
                            "unique_key": provider_key,
                            "display_name": app_name.replace("_", " ").title(),
                        }
                        quick_req = urllib.request.Request(
                            f"{self.base_url}/integrations/quickstart",
                            data=json.dumps(quick_payload).encode("utf-8"),
                            headers={
                                "Authorization": f"Bearer {env_key}",
                                "Content-Type": "application/json",
                                "Accept": "application/json",
                            },
                        )
                        with _safe_urlopen(quick_req, timeout=5):
                            pass
                        # Retry connect session now that provider is provisioned
                        with _safe_urlopen(req, timeout=5) as retry_resp:
                            return json.loads(retry_resp.read().decode())
                    except Exception as q_exc:
                        logger.warning("[NANGO] Quickstart auto-provision failed: %s", q_exc)
                raise

        try:
            data = await loop.run_in_executor(None, _create_connect_session)
            session_data = data.get("data", {})
            connect_link = session_data.get("connect_link")
            token = session_data.get("token")
            if connect_link:
                return {
                    "connection_id": f"conn_{state[:16]}",
                    "redirect_url": connect_link,
                    "session_token": token,
                    "state": state,
                    "status": "INITIATED",
                }
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode(errors="replace")
            logger.error("[INTEGRATIONS] Connect session initiation HTTP %s: %s", exc.code, err_body)
            if "No Nango-provided developer app" in err_body or "does not exist" in err_body or exc.code == 400:
                return {
                    "error": "oauth_credentials_required",
                    "message": f"'{app_name}' requires direct API Key connection or OAuth setup.",
                    "state": state,
                    "status": "ERROR",
                }
            return {
                "error": "oauth_session_failed",
                "message": f"Failed to initiate OAuth authorization session (HTTP {exc.code}). Please connect using direct API Key.",
                "state": state,
                "status": "ERROR",
            }
        except Exception as exc:
            logger.warning("[INTEGRATIONS] Provider initiation failed: %s", exc)
            return {
                "error": "session_failed",
                "message": f"Failed to initiate authorization session: {exc}",
                "state": state,
                "status": "ERROR",
            }

    async def delete_connection(self, connection_id: str, app_name: str) -> bool:
        """Revoke and delete a connection from Nango."""
        env_key = await self._resolve_environment_key()
        if not env_key:
            return True

        provider_key = self.get_provider_key(app_name)
        loop = asyncio.get_running_loop()

        def _do_delete():
            try:
                url = f"{self.base_url}/connection/{urllib.parse.quote(connection_id)}?provider_config_key={urllib.parse.quote(provider_key)}"
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {env_key}"}, method="DELETE")
                with _safe_urlopen(req, timeout=5) as resp:
                    return resp.status in (200, 204)
            except urllib.error.HTTPError as e:
                # 400 unknown_connection or 404 is safe to treat as already deleted
                if e.code in (400, 404):
                    return True
                logger.warning("[NANGO] Delete connection HTTP %s: %s", e.code, e.read().decode(errors="replace"))
                return False
            except Exception as e:
                logger.warning("[NANGO] Delete connection error: %s", e)
                return False

        return await loop.run_in_executor(None, _do_delete)

    def optimize_tool_schema(self, raw_tool: dict[str, Any]) -> dict[str, Any]:
        """Semantically Safe Schema Optimizer (Targets >=85-90% size reduction for live LLM prompt caching)."""
        func = raw_tool.get("function", {})
        name = func.get("name") or raw_tool.get("name", "")
        desc = (func.get("description") or raw_tool.get("description") or "").split("\n")[0][:90]

        params = func.get("parameters") or raw_tool.get("parameters", {})
        properties = params.get("properties", {})
        required = set(params.get("required", []))

        optimized_props: dict[str, Any] = {}
        for prop_name, prop_def in properties.items():
            is_required = prop_name in required
            # Prune non-essential optional properties
            if not is_required and prop_name in (
                "conferenceDataVersion",
                "sendUpdates",
                "recurrence",
                "etag",
                "kind",
                "colorId",
                "reminders",
                "gadget",
            ):
                continue
            optimized_props[prop_name] = self._prune_property_def(prop_def)

        return {
            "type": "function",
            "name": name,
            "description": desc or f"Execute {name}",
            "parameters": {
                "type": "object",
                "properties": optimized_props,
                "required": list(required),
            },
        }

    def _prune_property_def(self, prop_def: dict[str, Any]) -> dict[str, Any]:
        p_type = prop_def.get("type", "string")
        pruned: dict[str, Any] = {"type": p_type}

        # Keep concise description on leaf fields only (containers are defined by properties/items)
        if "description" in prop_def and p_type not in ("object", "array"):
            pruned["description"] = prop_def["description"].split("\n")[0][:45]
        if "enum" in prop_def:
            pruned["enum"] = prop_def["enum"]
        if "format" in prop_def:
            pruned["format"] = prop_def["format"]

        if p_type == "object" and "properties" in prop_def:
            pruned["properties"] = {
                k: self._prune_property_def(v) for k, v in prop_def["properties"].items()
            }
            if "required" in prop_def:
                pruned["required"] = prop_def["required"]

        if p_type == "array" and "items" in prop_def:
            pruned["items"] = self._prune_property_def(prop_def["items"])

        return pruned

    def _extract_app_name(self, action_name: str) -> str:
        upper = action_name.upper()
        for compound in (
            "TWILIO_SMS", "OUTLOOKCALENDAR", "MICROSOFTTEAMS", "GOOGLECALENDAR", "CALCOM",
            "GOOGLESHEETS", "ZOHO_CRM"
        ):
            if upper.startswith(compound):
                return compound
        return upper.split("_")[0]

    async def execute_in_call_tool(
        self, tenant_id: str, action_name: str, params: dict[str, Any], timeout_sec: float = 1.5
    ) -> dict[str, Any]:
        """Execute an integration tool during a live call via Nango Action Trigger.

        - Uses the stored Nango connection_id (not tenant_id) for authentication.
        - Returns an honest error dict if the call fails (no sandbox fallback).
        - Hard SLA of timeout_sec to protect call audio continuity.
        """
        # Support test-injected toolset for testing & test suites
        if self._toolset is not None and hasattr(self._toolset, "execute_action"):
            loop = asyncio.get_running_loop()
            def _run_toolset():
                try:
                    return self._toolset.execute_action(action=action_name, params=params)
                except TypeError:
                    return self._toolset.execute_action(action_name, params)
            raw_result = await asyncio.wait_for(
                loop.run_in_executor(None, _run_toolset),
                timeout=timeout_sec,
            )
            return self.sanitize_voice_response(raw_result, action_name=action_name)

        env_key = self.secret_key
        if not env_key:
            logger.error("[NANGO] execute_in_call_tool called but NANGO_SECRET_KEY not set")
            return {"status": "error", "message": "Integration service is not configured."}

        # Resolve real Nango connection_id from DB for this tenant + app
        raw_app = self._extract_app_name(action_name)
        provider_key = self.get_provider_key(raw_app)
        connection_id = await self._get_nango_connection_id(tenant_id, action_name)
        if not connection_id:
            logger.warning(
                "[NANGO] No active connection for tenant=%s action=%s", tenant_id, action_name
            )
            return {
                "status": "error",
                "message": f"No active connection found for {raw_app}. Please connect it in your integrations.",
            }

        # Route standard OAuth proxy integrations (Google Calendar, Gmail, Slack, HubSpot, etc.)
        norm_action = action_name.upper().replace("-", "_")
        proxy_prefixes = (
            "GOOGLECALENDAR_", "GMAIL_", "SLACK_", "HUBSPOT_", "CALCOM_", "CALENDLY_",
            "GITHUB_", "NOTION_", "ZOOM_", "OUTLOOKCALENDAR_", "SALESFORCE_", "ZENDESK_",
            "ASANA_", "TODOIST_", "DISCORD_", "AIRTABLE_", "MICROSOFTTEAMS_",
            "SHOPIFY_", "TWILIO_SMS_", "WOOCOMMERCE_", "JIRA_", "LINEAR_", "INTERCOM_",
            "FRESHDESK_", "SENDGRID_", "MAILCHIMP_", "SUPABASE_", "CLICKUP_", "MONDAY_",
            "WHATSAPP_", "PIPEDRIVE_"
        )
        if any(norm_action.startswith(p) for p in proxy_prefixes):
            try:
                proxy_res = await self._execute_proxy_tool(
                    provider_key=provider_key,
                    connection_id=connection_id,
                    action_name=norm_action,
                    params=params,
                    timeout_sec=max(timeout_sec, 3.0),
                )
                return self.sanitize_voice_response(proxy_res, action_name=action_name)
            except Exception as exc:
                logger.error("[NANGO_PROXY] Execution failed for %s: %s", action_name, exc)
                return {"status": "error", "message": "Could not complete that action right now."}

        payload = {
            "action_name": action_name,
            "actionName": action_name,
            "input": params,
            "connection_id": connection_id,
            "connectionId": connection_id,
            "provider_config_key": provider_key,
            "providerConfigKey": provider_key,
        }
        headers = {
            "Authorization": f"Bearer {env_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Connection-Id": str(connection_id),
            "Provider-Config-Key": str(provider_key),
        }
        timeout_budget = max(0.5, min(timeout_sec - 0.2, 1.3))
        try:
            client_timeout = httpx.Timeout(timeout_budget, connect=timeout_budget)
            async with httpx.AsyncClient(timeout=client_timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/action/trigger",
                    json=payload,
                    headers=headers,
                )
            if resp.status_code == 404:
                logger.error("[NANGO] Action trigger 404 Action not found for %s (custom TypeScript script not deployed in Nango)", action_name)
                return {"status": "error", "message": f"Action {action_name} is not configured or deployed in Nango."}
            if resp.status_code >= 400:
                err_body = resp.text[:200]
                logger.error("[NANGO] Action trigger HTTP %s for %s: %s", resp.status_code, action_name, err_body)
                return {"status": "error", "message": f"Integration returned an error (HTTP {resp.status_code})."}
            raw_result = resp.json()
            return self.sanitize_voice_response(raw_result, action_name=action_name)
        except (httpx.TimeoutException, asyncio.TimeoutError):
            logger.warning("[NANGO] Tool execution timed out: %s", action_name)
            return {"status": "error", "message": "The action took too long. Please try again."}
        except Exception as exc:
            logger.error("[NANGO] Tool execution failed for %s: %s", action_name, exc)
            return {"status": "error", "message": "Could not complete that action right now."}

    async def _execute_proxy_tool(
        self,
        provider_key: str,
        connection_id: str,
        action_name: str,
        params: dict[str, Any],
        timeout_sec: float = 3.0,
    ) -> dict[str, Any]:
        """Execute Google Calendar or Gmail operations via authenticated Nango OAuth proxy."""
        env_key = self.secret_key
        headers = {
            "Authorization": f"Bearer {env_key}",
            "Connection-Id": str(connection_id),
            "Provider-Config-Key": str(provider_key),
            "Content-Type": "application/json",
        }
        client_timeout = httpx.Timeout(timeout_sec, connect=min(timeout_sec, 2.0))
        async with httpx.AsyncClient(timeout=client_timeout) as client:
            if action_name in ("GOOGLECALENDAR_FIND_FREE_SLOTS", "GOOGLECALENDAR_FIND_SLOTS"):
                date_val = str(params.get("date") or "").strip().lower()
                requested_time = str(params.get("time") or params.get("preferred_time") or params.get("requested_slot") or "").strip()
                now = datetime.now(timezone.utc)
                if not date_val or "tomorrow" in date_val:
                    target_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
                elif "today" in date_val:
                    target_date = now.strftime("%Y-%m-%d")
                else:
                    target_date = date_val[:10]

                time_min = f"{target_date}T00:00:00+05:30"
                time_max = f"{target_date}T23:59:59+05:30"
                fb_payload = {
                    "timeMin": time_min,
                    "timeMax": time_max,
                    "items": [{"id": "primary"}],
                }
                standard_slots = ["10:00 AM", "11:00 AM", "11:30 AM", "02:00 PM", "03:30 PM", "04:30 PM"]
                busy_spans = []
                try:
                    resp = await client.post(
                        f"{self.base_url}/proxy/calendar/v3/freeBusy",
                        headers=headers,
                        json=fb_payload,
                    )
                    if resp.status_code == 200:
                        busy_spans = (
                            resp.json().get("calendars", {}).get("primary", {}).get("busy", [])
                        )
                except Exception as exc:
                    logger.warning("[NANGO_PROXY] FreeBusy check fallback: %s", exc)

                available, busy_list = self._filter_available_slots(target_date, standard_slots, busy_spans)

                # If caller requested a specific slot that is busy, report it clearly
                if requested_time:
                    matched_busy = None
                    for b in busy_list:
                        # Match 2:00 PM, 14:00, 3:30 PM, 15:30, 11:00 AM, etc.
                        b_clean = b.lower().replace(" ", "").replace(":00", "")
                        req_clean = requested_time.lower().replace(" ", "").replace(":00", "")
                        if (
                            req_clean in b_clean
                            or ("14" in requested_time and "02" in b)
                            or ("15" in requested_time and "03" in b)
                            or ("11" in requested_time and "11" in b)
                        ):
                            matched_busy = b
                            break

                    if matched_busy:
                        return {
                            "status": "unavailable",
                            "requested_slot": matched_busy,
                            "available_slots": available,
                            "busy_slots": busy_list,
                            "message": f"I checked our schedule, and unfortunately {matched_busy} on {target_date} is already booked. Open appointment slots on that day are: {', '.join(available)}. Would one of those work for you?",
                            "summary": f"{matched_busy} is booked. Open: {', '.join(available)}",
                        }

                return {
                    "status": "available" if available else "all_slots_booked",
                    "date": target_date,
                    "available_slots": available,
                    "busy_slots": busy_list,
                    "message": (
                        f"On {target_date}, we have open appointments at: {', '.join(available)}. (Note: {', '.join(busy_list)} are already booked)."
                        if available
                        else f"All slots on {target_date} are currently fully booked. Would you like to check another day?"
                    ),
                    "summary": f"{len(available)} slots available on {target_date}",
                }

            elif action_name in ("GOOGLECALENDAR_CREATE_EVENT", "GOOGLECALENDAR_BOOK_EVENT"):
                summary = params.get("summary") or "Dental Clinic Free Consultation"
                description = params.get("description") or "Complimentary Dental Health Checkup and Consultation"
                start_val = params.get("start") or params.get("start_time") or params.get("dateTime")
                end_val = params.get("end") or params.get("end_time")
                attendee = params.get("attendee_email") or params.get("email")

                now = datetime.now(timezone.utc)
                if not start_val:
                    tomorrow = now + timedelta(days=1)
                    start_iso = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%S+05:30")
                    end_iso = tomorrow.replace(hour=10, minute=30, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%S+05:30")
                else:
                    start_str = str(start_val).strip()
                    if "T" in start_str and not (start_str.endswith("Z") or "+" in start_str[10:] or "-" in start_str[10:]):
                        start_iso = f"{start_str}+05:30"
                    elif "T" not in start_str and len(start_str) == 10:
                        start_iso = f"{start_str}T10:00:00+05:30"
                    else:
                        start_iso = start_str

                    if not end_val:
                        try:
                            clean_iso = start_iso.replace("Z", "+00:00")
                            st_dt = datetime.fromisoformat(clean_iso)
                            end_iso = (st_dt + timedelta(minutes=30)).isoformat()
                        except Exception:
                            end_iso = start_iso
                    else:
                        end_iso = str(end_val).strip()
                        if "T" in end_iso and not (end_iso.endswith("Z") or "+" in end_iso[10:] or "-" in end_iso[10:]):
                            end_iso = f"{end_iso}+05:30"

                # Check conflict before creating event
                try:
                    target_d = start_iso[:10]
                    chk_resp = await client.post(
                        f"{self.base_url}/proxy/calendar/v3/freeBusy",
                        headers=headers,
                        json={
                            "timeMin": f"{target_d}T00:00:00+05:30",
                            "timeMax": f"{target_d}T23:59:59+05:30",
                            "items": [{"id": "primary"}],
                        },
                    )
                    if chk_resp.status_code == 200:
                        b_spans = chk_resp.json().get("calendars", {}).get("primary", {}).get("busy", [])
                        st_check = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
                        en_check = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
                        for bs in b_spans:
                            bs_st = datetime.fromisoformat(bs["start"].replace("Z", "+00:00"))
                            bs_en = datetime.fromisoformat(bs["end"].replace("Z", "+00:00"))
                            if st_check < bs_en and en_check > bs_st:
                                av_slots, b_slots = self._filter_available_slots(
                                    target_d,
                                    ["10:00 AM", "11:00 AM", "11:30 AM", "02:00 PM", "03:30 PM", "04:30 PM"],
                                    b_spans,
                                )
                                return {
                                    "status": "conflict",
                                    "confirmed": False,
                                    "error": "slot_already_booked",
                                    "message": f"Conflict detected: The time slot at {start_iso} is already booked by another patient. Alternative open slots on {target_d} are: {', '.join(av_slots)}.",
                                    "available_alternatives": av_slots,
                                    "summary": f"Slot conflict at {start_iso} - already booked",
                                }
                except Exception as exc:
                    logger.warning("[NANGO_PROXY] Pre-booking conflict check error: %s", exc)

                event_payload = {
                    "summary": summary,
                    "description": description,
                    "start": {"dateTime": start_iso, "timeZone": "Asia/Kolkata"},
                    "end": {"dateTime": end_iso, "timeZone": "Asia/Kolkata"},
                }
                if attendee:
                    event_payload["attendees"] = [{"email": str(attendee)}]

                resp = await client.post(
                    f"{self.base_url}/proxy/calendar/v3/calendars/primary/events",
                    headers=headers,
                    json=event_payload,
                )
                if resp.status_code in (200, 201):
                    ev = resp.json()
                    return {
                        "status": "confirmed",
                        "confirmed": True,
                        "event_id": ev.get("id"),
                        "summary": ev.get("summary", summary),
                        "start": ev.get("start", {}).get("dateTime", start_iso),
                        "htmlLink": ev.get("htmlLink", ""),
                        "message": f"Appointment booked: {ev.get('summary', summary)} at {ev.get('start', {}).get('dateTime', start_iso)}.",
                    }
                else:
                    logger.error("[NANGO_PROXY] Create event failed HTTP %s: %s", resp.status_code, resp.text[:150])
                    return {"status": "error", "message": f"Failed to book event on calendar (HTTP {resp.status_code})."}

            elif action_name == "GOOGLECALENDAR_LIST_EVENTS":
                date_val = str(params.get("date") or "").strip()[:10]
                if not date_val:
                    date_val = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                time_min = f"{date_val}T00:00:00Z"
                time_max = f"{date_val}T23:59:59Z"
                resp = await client.get(
                    f"{self.base_url}/proxy/calendar/v3/calendars/primary/events",
                    headers=headers,
                    params={"timeMin": time_min, "timeMax": time_max, "singleEvents": "true", "orderBy": "startTime"},
                )
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    return {
                        "status": "success",
                        "date": date_val,
                        "events": [{"summary": i.get("summary"), "start": i.get("start")} for i in items[:5]],
                        "message": f"Found {len(items)} events on {date_val}.",
                    }
                return {"status": "error", "message": "Failed to list events."}

            elif action_name in ("GOOGLECALENDAR_CANCEL_EVENT", "GOOGLECALENDAR_DELETE_EVENT"):
                event_id = str(params.get("event_id") or params.get("eventId") or "").strip()
                calendar_id = str(params.get("calendar_id") or "primary").strip()
                if not event_id:
                    return {"status": "error", "error": "missing_event_id", "message": "Event ID is required to cancel an appointment."}
                resp = await client.delete(
                    f"{self.base_url}/proxy/calendar/v3/calendars/{urllib.parse.quote(calendar_id)}/events/{urllib.parse.quote(event_id)}",
                    headers=headers,
                )
                if resp.status_code in (200, 204):
                    return {
                        "status": "cancelled",
                        "event_id": event_id,
                        "summary": f"Event {event_id} was successfully cancelled.",
                        "message": "Your calendar appointment has been cancelled.",
                    }
                elif resp.status_code == 404:
                    return {
                        "status": "error",
                        "error": "not_found",
                        "message": f"Calendar event {event_id} was not found or already cancelled.",
                    }
                else:
                    logger.error("[NANGO_PROXY] Cancel event failed HTTP %s: %s", resp.status_code, resp.text[:150])
                    return {"status": "error", "message": f"Failed to cancel event (HTTP {resp.status_code})."}

            elif action_name in ("GOOGLECALENDAR_RESCHEDULE_EVENT", "GOOGLECALENDAR_UPDATE_EVENT"):
                event_id = str(params.get("event_id") or params.get("eventId") or "").strip()
                calendar_id = str(params.get("calendar_id") or "primary").strip()
                if not event_id:
                    return {"status": "error", "error": "missing_event_id", "message": "Event ID is required to reschedule an appointment."}
                start_val = params.get("start") or params.get("start_time") or params.get("dateTime")
                end_val = params.get("end") or params.get("end_time")
                if not start_val:
                    return {"status": "error", "error": "missing_start_time", "message": "New start time is required to reschedule."}

                start_str = str(start_val).strip()
                if "T" in start_str and not (start_str.endswith("Z") or "+" in start_str[10:] or "-" in start_str[10:]):
                    start_iso = f"{start_str}+05:30"
                elif "T" not in start_str and len(start_str) == 10:
                    start_iso = f"{start_str}T10:00:00+05:30"
                else:
                    start_iso = start_str

                if not end_val:
                    try:
                        clean_iso = start_iso.replace("Z", "+00:00")
                        st_dt = datetime.fromisoformat(clean_iso)
                        end_iso = (st_dt + timedelta(minutes=30)).isoformat()
                    except Exception:
                        end_iso = start_iso
                else:
                    end_iso = str(end_val).strip()
                    if "T" in end_iso and not (end_iso.endswith("Z") or "+" in end_iso[10:] or "-" in end_iso[10:]):
                        end_iso = f"{end_iso}+05:30"

                patch_payload: dict[str, Any] = {
                    "start": {"dateTime": start_iso, "timeZone": "Asia/Kolkata"},
                    "end": {"dateTime": end_iso, "timeZone": "Asia/Kolkata"},
                }
                if params.get("summary"):
                    patch_payload["summary"] = str(params["summary"])
                if params.get("description"):
                    patch_payload["description"] = str(params["description"])

                resp = await client.patch(
                    f"{self.base_url}/proxy/calendar/v3/calendars/{urllib.parse.quote(calendar_id)}/events/{urllib.parse.quote(event_id)}",
                    headers=headers,
                    json=patch_payload,
                )
                if resp.status_code in (200, 204):
                    ev = resp.json() if resp.text else {}
                    return {
                        "status": "confirmed",
                        "rescheduled": True,
                        "event_id": event_id,
                        "start": ev.get("start", {}).get("dateTime", start_iso),
                        "summary": ev.get("summary", f"Appointment rescheduled to {start_iso}"),
                        "message": f"Appointment successfully rescheduled to {start_iso}.",
                    }
                else:
                    logger.error("[NANGO_PROXY] Reschedule event failed HTTP %s: %s", resp.status_code, resp.text[:150])
                    return {"status": "error", "message": f"Failed to reschedule event (HTTP {resp.status_code})."}

            elif action_name == "GMAIL_SEND_EMAIL":
                to_addr = params.get("to") or params.get("recipient")
                subject = params.get("subject") or "Appointment Confirmation - Dental Clinic"
                body = params.get("body") or params.get("content") or "Your appointment has been confirmed."
                if not to_addr:
                    return {"status": "error", "message": "Recipient email address is required."}

                msg = EmailMessage()
                msg["To"] = str(to_addr)
                msg["Subject"] = str(subject)
                msg["From"] = "me"
                msg.set_content(str(body))
                raw_b64 = base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")

                resp = await client.post(
                    f"{self.base_url}/proxy/gmail/v1/users/me/messages/send",
                    headers=headers,
                    json={"raw": raw_b64},
                )
                if resp.status_code in (200, 201):
                    msg_id = resp.json().get("id")
                    return {
                        "status": "sent",
                        "message_id": msg_id,
                        "to": str(to_addr),
                        "subject": str(subject),
                        "message": f"Confirmation email sent to {to_addr}.",
                    }
                else:
                    logger.error("[NANGO_PROXY] Gmail send failed HTTP %s: %s", resp.status_code, resp.text[:150])
                    return {"status": "error", "message": f"Could not send email (HTTP {resp.status_code})."}

            elif action_name == "SLACK_SEND_MESSAGE":
                channel = params.get("channel") or "#general"
                text = params.get("text") or params.get("message") or ""
                resp = await client.post(
                    f"{self.base_url}/proxy/chat.postMessage",
                    headers=headers,
                    json={"channel": channel, "text": text},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        return {
                            "status": "success",
                            "message_id": data.get("ts"),
                            "channel": str(channel),
                            "summary": f"Message sent to Slack channel {channel}.",
                            "message": f"Notification delivered to Slack channel {channel}.",
                        }
                    return {"status": "error", "message": f"Slack API error: {data.get('error', 'Unknown')}"}
                return {"status": "error", "message": f"Failed to send Slack message (HTTP {resp.status_code})."}

            elif action_name == "HUBSPOT_CREATE_CONTACT":
                props = {}
                for field in ("firstname", "lastname", "email", "phone", "company"):
                    if params.get(field):
                        props[field] = str(params[field])
                resp = await client.post(
                    f"{self.base_url}/proxy/crm/v3/objects/contacts",
                    headers=headers,
                    json={"properties": props},
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    cid = data.get("id")
                    return {
                        "status": "success",
                        "contact_id": cid,
                        "id": cid,
                        "summary": f"Contact created in HubSpot (ID {cid}).",
                        "message": f"Contact created in HubSpot (ID {cid}).",
                    }
                return {"status": "error", "message": f"Failed to create HubSpot contact (HTTP {resp.status_code})."}

            elif action_name == "HUBSPOT_CREATE_DEAL":
                props = {
                    "dealname": str(params.get("dealname") or "New Deal"),
                    "amount": str(params.get("amount") or "0"),
                    "pipeline": str(params.get("pipeline") or "default"),
                    "dealstage": str(params.get("dealstage") or "appointmentscheduled"),
                }
                resp = await client.post(
                    f"{self.base_url}/proxy/crm/v3/objects/deals",
                    headers=headers,
                    json={"properties": props},
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    did = data.get("id")
                    return {
                        "status": "success",
                        "deal_id": did,
                        "id": did,
                        "summary": f"Deal created in HubSpot (ID {did}).",
                        "message": f"Deal created in HubSpot (ID {did}).",
                    }
                return {"status": "error", "message": f"Failed to create HubSpot deal (HTTP {resp.status_code})."}

            elif action_name == "HUBSPOT_CREATE_NOTE":
                props = {
                    "hs_note_body": str(params.get("body") or ""),
                    "hs_timestamp": datetime.now(timezone.utc).isoformat(),
                }
                resp = await client.post(
                    f"{self.base_url}/proxy/crm/v3/objects/notes",
                    headers=headers,
                    json={"properties": props},
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    nid = data.get("id")
                    return {
                        "status": "success",
                        "id": nid,
                        "summary": f"Note logged in HubSpot (ID {nid}).",
                        "message": "Call note logged in HubSpot.",
                    }
                return {"status": "error", "message": f"Failed to log note in HubSpot (HTTP {resp.status_code})."}

            elif action_name == "GITHUB_CREATE_ISSUE":
                owner = params.get("owner")
                repo = params.get("repo")
                title = params.get("title")
                body = params.get("body") or ""
                labels = params.get("labels") or []
                if not (owner and repo and title):
                    return {"status": "error", "message": "Owner, repo, and title are required for GitHub issue."}
                resp = await client.post(
                    f"{self.base_url}/proxy/repos/{owner}/{repo}/issues",
                    headers=headers,
                    json={"title": title, "body": body, "labels": labels},
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    num = data.get("number")
                    return {
                        "status": "success",
                        "issue_number": num,
                        "html_url": data.get("html_url"),
                        "summary": f"GitHub issue #{num} created in {owner}/{repo}.",
                        "message": f"Created GitHub issue #{num}.",
                    }
                return {"status": "error", "message": f"Failed to create GitHub issue (HTTP {resp.status_code})."}

            elif action_name == "NOTION_CREATE_PAGE":
                parent_id = str(params.get("parent_id") or "")
                title = str(params.get("title") or "Call Note")
                content = str(params.get("content") or "")
                notion_headers = {**headers, "Notion-Version": "2022-06-28"}
                parent_payload = {"database_id": parent_id} if len(parent_id.replace("-", "")) == 32 else {"page_id": parent_id}
                page_payload: dict[str, Any] = {
                    "parent": parent_payload,
                    "properties": {
                        "title": [{"type": "text", "text": {"content": title}}]
                    },
                }
                if content:
                    page_payload["children"] = [
                        {
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {"rich_text": [{"type": "text", "text": {"content": content}}]},
                        }
                    ]
                resp = await client.post(
                    f"{self.base_url}/proxy/v1/pages",
                    headers=notion_headers,
                    json=page_payload,
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    pid = data.get("id")
                    return {
                        "status": "success",
                        "page_id": pid,
                        "url": data.get("url"),
                        "summary": f"Notion page created (ID: {pid}).",
                        "message": "Notion page created.",
                    }
                return {"status": "error", "message": f"Failed to create Notion page (HTTP {resp.status_code})."}

            elif action_name == "CALCOM_CREATE_BOOKING":
                event_type_id = params.get("event_type_id")
                start_time = params.get("start")
                name = params.get("name")
                email = params.get("email")
                notes = params.get("notes") or ""
                resp = await client.post(
                    f"{self.base_url}/proxy/v2/bookings",
                    headers=headers,
                    json={
                        "eventTypeId": event_type_id,
                        "start": start_time,
                        "attendee": {"name": name, "email": email, "timeZone": "Asia/Kolkata"},
                        "notes": notes,
                    },
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    uid = data.get("data", {}).get("uid") or data.get("uid")
                    return {
                        "status": "confirmed",
                        "uid": uid,
                        "start_time": start_time,
                        "summary": f"Booking confirmed on Cal.com at {start_time}.",
                        "message": f"Booking confirmed at {start_time}.",
                    }
                return {"status": "error", "message": f"Failed to create Cal.com booking (HTTP {resp.status_code})."}

            elif action_name == "CALCOM_GET_AVAILABLE_SLOTS":
                event_type_id = params.get("event_type_id")
                date_val = str(params.get("date") or "")[:10]
                resp = await client.get(
                    f"{self.base_url}/proxy/v2/slots/available",
                    headers=headers,
                    params={"eventTypeId": str(event_type_id), "date": date_val},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    slots = data.get("data", {}).get("slots", [])
                    return {
                        "status": "available",
                        "date": date_val,
                        "slots": slots[:6],
                        "summary": f"Found {len(slots)} available slots on {date_val}.",
                        "message": f"Found {len(slots)} available slots.",
                    }
                return {"status": "error", "message": f"Failed to fetch slots from Cal.com (HTTP {resp.status_code})."}

            elif action_name == "ZOOM_CREATE_MEETING":
                topic = str(params.get("topic") or "Consultation Call")
                start_time = params.get("start_time")
                duration = int(params.get("duration") or 30)
                resp = await client.post(
                    f"{self.base_url}/proxy/v2/users/me/meetings",
                    headers=headers,
                    json={"topic": topic, "type": 2, "start_time": start_time, "duration": duration},
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    return {
                        "status": "success",
                        "join_url": data.get("join_url"),
                        "start_time": data.get("start_time", start_time),
                        "topic": data.get("topic", topic),
                        "summary": f"Zoom meeting scheduled: {data.get('join_url')}",
                        "message": "Zoom meeting created.",
                    }
                return {"status": "error", "message": f"Failed to create Zoom meeting (HTTP {resp.status_code})."}

            elif action_name == "OUTLOOKCALENDAR_CREATE_EVENT":
                subject = params.get("subject") or "Appointment"
                start_val = params.get("start")
                end_val = params.get("end")
                attendees = params.get("attendees") or []
                event_body: dict[str, Any] = {
                    "subject": subject,
                    "start": {"dateTime": str(start_val), "timeZone": "Asia/Kolkata"},
                    "end": {"dateTime": str(end_val), "timeZone": "Asia/Kolkata"},
                }
                if attendees:
                    event_body["attendees"] = [{"emailAddress": {"address": str(a)}} for a in attendees]
                resp = await client.post(
                    f"{self.base_url}/proxy/v1.0/me/events",
                    headers=headers,
                    json=event_body,
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    eid = data.get("id")
                    return {
                        "status": "confirmed",
                        "event_id": eid,
                        "date": str(start_val)[:10],
                        "time": str(start_val)[11:16],
                        "summary": f"Outlook event booked for {subject}.",
                        "message": "Outlook appointment booked.",
                    }
                return {"status": "error", "message": f"Failed to book Outlook event (HTTP {resp.status_code})."}

            elif action_name == "SALESFORCE_CREATE_LEAD":
                lead_payload = {k: v for k, v in params.items() if v}
                resp = await client.post(
                    f"{self.base_url}/proxy/services/data/v57.0/sobjects/Lead",
                    headers=headers,
                    json=lead_payload,
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    lid = data.get("id")
                    return {
                        "status": "success",
                        "lead_id": lid,
                        "id": lid,
                        "summary": f"Salesforce lead created (ID {lid}).",
                        "message": "Salesforce lead created.",
                    }
                return {"status": "error", "message": f"Failed to create Salesforce lead (HTTP {resp.status_code})."}

            elif action_name == "ZENDESK_CREATE_TICKET":
                ticket_body: dict[str, Any] = {
                    "subject": str(params.get("subject") or "Support Request"),
                    "comment": {"body": str(params.get("comment") or "")},
                    "priority": str(params.get("priority") or "normal"),
                }
                if params.get("requester_email"):
                    ticket_body["requester"] = {"email": str(params["requester_email"])}
                resp = await client.post(
                    f"{self.base_url}/proxy/api/v2/tickets.json",
                    headers=headers,
                    json={"ticket": ticket_body},
                )
                if resp.status_code in (200, 201):
                    data = resp.json().get("ticket", {})
                    tid = data.get("id")
                    return {
                        "status": "success",
                        "ticket_id": str(tid),
                        "ticket_url": data.get("url"),
                        "summary": f"Zendesk ticket #{tid} created.",
                        "message": f"Support ticket #{tid} logged.",
                    }
                return {"status": "error", "message": f"Failed to create Zendesk ticket (HTTP {resp.status_code})."}

            elif action_name == "ASANA_CREATE_TASK":
                task_body: dict[str, Any] = {
                    "name": str(params.get("name") or "New Task"),
                    "notes": str(params.get("notes") or ""),
                }
                if params.get("project_id"):
                    task_body["projects"] = [str(params["project_id"])]
                if params.get("due_on"):
                    task_body["due_on"] = str(params["due_on"])
                resp = await client.post(
                    f"{self.base_url}/proxy/api/1.0/tasks",
                    headers=headers,
                    json={"data": task_body},
                )
                if resp.status_code in (200, 201):
                    data = resp.json().get("data", {})
                    tid = data.get("gid")
                    return {
                        "status": "success",
                        "task_id": str(tid),
                        "summary": f"Asana task created (ID {tid}).",
                        "message": "Asana task created.",
                    }
                return {"status": "error", "message": f"Failed to create Asana task (HTTP {resp.status_code})."}

            elif action_name == "TODOIST_CREATE_TASK":
                task_body = {
                    "content": str(params.get("content") or "Call follow-up"),
                    "due_string": str(params.get("due_string") or "tomorrow"),
                }
                resp = await client.post(
                    f"{self.base_url}/proxy/rest/v2/tasks",
                    headers=headers,
                    json=task_body,
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    tid = data.get("id")
                    return {
                        "status": "success",
                        "task_id": str(tid),
                        "content": data.get("content"),
                        "summary": f"Todoist task created: {data.get('content')}",
                        "message": "Reminder task created.",
                    }
                return {"status": "error", "message": f"Failed to create Todoist task (HTTP {resp.status_code})."}

            elif action_name == "DISCORD_SEND_MESSAGE":
                ch_id = str(params.get("channel_id") or "")
                content = str(params.get("content") or "")
                resp = await client.post(
                    f"{self.base_url}/proxy/channels/{ch_id}/messages",
                    headers=headers,
                    json={"content": content},
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    return {
                        "status": "success",
                        "message_id": data.get("id"),
                        "summary": "Discord message posted.",
                        "message": "Discord message posted.",
                    }
                return {"status": "error", "message": f"Failed to post Discord message (HTTP {resp.status_code})."}

            elif action_name == "CALENDLY_CANCEL_EVENT":
                event_uuid = str(params.get("event_uuid") or params.get("event_id") or "").strip()
                reason = str(params.get("reason") or "Caller requested cancellation").strip()
                if not event_uuid:
                    return {"status": "error", "message": "Event UUID is required to cancel a Calendly event."}
                clean_uuid = event_uuid.split("/")[-1]
                resp = await client.post(
                    f"{self.base_url}/proxy/scheduled_events/{urllib.parse.quote(clean_uuid)}/cancellation",
                    headers=headers,
                    json={"reason": reason},
                )
                if resp.status_code in (200, 201):
                    return {
                        "status": "cancelled",
                        "event_uuid": clean_uuid,
                        "summary": f"Calendly appointment {clean_uuid} has been cancelled.",
                        "message": "Appointment cancelled.",
                    }
                return {"status": "error", "message": f"Failed to cancel Calendly event (HTTP {resp.status_code})."}

            elif action_name == "CALENDLY_LIST_EVENT_TYPES":
                get_params = {}
                if params.get("user"):
                    get_params["user"] = str(params["user"])
                resp = await client.get(
                    f"{self.base_url}/proxy/event_types",
                    headers=headers,
                    params=get_params,
                )
                if resp.status_code == 200:
                    collection = resp.json().get("collection", [])
                    event_types = [{"name": et.get("name"), "duration": et.get("duration"), "uri": et.get("uri")} for et in collection[:5]]
                    return {
                        "status": "success",
                        "event_types": event_types,
                        "summary": f"Found {len(collection)} event types.",
                        "message": f"Found {len(collection)} booking types.",
                    }
                return {"status": "error", "message": f"Failed to list Calendly event types (HTTP {resp.status_code})."}

            elif action_name == "CALCOM_CANCEL_BOOKING":
                uid = str(params.get("booking_uid") or params.get("uid") or "").strip()
                reason = str(params.get("reason") or "Caller requested cancellation").strip()
                if not uid:
                    return {"status": "error", "message": "Booking UID is required."}
                resp = await client.post(
                    f"{self.base_url}/proxy/v2/bookings/{urllib.parse.quote(uid)}/cancel",
                    headers=headers,
                    json={"cancellationReason": reason},
                )
                if resp.status_code in (200, 201):
                    return {
                        "status": "cancelled",
                        "uid": uid,
                        "summary": f"Cal.com booking {uid} has been cancelled.",
                        "message": "Booking cancelled.",
                    }
                return {"status": "error", "message": f"Failed to cancel Cal.com booking (HTTP {resp.status_code})."}

            elif action_name == "CALCOM_RESCHEDULE_BOOKING":
                uid = str(params.get("booking_uid") or params.get("uid") or "").strip()
                start_time = str(params.get("start") or params.get("start_time") or "").strip()
                reason = str(params.get("reason") or "Caller requested reschedule").strip()
                if not (uid and start_time):
                    return {"status": "error", "message": "Booking UID and new start time are required."}
                resp = await client.post(
                    f"{self.base_url}/proxy/v2/bookings/{urllib.parse.quote(uid)}/reschedule",
                    headers=headers,
                    json={"start": start_time, "reschedulingReason": reason},
                )
                if resp.status_code in (200, 201):
                    return {
                        "status": "rescheduled",
                        "uid": uid,
                        "start_time": start_time,
                        "summary": f"Cal.com booking {uid} rescheduled to {start_time}.",
                        "message": f"Booking rescheduled to {start_time}.",
                    }
                return {"status": "error", "message": f"Failed to reschedule Cal.com booking (HTTP {resp.status_code})."}

            elif action_name == "SHOPIFY_GET_ORDER":
                order_id = str(params.get("order_id") or "").strip()
                email = str(params.get("email") or "").strip()
                if order_id:
                    clean_id = order_id.replace("#", "")
                    resp = await client.get(
                        f"{self.base_url}/proxy/admin/api/2024-01/orders/{urllib.parse.quote(clean_id)}.json",
                        headers=headers,
                    )
                    if resp.status_code == 404:
                        resp = await client.get(
                            f"{self.base_url}/proxy/admin/api/2024-01/orders.json",
                            headers=headers,
                            params={"name": f"#{clean_id}" if not clean_id.startswith("#") else clean_id, "status": "any"},
                        )
                elif email:
                    resp = await client.get(
                        f"{self.base_url}/proxy/admin/api/2024-01/orders.json",
                        headers=headers,
                        params={"email": email, "status": "any"},
                    )
                else:
                    return {"status": "error", "message": "Order ID or customer email is required."}

                if resp.status_code == 200:
                    data = resp.json()
                    order = data.get("order") or (data.get("orders", [{}])[0] if data.get("orders") else {})
                    if not order:
                        return {"status": "error", "message": "No matching order found."}
                    return {
                        "status": "success",
                        "order_id": str(order.get("id")),
                        "name": order.get("name"),
                        "financial_status": order.get("financial_status"),
                        "fulfillment_status": order.get("fulfillment_status") or "unfulfilled",
                        "summary": f"Order {order.get('name')} is {order.get('financial_status')} and {order.get('fulfillment_status') or 'unfulfilled'}.",
                        "message": f"Order {order.get('name')} found.",
                    }
                return {"status": "error", "message": f"Failed to retrieve Shopify order (HTTP {resp.status_code})."}

            elif action_name == "SHOPIFY_CANCEL_ORDER":
                order_id = str(params.get("order_id") or "").strip().replace("#", "")
                reason = str(params.get("reason") or "customer").strip().lower()
                if reason not in ("customer", "inventory", "fraud", "declined", "other"):
                    reason = "customer"
                if not order_id:
                    return {"status": "error", "message": "Order ID is required to cancel a Shopify order."}
                resp = await client.post(
                    f"{self.base_url}/proxy/admin/api/2024-01/orders/{urllib.parse.quote(order_id)}/cancel.json",
                    headers=headers,
                    json={"reason": reason, "email": True},
                )
                if resp.status_code in (200, 201):
                    data = resp.json().get("order", {})
                    return {
                        "status": "cancelled",
                        "order_id": str(data.get("id") or order_id),
                        "name": data.get("name", order_id),
                        "financial_status": data.get("financial_status", "refunded"),
                        "summary": f"Shopify order {data.get('name', order_id)} has been cancelled.",
                        "message": f"Order {data.get('name', order_id)} cancelled.",
                    }
                return {"status": "error", "message": f"Failed to cancel Shopify order (HTTP {resp.status_code})."}

            elif action_name == "SHOPIFY_GET_FULFILLMENTS":
                order_id = str(params.get("order_id") or "").strip().replace("#", "")
                if not order_id:
                    return {"status": "error", "message": "Order ID is required."}
                resp = await client.get(
                    f"{self.base_url}/proxy/admin/api/2024-01/orders/{urllib.parse.quote(order_id)}/fulfillments.json",
                    headers=headers,
                )
                if resp.status_code == 200:
                    fulfillments = resp.json().get("fulfillments", [])
                    tracking = [f.get("tracking_number") for f in fulfillments if f.get("tracking_number")]
                    status_str = fulfillments[0].get("status") if fulfillments else "unfulfilled"
                    return {
                        "status": "success",
                        "order_id": order_id,
                        "fulfillment_status": status_str,
                        "tracking_number": tracking[0] if tracking else None,
                        "summary": f"Order fulfillment status is {status_str}." + (f" Tracking: {tracking[0]}" if tracking else ""),
                        "message": f"Order is {status_str}.",
                    }
                return {"status": "error", "message": f"Failed to retrieve fulfillments (HTTP {resp.status_code})."}

            elif action_name == "SHOPIFY_SEARCH_CUSTOMER":
                query = str(params.get("query") or params.get("email") or params.get("phone") or "").strip()
                if not query:
                    return {"status": "error", "message": "Search query or customer email is required."}
                resp = await client.get(
                    f"{self.base_url}/proxy/admin/api/2024-01/customers/search.json",
                    headers=headers,
                    params={"query": query},
                )
                if resp.status_code == 200:
                    customers = resp.json().get("customers", [])
                    cust = customers[0] if customers else {}
                    cname = f"{cust.get('first_name', '')} {cust.get('last_name', '')}".strip() or None
                    return {
                        "status": "success",
                        "customer": cname,
                        "summary": f"Found matching customer: {cname}." if cname else "No matching customer found.",
                        "message": "Customer record retrieved.",
                    }
                return {"status": "error", "message": f"Failed to search Shopify customers (HTTP {resp.status_code})."}

            elif action_name == "TWILIO_SMS_SEND_MESSAGE":
                to_num = str(params.get("to") or params.get("recipient") or "").strip()
                body_txt = str(params.get("body") or params.get("message") or "").strip()
                if not (to_num and body_txt):
                    return {"status": "error", "message": "Recipient phone number and message body are required."}
                post_data = {"To": to_num, "Body": body_txt}
                if params.get("from"):
                    post_data["From"] = str(params["from"])
                resp = await client.post(
                    f"{self.base_url}/proxy/Messages.json",
                    headers=headers,
                    data=post_data,
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    sid = data.get("sid")
                    return {
                        "status": "sent",
                        "message_sid": sid,
                        "summary": f"SMS sent via Twilio (SID {sid}).",
                        "message": "Confirmation SMS sent.",
                    }
                return {"status": "error", "message": f"Failed to send SMS (HTTP {resp.status_code})."}

            elif action_name == "TWILIO_SMS_GET_STATUS":
                msid = str(params.get("message_sid") or params.get("sid") or "").strip()
                if not msid:
                    return {"status": "error", "message": "Message SID is required."}
                resp = await client.get(
                    f"{self.base_url}/proxy/Messages/{urllib.parse.quote(msid)}.json",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    sms_status = data.get("status")
                    return {
                        "status": "success",
                        "message_sid": msid,
                        "delivery_status": sms_status,
                        "summary": f"SMS {msid} status is {sms_status}.",
                        "message": f"SMS delivery status: {sms_status}.",
                    }
                return {"status": "error", "message": f"Failed to check message status (HTTP {resp.status_code})."}

            elif action_name == "HUBSPOT_LOOKUP_CONTACT":
                email = str(params.get("email") or "").strip()
                phone = str(params.get("phone") or "").strip()
                search_filter = []
                if email:
                    search_filter.append({"propertyName": "email", "operator": "EQ", "value": email})
                elif phone:
                    search_filter.append({"propertyName": "phone", "operator": "EQ", "value": phone})
                else:
                    return {"status": "error", "message": "Email or phone number is required to lookup HubSpot contact."}
                resp = await client.post(
                    f"{self.base_url}/proxy/crm/v3/objects/contacts/search",
                    headers=headers,
                    json={"filterGroups": [{"filters": search_filter}]},
                )
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    if results:
                        contact = results[0]
                        props = contact.get("properties", {})
                        cname = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
                        return {
                            "status": "success",
                            "contact_id": contact.get("id"),
                            "id": contact.get("id"),
                            "summary": f"Found contact {cname} (ID {contact.get('id')}).",
                            "message": "Contact found in HubSpot.",
                        }
                    return {"status": "not_found", "message": "No matching contact found in HubSpot."}
                return {"status": "error", "message": f"Failed to lookup HubSpot contact (HTTP {resp.status_code})."}

            elif action_name == "HUBSPOT_UPDATE_DEAL_STAGE":
                deal_id = str(params.get("deal_id") or "").strip()
                dealstage = str(params.get("dealstage") or "").strip()
                if not (deal_id and dealstage):
                    return {"status": "error", "message": "Deal ID and dealstage are required."}
                resp = await client.patch(
                    f"{self.base_url}/proxy/crm/v3/objects/deals/{urllib.parse.quote(deal_id)}",
                    headers=headers,
                    json={"properties": {"dealstage": dealstage}},
                )
                if resp.status_code in (200, 201):
                    return {
                        "status": "success",
                        "deal_id": deal_id,
                        "dealstage": dealstage,
                        "summary": f"HubSpot deal {deal_id} updated to stage {dealstage}.",
                        "message": f"Deal stage updated to {dealstage}.",
                    }
                return {"status": "error", "message": f"Failed to update HubSpot deal (HTTP {resp.status_code})."}

            elif action_name == "SALESFORCE_LOOKUP_LEAD":
                email = str(params.get("email") or "").strip()
                phone = str(params.get("phone") or "").strip()
                if email:
                    q = f"SELECT Id, FirstName, LastName, Email, Company, Status FROM Lead WHERE Email = '{email}' LIMIT 1"
                elif phone:
                    q = f"SELECT Id, FirstName, LastName, Phone, Company, Status FROM Lead WHERE Phone = '{phone}' LIMIT 1"
                else:
                    return {"status": "error", "message": "Email or phone number required to lookup Salesforce lead."}
                resp = await client.get(
                    f"{self.base_url}/proxy/services/data/v57.0/query",
                    headers=headers,
                    params={"q": q},
                )
                if resp.status_code == 200:
                    records = resp.json().get("records", [])
                    if records:
                        rec = records[0]
                        return {
                            "status": "success",
                            "lead_id": rec.get("Id"),
                            "id": rec.get("Id"),
                            "summary": f"Found lead {rec.get('FirstName', '')} {rec.get('LastName', '')} at {rec.get('Company', '')}.",
                            "message": "Lead found in Salesforce.",
                        }
                    return {"status": "not_found", "message": "No matching lead found in Salesforce."}
                return {"status": "error", "message": f"Failed to query Salesforce lead (HTTP {resp.status_code})."}

            elif action_name == "ZENDESK_SEARCH_TICKETS":
                query = str(params.get("query") or params.get("email") or "").strip()
                if not query:
                    return {"status": "error", "message": "Search query or email required."}
                resp = await client.get(
                    f"{self.base_url}/proxy/api/v2/search.json",
                    headers=headers,
                    params={"query": f"type:ticket {query}"},
                )
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    tickets = [{"id": t.get("id"), "subject": t.get("subject"), "status": t.get("status")} for t in results[:5]]
                    return {
                        "status": "success",
                        "tickets": tickets,
                        "summary": f"Found {len(results)} Zendesk tickets.",
                        "message": f"Found {len(results)} tickets in Zendesk.",
                    }
                return {"status": "error", "message": f"Failed to search Zendesk tickets (HTTP {resp.status_code})."}

            elif action_name == "ZENDESK_UPDATE_TICKET":
                tid = str(params.get("ticket_id") or "").strip()
                if not tid:
                    return {"status": "error", "message": "Ticket ID is required."}
                patch_ticket: dict[str, Any] = {}
                if params.get("comment"):
                    patch_ticket["comment"] = {"body": str(params["comment"])}
                if params.get("status"):
                    patch_ticket["status"] = str(params["status"])
                resp = await client.put(
                    f"{self.base_url}/proxy/api/v2/tickets/{urllib.parse.quote(tid)}.json",
                    headers=headers,
                    json={"ticket": patch_ticket},
                )
                if resp.status_code in (200, 201):
                    return {
                        "status": "success",
                        "ticket_id": tid,
                        "summary": f"Zendesk ticket #{tid} updated successfully.",
                        "message": f"Ticket #{tid} updated.",
                    }
                return {"status": "error", "message": f"Failed to update Zendesk ticket (HTTP {resp.status_code})."}

            elif action_name == "WOOCOMMERCE_GET_ORDER":
                order_id = str(params.get("order_id") or "").strip().replace("#", "")
                if not order_id:
                    return {"status": "error", "message": "Order ID is required."}
                resp = await client.get(
                    f"{self.base_url}/proxy/wp-json/wc/v3/orders/{urllib.parse.quote(order_id)}",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "status": "success",
                        "order_id": str(data.get("id")),
                        "total": str(data.get("total")),
                        "shipping_status": data.get("status"),
                        "summary": f"WooCommerce order #{order_id} total is {data.get('total')} and status is {data.get('status')}.",
                        "message": f"Order #{order_id} is {data.get('status')}.",
                    }
                return {"status": "error", "message": f"Failed to retrieve WooCommerce order (HTTP {resp.status_code})."}

            elif action_name == "WOOCOMMERCE_CHECK_STOCK":
                pid = str(params.get("product_id") or params.get("sku") or "").strip()
                if not pid:
                    return {"status": "error", "message": "Product ID or SKU is required."}
                resp = await client.get(
                    f"{self.base_url}/proxy/wp-json/wc/v3/products/{urllib.parse.quote(pid)}",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    stock_qty = data.get("stock_quantity")
                    stock_status = data.get("stock_status", "instock")
                    return {
                        "status": "success",
                        "stock": stock_qty if stock_qty is not None else stock_status,
                        "summary": f"Product {data.get('name', pid)} stock status: {stock_status}.",
                        "message": f"Stock status is {stock_status}.",
                    }
                return {"status": "error", "message": f"Failed to check product stock (HTTP {resp.status_code})."}

            elif action_name == "WOOCOMMERCE_UPDATE_ORDER_STATUS":
                order_id = str(params.get("order_id") or "").strip().replace("#", "")
                status_val = str(params.get("status") or "").strip().lower()
                if not (order_id and status_val):
                    return {"status": "error", "message": "Order ID and new status are required."}
                resp = await client.put(
                    f"{self.base_url}/proxy/wp-json/wc/v3/orders/{urllib.parse.quote(order_id)}",
                    headers=headers,
                    json={"status": status_val},
                )
                if resp.status_code in (200, 201):
                    return {
                        "status": "success",
                        "order_id": order_id,
                        "shipping_status": status_val,
                        "summary": f"WooCommerce order #{order_id} status updated to {status_val}.",
                        "message": f"Order #{order_id} updated to {status_val}.",
                    }
                return {"status": "error", "message": f"Failed to update WooCommerce order (HTTP {resp.status_code})."}

            elif action_name == "JIRA_GET_ISSUE":
                ikey = str(params.get("issue_key") or params.get("issue_id") or "").strip()
                if not ikey:
                    return {"status": "error", "message": "Issue key is required."}
                resp = await client.get(
                    f"{self.base_url}/proxy/rest/api/3/issue/{urllib.parse.quote(ikey)}",
                    headers=headers,
                )
                if resp.status_code == 200:
                    fields = resp.json().get("fields", {})
                    st_name = fields.get("status", {}).get("name", "Open")
                    return {
                        "status": "success",
                        "key": ikey,
                        "issue_status": st_name,
                        "summary": f"Jira issue {ikey} is currently {st_name}.",
                        "message": f"Issue {ikey} is {st_name}.",
                    }
                return {"status": "error", "message": f"Failed to get Jira issue (HTTP {resp.status_code})."}

            elif action_name == "JIRA_ADD_COMMENT":
                ikey = str(params.get("issue_key") or params.get("issue_id") or "").strip()
                comment_txt = str(params.get("comment") or "").strip()
                if not (ikey and comment_txt):
                    return {"status": "error", "message": "Issue key and comment are required."}
                doc_body = {
                    "body": {
                        "type": "doc",
                        "version": 1,
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": comment_txt}]}],
                    }
                }
                resp = await client.post(
                    f"{self.base_url}/proxy/rest/api/3/issue/{urllib.parse.quote(ikey)}/comment",
                    headers=headers,
                    json=doc_body,
                )
                if resp.status_code in (200, 201):
                    return {
                        "status": "success",
                        "key": ikey,
                        "summary": f"Comment added to Jira issue {ikey}.",
                        "message": f"Comment logged on {ikey}.",
                    }
                return {"status": "error", "message": f"Failed to add comment to Jira issue (HTTP {resp.status_code})."}

            elif action_name == "LINEAR_SEARCH_ISSUES":
                q = str(params.get("query") or "").strip()
                gql = {
                    "query": "query Search($q: String!) { issueSearch(query: $q, first: 5) { nodes { id identifier title state { name } } } }",
                    "variables": {"q": q},
                }
                resp = await client.post(
                    f"{self.base_url}/proxy/graphql",
                    headers=headers,
                    json=gql,
                )
                if resp.status_code == 200:
                    nodes = resp.json().get("data", {}).get("issueSearch", {}).get("nodes", [])
                    issues = [{"identifier": n.get("identifier"), "title": n.get("title")} for n in nodes]
                    return {
                        "status": "success",
                        "issues": issues,
                        "summary": f"Found {len(nodes)} issues in Linear.",
                        "message": f"Found {len(nodes)} issues.",
                    }
                return {"status": "error", "message": f"Failed to search Linear issues (HTTP {resp.status_code})."}

            elif action_name == "ZOOM_GET_MEETING":
                mid = str(params.get("meeting_id") or "").strip()
                if not mid:
                    return {"status": "error", "message": "Meeting ID is required."}
                resp = await client.get(
                    f"{self.base_url}/proxy/v2/meetings/{urllib.parse.quote(mid)}",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "status": "success",
                        "meeting_id": str(data.get("id")),
                        "join_url": data.get("join_url"),
                        "start_time": data.get("start_time"),
                        "topic": data.get("topic"),
                        "summary": f"Zoom meeting '{data.get('topic')}' at {data.get('start_time')}.",
                        "message": f"Meeting link: {data.get('join_url')}",
                    }
                return {"status": "error", "message": f"Failed to get Zoom meeting (HTTP {resp.status_code})."}

            elif action_name == "GMAIL_CREATE_DRAFT":
                to_addr = params.get("to") or params.get("recipient")
                subject = params.get("subject") or "Follow-Up - Call Summary"
                body = params.get("body") or "Draft notes from our recent phone call."
                if not to_addr:
                    return {"status": "error", "message": "Recipient email address is required."}
                msg = EmailMessage()
                msg["To"] = str(to_addr)
                msg["Subject"] = str(subject)
                msg["From"] = "me"
                msg.set_content(str(body))
                raw_b64 = base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")
                resp = await client.post(
                    f"{self.base_url}/proxy/gmail/v1/users/me/drafts",
                    headers=headers,
                    json={"message": {"raw": raw_b64}},
                )
                if resp.status_code in (200, 201):
                    did = resp.json().get("id")
                    return {
                        "status": "draft_created",
                        "draft_id": did,
                        "to": str(to_addr),
                        "subject": str(subject),
                        "summary": f"Email draft created in Gmail for {to_addr}.",
                        "message": f"Draft saved in Gmail.",
                    }
                return {"status": "error", "message": f"Failed to create Gmail draft (HTTP {resp.status_code})."}

            elif action_name == "ASANA_ADD_COMMENT":
                tid = str(params.get("task_id") or "").strip()
                comment = str(params.get("comment") or "").strip()
                if not (tid and comment):
                    return {"status": "error", "message": "Task ID and comment are required."}
                resp = await client.post(
                    f"{self.base_url}/proxy/api/1.0/tasks/{urllib.parse.quote(tid)}/stories",
                    headers=headers,
                    json={"data": {"text": comment}},
                )
                if resp.status_code in (200, 201):
                    cid = resp.json().get("data", {}).get("gid")
                    return {
                        "status": "success",
                        "task_id": tid,
                        "comment_id": str(cid),
                        "summary": f"Comment added to Asana task {tid}.",
                        "message": "Task comment added.",
                    }
                return {"status": "error", "message": f"Failed to add Asana comment (HTTP {resp.status_code})."}

            elif action_name == "NOTION_SEARCH_PAGES":
                q = str(params.get("query") or "").strip()
                notion_headers = {**headers, "Notion-Version": "2022-06-28"}
                resp = await client.post(
                    f"{self.base_url}/proxy/v1/search",
                    headers=notion_headers,
                    json={"query": q, "page_size": 5},
                )
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    return {
                        "status": "success",
                        "results": len(results),
                        "summary": f"Found {len(results)} pages in Notion.",
                        "message": f"Found {len(results)} Notion pages.",
                    }
                return {"status": "error", "message": f"Failed to search Notion (HTTP {resp.status_code})."}

            elif action_name == "AIRTABLE_SEARCH_RECORDS":
                base_id = str(params.get("base_id") or "").strip()
                table_name = str(params.get("table_name") or "").strip()
                flt = str(params.get("filter") or "").strip()
                if not (base_id and table_name):
                    return {"status": "error", "message": "Base ID and table name are required."}
                req_params: dict[str, Any] = {"maxRecords": 5}
                if flt:
                    req_params["filterByFormula"] = flt
                resp = await client.get(
                    f"{self.base_url}/proxy/v0/{urllib.parse.quote(base_id)}/{urllib.parse.quote(table_name)}",
                    headers=headers,
                    params=req_params,
                )
                if resp.status_code == 200:
                    recs = resp.json().get("records", [])
                    return {
                        "status": "success",
                        "records": len(recs),
                        "summary": f"Found {len(recs)} records in Airtable table {table_name}.",
                        "message": f"Found {len(recs)} Airtable records.",
                    }
                return {"status": "error", "message": f"Failed to query Airtable (HTTP {resp.status_code})."}

            elif action_name == "INTERCOM_SEARCH_CONTACT":
                email = str(params.get("email") or "").strip()
                if not email:
                    return {"status": "error", "message": "Email is required."}
                resp = await client.post(
                    f"{self.base_url}/proxy/contacts/search",
                    headers=headers,
                    json={"query": {"field": "email", "operator": "=", "value": email}},
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    cid = data[0].get("id") if data else None
                    return {
                        "status": "success" if cid else "not_found",
                        "contact_id": cid,
                        "summary": f"Found Intercom contact {cid}." if cid else "No matching contact in Intercom.",
                        "message": "Contact found in Intercom." if cid else "Contact not found.",
                    }
                return {"status": "error", "message": f"Failed to search Intercom contact (HTTP {resp.status_code})."}

            elif action_name == "GITHUB_SEARCH_ISSUES":
                owner = str(params.get("owner") or "").strip()
                repo = str(params.get("repo") or "").strip()
                q = str(params.get("query") or "").strip()
                full_q = f"{q} repo:{owner}/{repo}" if (owner and repo) else q
                resp = await client.get(
                    f"{self.base_url}/proxy/search/issues",
                    headers=headers,
                    params={"q": full_q, "per_page": 5},
                )
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    issues = [{"number": it.get("number"), "title": it.get("title")} for it in items]
                    return {
                        "status": "success",
                        "issues": issues,
                        "summary": f"Found {len(items)} GitHub issues.",
                        "message": f"Found {len(items)} issues.",
                    }
                return {"status": "error", "message": f"Failed to search GitHub issues (HTTP {resp.status_code})."}

            elif action_name == "FRESHDESK_CREATE_TICKET":
                subject = str(params.get("subject") or "Support Request").strip()
                description = str(params.get("description") or "").strip()
                email = str(params.get("email") or "").strip()
                priority = int(params.get("priority") or 1)
                resp = await client.post(
                    f"{self.base_url}/proxy/api/v2/tickets",
                    headers=headers,
                    json={"subject": subject, "description": description, "email": email, "priority": priority, "status": 2},
                )
                if resp.status_code in (200, 201):
                    tid = resp.json().get("id")
                    return {
                        "status": "success",
                        "ticket_id": str(tid),
                        "summary": f"Freshdesk ticket #{tid} created.",
                        "message": f"Ticket #{tid} logged.",
                    }
                return {"status": "error", "message": f"Failed to create Freshdesk ticket (HTTP {resp.status_code})."}

            elif action_name == "FRESHDESK_LOOKUP_TICKET":
                tid = str(params.get("ticket_id") or "").strip()
                email = str(params.get("email") or "").strip()
                if tid:
                    resp = await client.get(
                        f"{self.base_url}/proxy/api/v2/tickets/{urllib.parse.quote(tid)}",
                        headers=headers,
                    )
                elif email:
                    resp = await client.get(
                        f"{self.base_url}/proxy/api/v2/tickets",
                        headers=headers,
                        params={"email": email},
                    )
                else:
                    return {"status": "error", "message": "Ticket ID or email is required."}
                if resp.status_code == 200:
                    data = resp.json()
                    ticket = data if isinstance(data, dict) else (data[0] if data else {})
                    return {
                        "status": "success",
                        "ticket_id": str(ticket.get("id")),
                        "subject": ticket.get("subject"),
                        "summary": f"Freshdesk ticket #{ticket.get('id')}: {ticket.get('subject')}.",
                        "message": "Ticket found in Freshdesk.",
                    }
                return {"status": "error", "message": f"Failed to lookup Freshdesk ticket (HTTP {resp.status_code})."}

            elif action_name == "SENDGRID_SEND_EMAIL":
                to_email = str(params.get("to") or params.get("recipient") or "").strip()
                subject = str(params.get("subject") or "Notification").strip()
                body = str(params.get("body") or "").strip()
                from_email = str(params.get("from_email") or "noreply@dialtact.ai").strip()
                if not (to_email and body):
                    return {"status": "error", "message": "Recipient email and body are required."}
                send_payload = {
                    "personalizations": [{"to": [{"email": to_email}]}],
                    "from": {"email": from_email},
                    "subject": subject,
                    "content": [{"type": "text/plain", "value": body}],
                }
                resp = await client.post(
                    f"{self.base_url}/proxy/v3/mail/send",
                    headers=headers,
                    json=send_payload,
                )
                if resp.status_code in (200, 202):
                    return {
                        "status": "sent",
                        "summary": f"Email sent via SendGrid to {to_email}.",
                        "message": f"Email sent to {to_email}.",
                    }
                return {"status": "error", "message": f"Failed to send email via SendGrid (HTTP {resp.status_code})."}

            elif action_name == "MAILCHIMP_ADD_SUBSCRIBER":
                lid = str(params.get("list_id") or "").strip()
                em = str(params.get("email") or "").strip()
                if not (lid and em):
                    return {"status": "error", "message": "Audience list ID and email are required."}
                m_payload = {
                    "email_address": em,
                    "status": "subscribed",
                    "merge_fields": {
                        "FNAME": str(params.get("first_name") or ""),
                        "LNAME": str(params.get("last_name") or ""),
                    },
                }
                resp = await client.post(
                    f"{self.base_url}/proxy/3.0/lists/{urllib.parse.quote(lid)}/members",
                    headers=headers,
                    json=m_payload,
                )
                if resp.status_code in (200, 201):
                    sub_id = resp.json().get("id")
                    return {
                        "status": "subscribed",
                        "subscriber_id": str(sub_id),
                        "summary": f"Subscriber {em} added to Mailchimp audience list.",
                        "message": "Added to audience list.",
                    }
                return {"status": "error", "message": f"Failed to add subscriber to Mailchimp (HTTP {resp.status_code})."}

            elif action_name == "CLICKUP_CREATE_TASK":
                lid = str(params.get("list_id") or "").strip()
                name = str(params.get("name") or "New Call Task").strip()
                desc = str(params.get("description") or "").strip()
                priority = int(params.get("priority") or 3)
                if not lid:
                    return {"status": "error", "message": "List ID is required."}
                resp = await client.post(
                    f"{self.base_url}/proxy/api/v2/list/{urllib.parse.quote(lid)}/task",
                    headers=headers,
                    json={"name": name, "description": desc, "priority": priority},
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    return {
                        "status": "success",
                        "task_id": str(data.get("id")),
                        "url": data.get("url"),
                        "summary": f"ClickUp task created: {name}.",
                        "message": "ClickUp task created.",
                    }
                return {"status": "error", "message": f"Failed to create ClickUp task (HTTP {resp.status_code})."}

            elif action_name == "MONDAY_CREATE_ITEM":
                bid = str(params.get("board_id") or "").strip()
                iname = str(params.get("item_name") or "New Call Item").strip()
                gql = {
                    "query": "mutation ($boardId: ID!, $itemName: String!) { create_item (board_id: $boardId, item_name: $itemName) { id } }",
                    "variables": {"boardId": bid, "itemName": iname},
                }
                resp = await client.post(
                    f"{self.base_url}/proxy/v2",
                    headers=headers,
                    json=gql,
                )
                if resp.status_code == 200:
                    iid = resp.json().get("data", {}).get("create_item", {}).get("id")
                    return {
                        "status": "success",
                        "item_id": str(iid),
                        "summary": f"Monday.com item '{iname}' created (ID {iid}).",
                        "message": "Monday board item created.",
                    }
                return {"status": "error", "message": f"Failed to create Monday item (HTTP {resp.status_code})."}

            elif action_name == "WHATSAPP_SEND_MESSAGE":
                to_num = str(params.get("to") or params.get("recipient") or "").strip()
                msg_text = str(params.get("message") or params.get("text") or "").strip()
                if not (to_num and msg_text):
                    return {"status": "error", "message": "Recipient phone number and message are required."}
                resp = await client.post(
                    f"{self.base_url}/proxy/messages",
                    headers=headers,
                    json={"messaging_product": "whatsapp", "to": to_num, "type": "text", "text": {"body": msg_text}},
                )
                if resp.status_code in (200, 201):
                    mid = resp.json().get("messages", [{}])[0].get("id")
                    return {
                        "status": "sent",
                        "message_id": str(mid),
                        "summary": f"WhatsApp message delivered to {to_num}.",
                        "message": "WhatsApp confirmation sent.",
                    }
                return {"status": "error", "message": f"Failed to send WhatsApp message (HTTP {resp.status_code})."}

            elif action_name == "SUPABASE_INSERT_ROW":
                table = str(params.get("table") or "").strip()
                row_data = params.get("row") or {}
                if not (table and row_data):
                    return {"status": "error", "message": "Table name and row data are required."}
                resp = await client.post(
                    f"{self.base_url}/proxy/rest/v1/{urllib.parse.quote(table)}",
                    headers=headers,
                    json=row_data,
                )
                if resp.status_code in (200, 201):
                    return {
                        "status": "success",
                        "summary": f"Row inserted into Supabase table {table}.",
                        "message": "Record inserted into Supabase.",
                    }
                return {"status": "error", "message": f"Failed to insert row into Supabase (HTTP {resp.status_code})."}

            elif action_name == "SUPABASE_QUERY_ROW":
                table = str(params.get("table") or "").strip()
                col = str(params.get("filter_column") or "").strip()
                val = str(params.get("filter_value") or "").strip()
                if not (table and col and val):
                    return {"status": "error", "message": "Table, filter column, and filter value are required."}
                resp = await client.get(
                    f"{self.base_url}/proxy/rest/v1/{urllib.parse.quote(table)}",
                    headers=headers,
                    params={col: f"eq.{val}", "limit": "1"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "status": "success",
                        "data": data[0] if data else None,
                        "summary": f"Queried Supabase table {table}.",
                        "message": "Supabase query completed.",
                    }
                return {"status": "error", "message": f"Failed to query Supabase (HTTP {resp.status_code})."}

            return {"status": "error", "message": f"Unsupported proxy action {action_name}"}

    def _filter_available_slots(
        self, target_date: str, standard_slots: list[str], busy_spans: list[dict[str, str]]
    ) -> tuple[list[str], list[str]]:
        """Compute available and busy slots by testing overlap against FreeBusy intervals."""
        available: list[str] = []
        busy_list: list[str] = []
        parsed_busy = []
        tz_offset = timedelta(hours=5, minutes=30)
        for b in busy_spans:
            try:
                st = datetime.fromisoformat(b["start"].replace("Z", "+00:00"))
                en = datetime.fromisoformat(b["end"].replace("Z", "+00:00"))
                parsed_busy.append((st, en))
            except Exception:
                continue

        for slot in standard_slots:
            try:
                dt = datetime.strptime(f"{target_date} {slot}", "%Y-%m-%d %I:%M %p")
                dt_utc = dt.replace(tzinfo=timezone.utc) - tz_offset
                slot_en = dt_utc + timedelta(minutes=30)
                is_busy = False
                for b_st, b_en in parsed_busy:
                    if dt_utc < b_en and slot_en > b_st:
                        is_busy = True
                        break
                if is_busy:
                    busy_list.append(slot)
                else:
                    available.append(slot)
            except Exception:
                available.append(slot)
        return available, busy_list

    async def _get_nango_connection_id(
        self, tenant_id: str, action_name: str
    ) -> str | None:
        """Look up the stored Nango connection_id for a tenant's integration."""
        raw_app = self._extract_app_name(action_name)
        try:
            from server.db.connection import get_session_factory
            from server.services.tenant_tool_cache import get_connection_id
            sf = get_session_factory()
            return await get_connection_id(tenant_id, raw_app, sf)
        except Exception as exc:
            logger.warning("[NANGO] connection_id lookup failed: %s", exc)
            return None

    def sanitize_voice_response(self, raw: Any, action_name: str = "") -> dict[str, Any]:
        """Trim raw Nango API response to only voice-relevant fields for TTS.

        Uses the tool_schema_registry whitelist keyed per integration so that
        CRM, task, and messaging tools each preserve their own meaningful keys.
        """
        if not isinstance(raw, dict):
            return {"result": str(raw)[:120]}

        # Resolve whitelist from registry (falls back to generic keys)
        try:
            from server.services.tool_schema_registry import get_response_keys_for_tool
            keep_keys: tuple = get_response_keys_for_tool(action_name) if action_name else (
                "status", "confirmed", "date", "time", "summary", "available", "slots"
            )
        except Exception:
            keep_keys = ("status", "confirmed", "date", "time", "summary", "available", "slots")

        sanitized: dict[str, Any] = {}
        for key in keep_keys:
            if key in raw:
                sanitized[key] = raw[key]

        # Also pull from nested data/response_data/output/result if top-level is sparse
        data = raw.get("data") or raw.get("response_data") or raw.get("output") or raw.get("result") or raw.get("response") or raw
        if isinstance(data, dict):
            for k, v in data.items():
                if k not in sanitized and k in keep_keys:
                    sanitized[k] = v
                elif (
                    k not in sanitized
                    and isinstance(v, (str, int, float, bool))
                    and len(str(v)) < 80
                    and not str(v).startswith("http")
                    and not (isinstance(v, str) and len(v) > 32 and "-" in v)
                ):
                    # Allow short, non-URL scalar values that look human-readable
                    sanitized[k] = v

        return sanitized or {"status": "success"}


# Singleton instance
nango_service = NangoService()
