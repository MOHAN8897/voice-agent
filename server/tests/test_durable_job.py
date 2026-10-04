"""Unit tests for DurableJob schema and lifecycle."""
from __future__ import annotations

from server.call.durable_job import DurableJob, JobStatus


def test_durable_job_defaults():
    job = DurableJob(
        call_id="call-abc",
        tenant_id="tenant-123",
        job_type="post_call_summary",
    )
    assert job.status == JobStatus.PENDING
    assert job.attempt_count == 0
    assert job.idempotency_key == "post_call_summary:call-abc"
    assert job.job_id is not None


def test_durable_job_idempotency_with_action():
    job = DurableJob(
        call_id="call-abc",
        tenant_id="tenant-123",
        job_type="composio_action",
        payload={"action_name": "hubspot_sync"},
    )
    assert job.idempotency_key == "composio_action:call-abc:hubspot_sync"


def test_durable_job_serialization_roundtrip():
    job = DurableJob(
        call_id="call-abc",
        tenant_id="tenant-123",
        job_type="recording_upload",
        payload={"bucket": "voxly-archives"},
    )
    data = job.to_dict()
    assert data["status"] == "pending"

    reconstructed = DurableJob.from_dict(data)
    assert reconstructed.job_id == job.job_id
    assert reconstructed.status == JobStatus.PENDING
    assert reconstructed.payload == {"bucket": "voxly-archives"}


def test_durable_job_retry_backoff_and_dead_letter():
    job = DurableJob(
        call_id="call-abc",
        tenant_id="tenant-123",
        job_type="composio_action",
        max_attempts=3,
    )

    # Attempt 1 fail
    job.mark_failed("Network timeout", backoff_base_sec=10.0)
    assert job.attempt_count == 1
    assert job.status == JobStatus.FAILED
    assert job.error_message == "Network timeout"

    # Attempt 2 fail
    job.mark_failed("Rate limit", backoff_base_sec=10.0)
    assert job.attempt_count == 2
    assert job.status == JobStatus.FAILED

    # Attempt 3 fail -> dead letter
    job.mark_failed("Permanent 403", backoff_base_sec=10.0)
    assert job.attempt_count == 3
    assert job.status == JobStatus.DEAD_LETTER

    # Recovery test
    job.mark_completed()
    assert job.status == JobStatus.COMPLETED
    assert job.error_message is None
