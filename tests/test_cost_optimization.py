from __future__ import annotations

from app.cost_optimization import CostPolicy, compact_documents, estimate_cost
from app.mock_llm import FakeLLM


def test_compact_documents_enforces_shared_context_budget() -> None:
    documents = ["a" * 100, "b" * 100]

    compacted = compact_documents(documents, 80)

    assert compacted == ["a" * 40, "b" * 40]


def test_output_budget_reduces_usage_and_cost(monkeypatch) -> None:
    monkeypatch.setattr("app.mock_llm.random.randint", lambda _start, _end: 150)
    llm = FakeLLM()

    baseline = llm.generate("x" * 400)
    optimized = llm.generate("x" * 240, max_output_tokens=80)

    baseline_cost = estimate_cost(baseline.usage.input_tokens, baseline.usage.output_tokens)
    optimized_cost = estimate_cost(optimized.usage.input_tokens, optimized.usage.output_tokens)
    assert optimized.usage.output_tokens == 80
    assert optimized_cost < baseline_cost


def test_cost_policy_reads_positive_limits(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MAX_CONTEXT_CHARS", "240")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "80")

    assert CostPolicy.from_env() == CostPolicy(max_context_chars=240, max_output_tokens=80)
