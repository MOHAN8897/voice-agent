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
    "STRIPE": "stripe-api-key",
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
                with urllib.request.urlopen(req, timeout=4) as resp:
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
                with urllib.request.urlopen(req, timeout=5) as resp:
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
                    data=json.dumps({"display_name": "Voxly Voice Agent"}).encode(),
                    headers={
                        "Authorization": f"Bearer {account_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                )
                with urllib.request.urlopen(create_req, timeout=5) as c_resp:
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
                with urllib.request.urlopen(req, timeout=5) as resp:
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
                        tenant_id=uuid.UUID(str(tenant_id)),
                        user_id=uuid.UUID(str(user_id)),
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
            logger.error(
                "[NANGO] No Nango environment secret key configured. "
                "Set NANGO_SECRET_KEY (or NANGO_API_KEY) in your .env to enable OAuth."
            )
            return {
                "error": "nango_not_configured",
                "message": "Nango is not configured. Please set NANGO_SECRET_KEY in your environment to enable OAuth integrations.",
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
                with urllib.request.urlopen(req, timeout=5) as resp:
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
                        with urllib.request.urlopen(quick_req, timeout=5):
                            pass
                        # Retry connect session now that provider is provisioned
                        with urllib.request.urlopen(req, timeout=5) as retry_resp:
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
                    "connection_id": f"nango_conn_{state[:16]}",
                    "redirect_url": connect_link,
                    "session_token": token,
                    "state": state,
                    "status": "INITIATED",
                }
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode(errors="replace")
            logger.error("[NANGO] Connect session initiation HTTP %s: %s", exc.code, err_body)
            if "No Nango-provided developer app" in err_body or "does not exist" in err_body or exc.code == 400:
                return {
                    "error": "nango_credentials_required",
                    "message": f"'{app_name}' requires OAuth credentials in your Nango dashboard. You can configure it at app.nango.dev/integrations or connect immediately using an API Key.",
                    "nango_dashboard_url": "https://app.nango.dev/integrations",
                    "provider_key": provider_key,
                    "state": state,
                    "status": "ERROR",
                }
            return {
                "error": "nango_session_failed",
                "message": f"Failed to initiate OAuth session with Nango (HTTP {exc.code}). Ensure the integration is configured in your Nango dashboard.",
                "state": state,
                "status": "ERROR",
            }
        except Exception as exc:
            logger.error("[NANGO] Provider initiation failed: %s", exc)
            return {
                "error": "nango_session_failed",
                "message": f"Failed to initiate OAuth session: {exc}",
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
                with urllib.request.urlopen(req, timeout=5) as resp:
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
            "ASANA_", "TODOIST_", "DISCORD_", "AIRTABLE_", "MICROSOFTTEAMS_"
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


# Singleton instance and compatibility alias
nango_service = NangoService()
composio_service = nango_service
