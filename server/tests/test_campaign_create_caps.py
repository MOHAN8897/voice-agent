"""Campaign create concurrency / retry_rules caps — no DB required."""
from __future__ import annotations

from pydantic import ValidationError

from server.routes.campaigns import CampaignCreate


def test_campaign_create_accepts_retry_fields():
    body = CampaignCreate.model_validate(
        {
            "name": "Bulk",
            "agentId": "00000000-0000-0000-0000-000000000001",
            "concurrency": 99,
            "maxAttempts": 4,
            "retryDelayMinutes": 45,
            "fromE164": "+14155552671",
            "consentConfirmed": True,
        }
    )
    assert body.concurrency == 99  # route clamps; schema only stores intent
    assert body.max_attempts == 4
    assert body.retry_delay_minutes == 45
    assert body.from_e164 == "+14155552671"


def test_campaign_create_requires_agent():
    try:
        CampaignCreate.model_validate({"name": "x"})
        assert False, "expected validation error"
    except ValidationError:
        pass
