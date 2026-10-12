"""Dialtact.com Domain & Carrier Webhook Synchronization Script.

Uses GoDaddy API to manage dialtact.com DNS, verifies Cloudflare named tunnel routing,
and coordinates Vobiz carrier application webhooks.

Usage:
  python scripts/sync_dialtact_domain.py --status
  python scripts/sync_dialtact_domain.py --sync-records
  python scripts/sync_dialtact_domain.py --update-vobiz
  python scripts/sync_dialtact_domain.py --set-nameservers "ns1.cloudflare.com,ns2.cloudflare.com"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

from dotenv import dotenv_values

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(REPO_ROOT, ".env")

TUNNEL_TARGET = "28f535f4-d6d1-45b3-a8fc-266b3d9c1f66.cfargotunnel.com"
DOMAIN = "dialtact.com"


def get_godaddy_token() -> str:
    env = dotenv_values(ENV_PATH)
    token = env.get("godaddy_apikey", "") or os.getenv("godaddy_apikey", "")
    if not token:
        raise ValueError("Missing godaddy_apikey in .env or environment")
    return token.strip()


def godaddy_request(
    method: str,
    endpoint: str,
    data: Any = None,
) -> Any:
    token = get_godaddy_token()
    url = f"https://api.godaddy.com{endpoint}"
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        err_msg = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GoDaddy API {exc.code} for {endpoint}: {err_msg}") from exc


def get_domain_status() -> dict[str, Any]:
    info = godaddy_request("GET", f"/v1/domains/{DOMAIN}")
    records = godaddy_request("GET", f"/v1/domains/{DOMAIN}/records")
    return {
        "domain": info.get("domain", DOMAIN),
        "status": info.get("status"),
        "locked": info.get("locked"),
        "nameservers": info.get("nameServers", []),
        "records": records,
    }


def sync_tunnel_cnames() -> None:
    print(f"Syncing CNAME records for {DOMAIN} to Cloudflare tunnel ({TUNNEL_TARGET})...")
    records = [
        {"type": "CNAME", "name": "api-dev", "data": TUNNEL_TARGET, "ttl": 600},
        {"type": "CNAME", "name": "app-dev", "data": TUNNEL_TARGET, "ttl": 600},
        {"type": "CNAME", "name": "api", "data": TUNNEL_TARGET, "ttl": 600},
        {"type": "CNAME", "name": "app", "data": TUNNEL_TARGET, "ttl": 600},
    ]
    godaddy_request("PATCH", f"/v1/domains/{DOMAIN}/records", data=records)
    print("Successfully patched CNAME records on GoDaddy:")
    for r in records:
        print(f"  {r['name']}.{DOMAIN} -> {r['data']}")


def update_nameservers(nameservers: list[str]) -> None:
    ns_cleaned = [ns.strip() for ns in nameservers if ns.strip()]
    if len(ns_cleaned) < 2:
        raise ValueError("At least 2 nameservers are required")
    print(f"Updating {DOMAIN} nameservers on GoDaddy to: {ns_cleaned}")
    # GoDaddy PATCH /v1/domains/{domain} accepts nameServers
    godaddy_request("PATCH", f"/v1/domains/{DOMAIN}", data={"nameServers": ns_cleaned})
    print("Nameserver update request submitted to GoDaddy successfully.")


async def update_vobiz_urls(target_domain: str = "api-dev.dialtact.com") -> None:
    from server.services.vobiz_client import VobizClient

    client = VobizClient()
    if not client.configured:
        print("Vobiz not configured; skipping Vobiz update.")
        return

    ans_url = f"https://{target_domain}/api/vobiz/answer"
    hup_url = f"https://{target_domain}/api/vobiz/hangup"
    fb_url = f"https://{target_domain}/api/vobiz/fallback"

    print(f"Updating Vobiz application callback webhooks to {ans_url}...")
    try:
        res = await client.update_application(
            answer_url=ans_url,
            hangup_url=hup_url,
            fallback_answer_url=fb_url,
        )
        print("Vobiz application update successful:", res)
    except Exception as exc:
        print(f"Vobiz update notice: {exc}")
        print("Carrier requires verified public SSL before accepting new webhook URL.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dialtact.com DNS & Carrier Sync Tool")
    parser.add_argument("--status", action="store_true", help="Print domain, nameserver, and DNS status")
    parser.add_argument("--sync-records", action="store_true", help="Sync CNAME records on GoDaddy")
    parser.add_argument("--update-vobiz", action="store_true", help="Update Vobiz application callback URLs")
    parser.add_argument("--set-nameservers", type=str, help="Comma-separated nameservers to set on GoDaddy")

    args = parser.parse_args()

    if args.set_nameservers:
        ns_list = args.set_nameservers.split(",")
        update_nameservers(ns_list)
        return

    if args.sync_records:
        sync_tunnel_cnames()
        return

    if args.update_vobiz:
        asyncio.run(update_vobiz_urls())
        return

    # Default to status
    status = get_domain_status()
    print("=" * 60)
    print(f"DOMAIN: {status['domain']} (Status: {status['status']}, Locked: {status['locked']})")
    print(f"Active Nameservers ({len(status['nameservers'])}):")
    for ns in status["nameservers"]:
        print(f"  * {ns}")
    print("\nDNS Records:")
    for r in status["records"]:
        print(f"  {r.get('type'):<6} {r.get('name'):<16} -> {r.get('data')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
