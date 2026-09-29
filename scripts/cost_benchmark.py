from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cost_optimization import CostPolicy, compact_documents, estimate_cost
from app.mock_rag import retrieve


def _prompt(feature: str, docs: list[str], message: str) -> str:
    return (
        "You are a concise support assistant. Use the provided documents when relevant.\n"
        f"Feature={feature}\nDocs={' | '.join(docs)}\nQuestion={message}"
    )


def _usage(prompt: str, desired_output_tokens: int, policy: CostPolicy) -> tuple[int, int]:
    tokens_in = max(20, len(prompt) // 4)
    tokens_out = desired_output_tokens
    if policy.max_output_tokens:
        tokens_out = min(tokens_out, policy.max_output_tokens)
    return tokens_in, tokens_out


def run_benchmark(query_path: Path) -> dict[str, object]:
    queries = [json.loads(line) for line in query_path.read_text(encoding="utf-8").splitlines() if line]
    workload_hash = hashlib.sha256(
        json.dumps(queries, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    baseline = CostPolicy()
    optimized = CostPolicy(max_context_chars=48, max_output_tokens=80)
    totals = {
        "baseline": {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0},
        "optimized": {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0},
    }

    for index, query in enumerate(queries):
        docs = retrieve(query["message"])
        desired_output_tokens = random.Random(1311 + index).randint(80, 180)
        for name, policy in (("baseline", baseline), ("optimized", optimized)):
            prompt_docs = compact_documents(docs, policy.max_context_chars)
            prompt = _prompt(query["feature"], prompt_docs, query["message"])
            tokens_in, tokens_out = _usage(prompt, desired_output_tokens, policy)
            totals[name]["tokens_in"] += tokens_in
            totals[name]["tokens_out"] += tokens_out
            totals[name]["cost_usd"] += estimate_cost(tokens_in, tokens_out)

    for values in totals.values():
        values["cost_usd"] = round(values["cost_usd"], 6)
    baseline_cost = float(totals["baseline"]["cost_usd"])
    optimized_cost = float(totals["optimized"]["cost_usd"])
    saving_pct = round((baseline_cost - optimized_cost) / baseline_cost * 100, 2)
    return {
        "workload": str(query_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "workload_sha256_16": workload_hash,
        "requests": len(queries),
        "pricing_usd_per_million": {"input": 3.0, "output": 15.0},
        "baseline_policy": {"max_context_chars": None, "max_output_tokens": None},
        "optimized_policy": {"max_context_chars": 48, "max_output_tokens": 80},
        "baseline": totals["baseline"],
        "optimized": totals["optimized"],
        "cost_saving_pct": saving_pct,
        "same_workload": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic before/after cost benchmark")
    parser.add_argument("--min-saving-pct", type=float, default=20.0)
    args = parser.parse_args()
    result = run_benchmark(REPO_ROOT / "data" / "sample_queries.jsonl")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if float(result["cost_saving_pct"]) < args.min_saving_pct:
        print(f"FAIL: cost saving is below {args.min_saving_pct}%", file=sys.stderr)
        return 1
    print(f"PASS: cost saving >= {args.min_saving_pct}% on the identical workload.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
