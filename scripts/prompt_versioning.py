from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PROMPT_NAME = "day13-chat"
PROMPT_V1 = """You are a concise support assistant. Use the provided documents when relevant.
Feature={{feature}}
Docs={{docs}}
Question={{message}}"""
PROMPT_V2 = PROMPT_V1 + "\nAnswer in no more than three sentences."


def _client():
    load_dotenv(REPO_ROOT / ".env", override=False)
    from langfuse import get_client

    return get_client()


def _get_version(client, version: int):
    from langfuse.api.commons import NotFoundError

    try:
        return client.get_prompt(
            PROMPT_NAME,
            version=version,
            type="text",
            cache_ttl_seconds=0,
            fetch_timeout_seconds=5,
            max_retries=1,
        )
    except NotFoundError:
        return None


def create_versions(client) -> None:
    version_1 = _get_version(client, 1)
    if version_1 is None:
        created = client.create_prompt(
            name=PROMPT_NAME,
            type="text",
            prompt=PROMPT_V1,
            labels=["baseline", "production"],
            commit_message="Baseline prompt for Day 13 observability lab",
        )
        if created.version != 1:
            raise RuntimeError(
                f"Expected {PROMPT_NAME} version 1, but Langfuse created version {created.version}. "
                "Use a new prompt name or review existing project data before continuing."
            )
    elif version_1.prompt != PROMPT_V1:
        raise RuntimeError(f"{PROMPT_NAME} version 1 already exists with different content")
    else:
        client.update_prompt(name=PROMPT_NAME, version=1, new_labels=["baseline", "production"])

    version_2 = _get_version(client, 2)
    if version_2 is None:
        created = client.create_prompt(
            name=PROMPT_NAME,
            type="text",
            prompt=PROMPT_V2,
            labels=["candidate"],
            commit_message="Candidate: constrain answer to three sentences",
        )
        if created.version != 2:
            raise RuntimeError(
                f"Expected {PROMPT_NAME} version 2, but Langfuse created version {created.version}"
            )
    elif version_2.prompt != PROMPT_V2:
        raise RuntimeError(f"{PROMPT_NAME} version 2 already exists with different content")
    else:
        client.update_prompt(name=PROMPT_NAME, version=2, new_labels=["candidate"])

    client.clear_prompt_cache()
    print("Created/verified day13-chat v1 [baseline, production] and v2 [candidate].")


def set_production(client, version: int) -> None:
    if _get_version(client, 1) is None or _get_version(client, 2) is None:
        raise RuntimeError("Run the 'create' action before promote/rollback")
    client.update_prompt(
        name=PROMPT_NAME,
        version=1,
        new_labels=["baseline"] + (["production"] if version == 1 else []),
    )
    client.update_prompt(
        name=PROMPT_NAME,
        version=2,
        new_labels=["candidate"] + (["production"] if version == 2 else []),
    )
    client.clear_prompt_cache()
    action = "Promoted v2" if version == 2 else "Rolled production back to v1"
    print(f"{action}; production -> version {version}.")


def show_status(client) -> None:
    for version in (1, 2):
        prompt = _get_version(client, version)
        if prompt is None:
            print(f"v{version}: missing")
        else:
            labels = ", ".join(sorted(getattr(prompt, "labels", []))) or "none"
            print(f"v{version}: labels=[{labels}]")


def compare_labels(client) -> None:
    from app.agent import LabAgent

    agent = LabAgent()
    message = "Explain how metrics, logs, and traces work together."
    for label in ("baseline", "candidate"):
        _run_label(client, agent, label, message, "prompt-version-comparison")
    client.flush()
    print("Comparison traces flushed to Langfuse.")


def _run_label(client, agent, label: str, message: str, session_id: str) -> None:
    os.environ["LANGFUSE_PROMPT_NAME"] = PROMPT_NAME
    os.environ["LANGFUSE_PROMPT_LABEL"] = label
    client.clear_prompt_cache()
    correlation_id = f"prompt-{label}-{uuid.uuid4().hex[:8]}"
    result = agent.run(
        user_id="prompt-comparison-user",
        feature="monitoring",
        session_id=session_id,
        message=message,
        correlation_id=correlation_id,
    )
    print(
        f"label={label} correlation_id={correlation_id} "
        f"tokens={result.tokens_in + result.tokens_out} cost_usd={result.cost_usd:.6f}"
    )


def run_production(client) -> None:
    from app.agent import LabAgent

    _run_label(
        client,
        LabAgent(),
        "production",
        "Explain how metrics, logs, and traces work together.",
        "prompt-production-verification",
    )
    client.flush()
    print("Production verification trace flushed to Langfuse.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the Day 13 Langfuse prompt workflow")
    parser.add_argument(
        "action",
        choices=("create", "compare", "promote", "run-production", "rollback", "status"),
    )
    args = parser.parse_args()
    client = _client()

    if args.action == "create":
        create_versions(client)
    elif args.action == "compare":
        compare_labels(client)
    elif args.action == "promote":
        set_production(client, 2)
    elif args.action == "run-production":
        run_production(client)
    elif args.action == "rollback":
        set_production(client, 1)
    else:
        show_status(client)
    client.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
