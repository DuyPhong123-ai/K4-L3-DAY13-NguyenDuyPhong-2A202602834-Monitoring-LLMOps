from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import yaml

from .logging_config import LOG_PATH
from .metrics import percentile

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "dashboard.yaml"


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def load_recent_records(log_path: Path, minutes: int = 60) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    records: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        timestamp = _parse_timestamp(record.get("ts"))
        if timestamp is not None and timestamp >= cutoff:
            records.append(record)
    return records


def calculate_dashboard(records: list[dict[str, Any]], minutes: int = 60) -> dict[str, Any]:
    requests = [record for record in records if record.get("event") == "request_received"]
    responses = [record for record in records if record.get("event") == "response_sent"]
    failures = [record for record in records if record.get("event") == "request_failed"]

    latencies = [int(record["latency_ms"]) for record in responses if record.get("latency_ms") is not None]
    ttfts = [int(record["ttft_ms"]) for record in responses if record.get("ttft_ms") is not None]
    costs = [float(record["cost_usd"]) for record in responses if record.get("cost_usd") is not None]
    qualities = [float(record["quality_score"]) for record in responses if record.get("quality_score") is not None]

    tool_results = [record.get("tool_success") for record in records if record.get("tool_success") is not None]
    retrieval_success = (
        100 * sum(result is True for result in tool_results) / len(tool_results)
        if tool_results
        else 100.0
    )
    error_rate = 100 * len(failures) / len(requests) if requests else 0.0

    traffic_by_minute: Counter[str] = Counter()
    cost_by_minute: defaultdict[str, float] = defaultdict(float)
    for record in requests:
        timestamp = _parse_timestamp(record.get("ts"))
        if timestamp:
            traffic_by_minute[timestamp.strftime("%H:%M")] += 1
    for record in responses:
        timestamp = _parse_timestamp(record.get("ts"))
        if timestamp:
            cost_by_minute[timestamp.strftime("%H:%M")] += float(record.get("cost_usd", 0))

    return {
        "latency": {
            "P50": percentile(latencies, 50),
            "P95": percentile(latencies, 95),
            "P99": percentile(latencies, 99),
            "TTFT P95": percentile(ttfts, 95),
        },
        "traffic": {
            "total": len(requests),
            "rate": len(requests) / minutes,
            "series": dict(sorted(traffic_by_minute.items())),
        },
        "errors": {
            "error_rate": error_rate,
            "retrieval_success": retrieval_success,
            "breakdown": dict(Counter(str(record.get("error_type", "unknown")) for record in failures)),
        },
        "cost": {"total": sum(costs), "series": dict(sorted(cost_by_minute.items()))},
        "tokens": {
            "input": sum(int(record.get("tokens_in", 0)) for record in responses),
            "output": sum(int(record.get("tokens_out", 0)) for record in responses),
        },
        "quality": {"mean": mean(qualities) if qualities else 0.0},
        "record_count": len(records),
    }


def _meter(value: float, threshold: float, maximum: float, operator: str) -> str:
    scale = max(maximum, threshold, value, 1)
    value_pct = min(100.0, 100 * value / scale)
    threshold_pct = min(100.0, 100 * threshold / scale)
    status = "within" if (value <= threshold if operator == "lte" else value >= threshold) else "breach"
    return (
        '<div class="meter" role="img" '
        f'aria-label="Current {value:g}; threshold {operator} {threshold:g}">'
        f'<span class="meter-value {status}" style="width:{value_pct:.2f}%"></span>'
        f'<span class="meter-threshold" style="left:{threshold_pct:.2f}%"></span>'
        "</div>"
    )


def _threshold_label(panel: dict[str, Any]) -> str:
    threshold = panel["threshold"]
    symbol = "≤" if threshold["operator"] == "lte" else "≥"
    return f'{html.escape(threshold["aggregation"])} {symbol} {threshold["value"]:g} {html.escape(panel["unit"])}'


def _panel(title: str, unit: str, body: str, threshold: str, meter: str) -> str:
    return f"""
      <section class="panel">
        <div class="panel-heading"><h2>{html.escape(title)}</h2><span>{html.escape(unit)}</span></div>
        {body}
        <div class="threshold-label"><span class="dash"></span>SLO / threshold: {threshold}</div>
        {meter}
      </section>
    """


def render_dashboard(
    log_path: Path | None = None,
    config_path: Path = CONFIG_PATH,
) -> str:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))["dashboard"]
    minutes = int(config["time_range_minutes"])
    records = load_recent_records(log_path or LOG_PATH, minutes)
    data = calculate_dashboard(records, minutes)
    panels = {panel["id"]: panel for panel in config["panels"]}

    latency = data["latency"]
    latency_body = '<div class="metrics">' + "".join(
        f'<div><strong>{value:.0f}</strong><small>{html.escape(label)}</small></div>'
        for label, value in latency.items()
    ) + "</div>"
    latency_panel = panels["latency"]
    latency_threshold = latency_panel["threshold"]

    traffic = data["traffic"]
    traffic_body = (
        '<div class="metrics two">'
        f'<div><strong>{traffic["total"]}</strong><small>requests</small></div>'
        f'<div><strong>{traffic["rate"]:.2f}</strong><small>requests/min</small></div></div>'
        f'<p class="detail">Per-minute buckets: {html.escape(json.dumps(traffic["series"], ensure_ascii=False))}</p>'
    )
    traffic_panel = panels["traffic"]
    traffic_threshold = traffic_panel["threshold"]

    errors = data["errors"]
    errors_body = (
        '<div class="metrics two">'
        f'<div><strong>{errors["error_rate"]:.2f}%</strong><small>error rate</small></div>'
        f'<div><strong>{errors["retrieval_success"]:.2f}%</strong><small>retrieval success</small></div></div>'
        f'<p class="detail">Breakdown: {html.escape(json.dumps(errors["breakdown"], ensure_ascii=False))}</p>'
    )
    errors_panel = panels["errors"]
    errors_threshold = errors_panel["threshold"]

    cost = data["cost"]
    cost_body = (
        f'<div class="hero"><strong>${cost["total"]:.6f}</strong><small>total in window</small></div>'
        f'<p class="detail">Per-minute USD: {html.escape(json.dumps(cost["series"], ensure_ascii=False))}</p>'
    )
    cost_panel = panels["cost"]
    cost_threshold = cost_panel["threshold"]

    tokens = data["tokens"]
    tokens_body = (
        '<div class="metrics two">'
        f'<div><strong>{tokens["input"]:,}</strong><small>input</small></div>'
        f'<div><strong>{tokens["output"]:,}</strong><small>output</small></div></div>'
    )
    tokens_panel = panels["tokens"]
    tokens_threshold = tokens_panel["threshold"]

    quality = data["quality"]["mean"]
    quality_body = f'<div class="hero"><strong>{quality:.3f}</strong><small>mean quality score</small></div>'
    quality_panel = panels["quality"]
    quality_threshold = quality_panel["threshold"]

    cards = "".join(
        (
            _panel(
                latency_panel["title"], latency_panel["unit"], latency_body,
                _threshold_label(latency_panel),
                _meter(latency["P95"], latency_threshold["value"], latency_threshold["value"] * 1.2, latency_threshold["operator"]),
            ),
            _panel(
                traffic_panel["title"], traffic_panel["unit"], traffic_body,
                _threshold_label(traffic_panel),
                _meter(traffic["rate"], traffic_threshold["value"], max(2, traffic["rate"]), traffic_threshold["operator"]),
            ),
            _panel(
                errors_panel["title"], errors_panel["unit"], errors_body,
                _threshold_label(errors_panel),
                _meter(errors["error_rate"], errors_threshold["value"], errors_threshold["value"] * 2.5, errors_threshold["operator"]),
            ),
            _panel(
                cost_panel["title"], cost_panel["unit"], cost_body,
                _threshold_label(cost_panel),
                _meter(cost["total"], cost_threshold["value"], cost_threshold["value"] * 1.2, cost_threshold["operator"]),
            ),
            _panel(
                tokens_panel["title"], tokens_panel["unit"], tokens_body,
                _threshold_label(tokens_panel),
                _meter(tokens["input"] + tokens["output"], tokens_threshold["value"], tokens_threshold["value"] * 1.2, tokens_threshold["operator"]),
            ),
            _panel(
                quality_panel["title"], quality_panel["unit"], quality_body,
                _threshold_label(quality_panel),
                _meter(quality, quality_threshold["value"], 1, quality_threshold["operator"]),
            ),
        )
    )

    refreshed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="refresh" content="{int(config['refresh_seconds'])}">
  <title>{html.escape(config['title'])}</title>
  <style>
    :root {{ color-scheme: light dark; --bg:#0b1220; --panel:#111c2f; --text:#eaf0ff; --muted:#9eabc2; --line:#2a3954; --good:#42d392; --bad:#ff6b6b; --accent:#70a5ff; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; background:var(--bg); color:var(--text); font-family:Inter,Segoe UI,sans-serif; }}
    main {{ max-width:1200px; margin:auto; padding:28px; }} header {{ display:flex; justify-content:space-between; gap:20px; align-items:end; margin-bottom:22px; }}
    h1 {{ margin:0 0 6px; font-size:24px; }} h2 {{ margin:0; font-size:16px; font-weight:600; }} p {{ margin:0; }} .meta,.panel-heading span,.detail,small {{ color:var(--muted); }}
    .grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; }} .panel {{ min-height:220px; padding:20px; background:var(--panel); border:1px solid var(--line); border-radius:12px; }}
    .panel-heading {{ display:flex; justify-content:space-between; gap:16px; align-items:center; margin-bottom:22px; }} .panel-heading span {{ font-size:12px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }} .metrics.two {{ grid-template-columns:repeat(2,1fr); }} .metrics div,.hero {{ display:flex; flex-direction:column; gap:5px; }}
    strong {{ font-size:25px; font-weight:600; font-variant-numeric:tabular-nums; }} small {{ font-size:12px; }} .detail {{ margin-top:18px; font:12px/1.5 Consolas,monospace; overflow-wrap:anywhere; }}
    .threshold-label {{ display:flex; gap:8px; align-items:center; margin-top:24px; color:var(--muted); font-size:12px; }} .dash {{ width:24px; border-top:2px dashed var(--accent); }}
    .meter {{ position:relative; height:10px; margin-top:9px; background:var(--line); border-radius:5px; overflow:visible; }} .meter-value {{ display:block; height:100%; border-radius:5px; }} .meter-value.within {{ background:var(--good); }} .meter-value.breach {{ background:var(--bad); }}
    .meter-threshold {{ position:absolute; top:-4px; width:2px; height:18px; background:var(--accent); }}
    @media (max-width:760px) {{ main {{ padding:18px; }} header {{ align-items:start; flex-direction:column; }} .grid {{ grid-template-columns:1fr; }} .metrics {{ grid-template-columns:repeat(2,1fr); }} }}
  </style>
</head>
<body><main>
  <header><div><h1>{html.escape(config['title'])}</h1><p class="meta">Source: data/logs.jsonl · Time range: last {minutes} minutes · Refresh: {config['refresh_seconds']}s</p></div><p class="meta">{refreshed_at}<br>{data['record_count']} records</p></header>
  <div class="grid">{cards}</div>
</main></body></html>"""
