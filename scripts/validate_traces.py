from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.pii import PII_PATTERNS

FIELDS = "core,basic,io,metadata,model,usage,prompt,metrics,trace_context"
REQUIRED_ROOT_METADATA = {"correlation_id", "feature", "model", "prompt_name", "prompt_label", "prompt_version"}


def main() -> int:
    load_dotenv(REPO_ROOT / ".env", override=False)
    from langfuse import get_client

    client = get_client()
    now = datetime.now(timezone.utc)
    response = client.api.observations.get_many(
        from_start_time=now - timedelta(minutes=60),
        to_start_time=now + timedelta(minutes=1),
        fields=FIELDS,
        limit=1000,
    )

    roots = sorted(
        (item for item in response.data if item.name == "lab-agent-run"),
        key=lambda item: item.start_time,
        reverse=True,
    )[:10]
    selected_trace_ids = {item.trace_id for item in roots}
    by_trace: defaultdict[str, list] = defaultdict(list)
    for observation in response.data:
        if observation.trace_id in selected_trace_ids:
            by_trace[observation.trace_id].append(observation)

    valid: list[tuple[str, str]] = []
    invalid: list[tuple[str, list[str]]] = []
    pii_hits: list[str] = []
    detectors = {name: re.compile(pattern) for name, pattern in PII_PATTERNS.items()}

    for trace_id, observations in by_trace.items():
        problems: list[str] = []
        roots = [item for item in observations if item.name == "lab-agent-run"]
        retrievals = [item for item in observations if item.name == "retrieve-context"]
        generations = [item for item in observations if item.name == "generate-response"]
        if len(roots) != 1 or len(retrievals) != 1 or len(generations) != 1:
            problems.append("expected exactly one root, retriever, and generation")
        else:
            root, retrieval, generation = roots[0], retrievals[0], generations[0]
            if retrieval.parent_observation_id != root.id or generation.parent_observation_id != root.id:
                problems.append("child observation has the wrong parent")
            metadata = root.metadata or {}
            if not REQUIRED_ROOT_METADATA.issubset(metadata):
                problems.append("root metadata is incomplete")
            if not root.user_id or len(root.user_id) != 12 or not root.session_id or not root.environment:
                problems.append("user/session/environment context is incomplete")
            usage = generation.usage_details or {}
            cost = generation.cost_details or {}
            if not generation.model or not {"input", "output"}.issubset(usage):
                problems.append("generation model or token usage is incomplete")
            if cost.get("total") is None or generation.prompt_name != "day13-chat":
                problems.append("generation cost or prompt link is incomplete")

            safe_payload = json.dumps(
                [
                    {"input": item.input, "output": item.output, "metadata": item.metadata}
                    for item in observations
                ],
                ensure_ascii=False,
                default=str,
            )
            detected = [name for name, detector in detectors.items() if detector.search(safe_payload)]
            if detected:
                pii_hits.append(f"{trace_id}: {', '.join(detected)}")

            correlation_id = str(metadata.get("correlation_id", "missing"))

        if problems:
            invalid.append((trace_id, problems))
        else:
            valid.append((trace_id, correlation_id))

    print("--- Langfuse Trace Verification ---")
    print(f"Latest trace groups checked: {len(by_trace)}")
    print(f"Valid root/retriever/generation traces: {len(valid)}")
    print(f"Invalid traces: {len(invalid)}")
    print(f"Potential PII leaks: {len(pii_hits)}")
    for trace_id, correlation_id in valid[:10]:
        print(f"  trace_id={trace_id} correlation_id={correlation_id}")
    for trace_id, problems in invalid[:5]:
        print(f"  invalid trace_id={trace_id}: {'; '.join(problems)}")
    for hit in pii_hits[:5]:
        print(f"  PII: {hit}")

    passed = len(valid) >= 10 and not invalid and not pii_hits
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
