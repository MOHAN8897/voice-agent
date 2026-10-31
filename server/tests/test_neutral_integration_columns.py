from server.db.models.integration_models import TenantIntegration
from server.db.models.phase5_models import DialAttempt, PhoneNumber


def test_active_models_use_neutral_carrier_and_connection_columns():
    assert "carrier_number_id" in PhoneNumber.__table__.columns
    assert "plivo_number_id" not in PhoneNumber.__table__.columns
    assert "carrier_call_uuid" in DialAttempt.__table__.columns
    assert "plivo_call_uuid" not in DialAttempt.__table__.columns
    assert "connection_id" in TenantIntegration.__table__.columns
    assert "composio_connection_id" not in TenantIntegration.__table__.columns
    assert not hasattr(TenantIntegration, "composio_connection_id")
