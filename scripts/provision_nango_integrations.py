"""Create or update every catalog integration in the (self-hosted) Nango instance.

API-key / basic-auth providers need nothing else: tenants enter their own key in
the Connect form. OAuth providers need YOUR OAuth app for that provider (self-
hosted Nango has no shared developer apps). Put its credentials in .env:

    NANGO_OAUTH_<APP>_CLIENT_ID / NANGO_OAUTH_<APP>_CLIENT_SECRET
    e.g. NANGO_OAUTH_CALENDLY_CLIENT_ID, NANGO_OAUTH_TODOIST_CLIENT_SECRET

Google Calendar and Gmail fall back to GOOGLE_OAUTH_CLIENT_ID / _SECRET. In each
provider's OAuth app register the redirect URL  <NANGO_PUBLIC_URL>/oauth/callback.

Scopes are the least each integration's actions need (see SCOPES). Re-running is
safe: existing integrations are updated in place, never duplicated.

    python scripts/provision_nango_integrations.py            # report only
    python scripts/provision_nango_integrations.py --apply
"""
import argparse
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.config.env import get_settings  # noqa: E402
from server.routes.integrations_catalog import CATALOG_INTEGRATIONS  # noqa: E402
from server.services.nango_service import nango_service  # noqa: E402

# Least privilege for the actions in tool_schema_registry / nango_service.
SCOPES: dict[str, str] = {
    "google-calendar": "https://www.googleapis.com/auth/calendar.events.owned,"
                       "https://www.googleapis.com/auth/calendar.events.freebusy,"
                       "https://www.googleapis.com/auth/calendar.calendars.readonly",
    # gmail.compose (drafts) is a Google "restricted" scope: fine for an app in
    # Testing with listed test users, needs a CASA review before public launch.
    "google-mail": "https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/gmail.compose",
    # Read and append rows in the sheet the tenant names (sensitive, not restricted).
    "google-sheet": "https://www.googleapis.com/auth/spreadsheets",
    "calendly": "users:read,event_types:read,scheduled_events:write",
    "todoist": "data:read_write",
    "hubspot": "oauth,crm.objects.contacts.read,crm.objects.contacts.write,crm.objects.deals.read,crm.objects.deals.write",
    "salesforce": "api,refresh_token",
    "zendesk": "read,write",
    "jira": "read:jira-work,write:jira-work,offline_access",
    "linear": "read,issues:create",
    "zoom": "meeting:write:meeting,meeting:read:meeting",
    "slack": "chat:write,channels:read,groups:read",
    "airtable": "data.records:read,data.records:write,schema.bases:read",
    "asana": "default",
    "monday": "boards:read,boards:write",
    "github": "repo",
    "intercom": "",
    "notion": "",
    "clickup": "",
    "mailchimp": "",
}
GOOGLE_FALLBACK = {"google-calendar", "google-mail", "google-sheet"}


def _creds(app: str, provider: str) -> tuple[str | None, str | None]:
    cid = os.environ.get(f"NANGO_OAUTH_{app}_CLIENT_ID")
    secret = os.environ.get(f"NANGO_OAUTH_{app}_CLIENT_SECRET")
    if not (cid and secret) and provider in GOOGLE_FALLBACK:
        settings = get_settings()
        cid = cid or os.environ.get("GOOGLE_OAUTH_CLIENT_ID") or getattr(settings, "google_oauth_client_id", None)
        secret = secret or os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET") or getattr(settings, "google_oauth_client_secret", None)
    return cid, secret


def main(apply: bool) -> int:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    settings = get_settings()
    base, key = settings.nango_base_url.rstrip("/"), settings.nango_secret_key
    if not key:
        print("NANGO_SECRET_KEY is not set.")
        return 1
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    callback = f"{os.environ.get('NANGO_PUBLIC_URL') or base}/oauth/callback"
    with httpx.Client(timeout=20) as client:
        existing = {i["unique_key"] for i in client.get(f"{base}/integrations", headers=headers).json().get("data", [])}
        missing_oauth: list[str] = []
        for row in CATALOG_INTEGRATIONS:
            app = row["id"]
            unique_key = nango_service.get_provider_key(app)
            provider = client.get(f"{base}/providers/{unique_key}", headers=headers).json().get("data") or {}
            mode = provider.get("auth_mode")
            if not mode:
                print(f"  {app:15} {unique_key:20} provider unknown to this Nango version")
                continue
            body: dict = {"unique_key": unique_key, "provider": unique_key, "display_name": row["name"]}
            if mode.startswith("OAUTH"):
                cid, secret = _creds(app, unique_key)
                if not (cid and secret):
                    missing_oauth.append(app)
                    print(f"  {app:15} {unique_key:20} {mode:8} SKIPPED: no OAuth app credentials")
                    continue
                body["credentials"] = {"type": mode, "client_id": cid, "client_secret": secret, "scopes": SCOPES.get(unique_key, "")}
            action = "update" if unique_key in existing else "create"
            if apply:
                if action == "create":
                    res = client.post(f"{base}/integrations", headers=headers, json=body)
                else:
                    res = client.patch(f"{base}/integrations/{unique_key}", headers=headers,
                                       json={k: v for k, v in body.items() if k not in {"unique_key", "provider"}})
                status = "ok" if res.status_code < 300 else f"FAILED {res.status_code} {res.text[:160]}"
            else:
                status = "would " + action
            print(f"  {app:15} {unique_key:20} {mode:8} {status}")
    if missing_oauth:
        print(f"\nOAuth apps still needed for: {', '.join(missing_oauth)}")
        print(f"Register this redirect URL in each: {callback}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true")
    sys.exit(main(parser.parse_args().apply))
