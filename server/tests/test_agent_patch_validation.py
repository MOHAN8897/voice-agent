"""The console's agent settings save rejects values the runtime cannot honour."""
import pytest
from pydantic import ValidationError

from server.routes.agents import PatchAgentBody


def test_status_is_live_or_paused_only():
    assert PatchAgentBody(status="paused").status == "paused"
    with pytest.raises(ValidationError):
        PatchAgentBody(status="deleted")


def test_name_must_not_be_blank_or_huge():
    with pytest.raises(ValidationError):
        PatchAgentBody(name="")
    with pytest.raises(ValidationError):
        PatchAgentBody(name="x" * 81)
