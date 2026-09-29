from __future__ import annotations

import os
from dataclasses import dataclass


INPUT_COST_PER_MILLION = 3.0
OUTPUT_COST_PER_MILLION = 15.0


def _positive_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


@dataclass(frozen=True)
class CostPolicy:
    """Optional token controls; unset values preserve baseline behavior."""

    max_context_chars: int | None = None
    max_output_tokens: int | None = None

    @classmethod
    def from_env(cls) -> "CostPolicy":
        return cls(
            max_context_chars=_positive_int(os.getenv("LLM_MAX_CONTEXT_CHARS")),
            max_output_tokens=_positive_int(os.getenv("LLM_MAX_OUTPUT_TOKENS")),
        )


def compact_documents(documents: list[str], max_context_chars: int | None) -> list[str]:
    if not max_context_chars or not documents:
        return documents
    per_document = max(1, max_context_chars // len(documents))
    return [document[:per_document] for document in documents]


def estimate_cost(tokens_in: int, tokens_out: int) -> float:
    input_cost = (tokens_in / 1_000_000) * INPUT_COST_PER_MILLION
    output_cost = (tokens_out / 1_000_000) * OUTPUT_COST_PER_MILLION
    return round(input_cost + output_cost, 6)
