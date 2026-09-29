from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.audit import query_audit_events, write_audit_event


def main() -> int:
    now = datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "audit.jsonl"
        write_audit_event(
            event="incident_control",
            action="enable",
            outcome="success",
            actor_id_hash="dc9b2ec8da9d",
            correlation_id="req-deadbeef",
            resource="incident/expired-demo",
            path=path,
            now=now - timedelta(days=31),
        )
        current = write_audit_event(
            event="incident_control",
            action="disable",
            outcome="success",
            actor_id_hash="dc9b2ec8da9d",
            correlation_id="req-a1b2c3d4",
            resource="incident/rag_slow",
            metadata={"note": "contact student@example.com"},
            path=path,
            now=now,
        )
        matches = query_audit_events(path, correlation_id="req-a1b2c3d4")
        all_records = query_audit_events(path)

    print("Audit schema: config/audit_schema.json (version 1.0)")
    print("Production stream: data/audit.jsonl")
    print("Retention: 30 days; expired or malformed records are removed")
    print("Demo inserted: 2 records (one 31 days old, one current)")
    print(f"Records after automatic retention: {len(all_records)}")
    print("Query: correlation_id=req-a1b2c3d4")
    print(f"Matched: {len(matches)}")
    print(json.dumps(current, ensure_ascii=False, separators=(",", ":")))
    serialized = json.dumps(current, ensure_ascii=False)
    if len(all_records) != 1 or len(matches) != 1 or "student@example.com" in serialized:
        print("Audit demo: FAIL", file=sys.stderr)
        return 1
    print("Audit demo: PASS (retention enforced, query matched, PII scrubbed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
