from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .pii import scrub_text

AUDIT_LOG_PATH = Path(os.getenv("AUDIT_LOG_PATH", "data/audit.jsonl"))
AUDIT_RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS", "30"))
SCHEMA_VERSION = "1.0"


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def enforce_retention(
    path: Path = AUDIT_LOG_PATH,
    *,
    retention_days: int = AUDIT_RETENTION_DAYS,
    now: datetime | None = None,
) -> dict[str, int]:
    if not path.exists():
        return {"kept": 0, "removed": 0}
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
    kept: list[str] = []
    removed = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
            if _parse_timestamp(record["ts"]) >= cutoff:
                kept.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            else:
                removed += 1
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            removed += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return {"kept": len(kept), "removed": removed}


def write_audit_event(
    *,
    event: str,
    action: str,
    outcome: str,
    actor_id_hash: str,
    correlation_id: str,
    resource: str,
    metadata: dict[str, Any] | None = None,
    path: Path = AUDIT_LOG_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    timestamp = now or datetime.now(timezone.utc)
    enforce_retention(path, now=timestamp)
    record = _scrub(
        {
            "schema_version": SCHEMA_VERSION,
            "event_id": f"audit-{uuid.uuid4().hex[:12]}",
            "ts": timestamp.isoformat().replace("+00:00", "Z"),
            "event": event,
            "action": action,
            "outcome": outcome,
            "actor_id_hash": actor_id_hash,
            "correlation_id": correlation_id,
            "resource": resource,
            "metadata": metadata or {},
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    return record


def query_audit_events(
    path: Path = AUDIT_LOG_PATH,
    *,
    correlation_id: str | None = None,
    event: str | None = None,
    outcome: str | None = None,
) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    matches: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if correlation_id and record.get("correlation_id") != correlation_id:
            continue
        if event and record.get("event") != event:
            continue
        if outcome and record.get("outcome") != outcome:
            continue
        matches.append(record)
    return matches
