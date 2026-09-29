from __future__ import annotations

import json
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app import main as main_module
from app.audit import enforce_retention, query_audit_events, write_audit_event


def test_audit_event_is_scrubbed_and_queryable(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"

    record = write_audit_event(
        event="incident_control",
        action="enable",
        outcome="success",
        actor_id_hash="dc9b2ec8da9d",
        correlation_id="req-1234abcd",
        resource="incident/rag_slow",
        metadata={"note": "contact student@example.com or 0901234567"},
        path=path,
    )

    assert record["schema_version"] == "1.0"
    assert record["event_id"].startswith("audit-")
    serialized = path.read_text(encoding="utf-8")
    assert "student@example.com" not in serialized
    assert "0901234567" not in serialized
    assert "REDACTED_EMAIL" in serialized
    assert query_audit_events(path, correlation_id="req-1234abcd") == [record]


def test_audit_retention_removes_expired_and_malformed_records(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    old_record = {
        "ts": (now - timedelta(days=31)).isoformat().replace("+00:00", "Z"),
        "event": "old",
    }
    current_record = {
        "ts": (now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        "event": "current",
    }
    path.write_text(
        json.dumps(old_record) + "\n" + "not-json\n" + json.dumps(current_record) + "\n",
        encoding="utf-8",
    )

    result = enforce_retention(path, retention_days=30, now=now)

    assert result == {"kept": 1, "removed": 2}
    assert query_audit_events(path, event="current") == [current_record]


def test_audit_query_filters_outcome(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    for outcome in ("success", "failure"):
        write_audit_event(
            event="incident_control",
            action="enable",
            outcome=outcome,
            actor_id_hash="dc9b2ec8da9d",
            correlation_id="req-1234abcd",
            resource="incident/rag_slow",
            path=path,
        )

    assert len(query_audit_events(path, outcome="failure")) == 1


def test_incident_control_endpoint_writes_correlated_audit_event(monkeypatch) -> None:
    captured: list[dict] = []
    monkeypatch.setattr(main_module, "write_audit_event", lambda **kwargs: captured.append(kwargs))

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/incidents/rag_slow/disable",
                headers={"x-request-id": "req-a1b2c3d4", "x-actor-id": "operator-01"},
            )

    response = asyncio.run(request())

    assert response.status_code == 200
    assert captured[0]["event"] == "incident_control"
    assert captured[0]["action"] == "disable"
    assert captured[0]["outcome"] == "success"
    assert captured[0]["correlation_id"] == "req-a1b2c3d4"
    assert captured[0]["actor_id_hash"] != "operator-01"
