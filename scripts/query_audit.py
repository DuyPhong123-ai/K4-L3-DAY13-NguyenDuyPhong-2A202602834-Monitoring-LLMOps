from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.audit import AUDIT_LOG_PATH, enforce_retention, query_audit_events


def main() -> int:
    parser = argparse.ArgumentParser(description="Query the separate audit JSONL stream")
    parser.add_argument("--path", type=Path, default=AUDIT_LOG_PATH)
    parser.add_argument("--correlation-id")
    parser.add_argument("--event")
    parser.add_argument("--outcome", choices=("success", "failure"))
    parser.add_argument("--enforce-retention", action="store_true")
    args = parser.parse_args()
    if args.enforce_retention:
        print(json.dumps({"retention": enforce_retention(args.path)}, ensure_ascii=False))
    records = query_audit_events(
        args.path,
        correlation_id=args.correlation_id,
        event=args.event,
        outcome=args.outcome,
    )
    for record in records:
        print(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    print(json.dumps({"matched": len(records)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
