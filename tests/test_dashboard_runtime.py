from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.dashboard import calculate_dashboard, load_recent_records, render_dashboard


def test_dashboard_reads_logs_and_renders_six_panels(tmp_path: Path) -> None:
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    records = [
        {"ts": timestamp, "event": "request_received"},
        {
            "ts": timestamp,
            "event": "response_sent",
            "latency_ms": 200,
            "ttft_ms": 50,
            "cost_usd": 0.002,
            "tokens_in": 30,
            "tokens_out": 100,
            "quality_score": 0.8,
            "tool_success": True,
        },
    ]
    log_path = tmp_path / "logs.jsonl"
    log_path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

    recent = load_recent_records(log_path)
    dashboard = calculate_dashboard(recent)
    page = render_dashboard(log_path=log_path)

    assert dashboard["latency"]["P95"] == 200
    assert dashboard["errors"]["retrieval_success"] == 100
    assert page.count('<section class="panel">') == 6
    assert "last 60 minutes" in page
    assert "SLO / threshold" in page
    assert "Latency percentiles and TTFT" in page
