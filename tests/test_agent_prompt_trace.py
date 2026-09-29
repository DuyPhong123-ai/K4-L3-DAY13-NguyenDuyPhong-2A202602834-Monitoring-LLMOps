from __future__ import annotations

from contextlib import contextmanager

from app import agent as agent_module


class ManagedPrompt:
    version = 3

    def compile(self, **variables: str) -> str:
        return (
            f"Feature={variables['feature']}\n"
            f"Docs={variables['docs']}\n"
            f"Question={variables['message']}"
        )


class RecordingLangfuseClient:
    def __init__(self) -> None:
        self.prompt = ManagedPrompt()
        self.span_updates: list[dict] = []
        self.observations: list[RecordingObservation] = []

    def get_prompt(self, name: str, **kwargs):
        return self.prompt

    def update_current_span(self, **kwargs) -> None:
        self.span_updates.append(kwargs)

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        observation = RecordingObservation(kwargs)
        self.observations.append(observation)
        yield observation


class RecordingObservation:
    def __init__(self, creation: dict) -> None:
        self.creation = creation
        self.updates: list[dict] = []

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)


def test_agent_records_prompt_version_with_v4_observation_api(monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_PROMPT_NAME", "day13-chat")
    monkeypatch.setenv("LANGFUSE_PROMPT_LABEL", "production")
    client = RecordingLangfuseClient()
    monkeypatch.setattr(agent_module, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(agent_module, "tracing_enabled", lambda: True)

    propagated: list[dict] = []

    @contextmanager
    def record_attributes(**kwargs):
        propagated.append(kwargs)
        yield

    monkeypatch.setattr(agent_module, "propagate_attributes", record_attributes)

    agent = agent_module.LabAgent()
    agent_module.LabAgent.run.__wrapped__(
        agent,
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message="Explain traces",
        correlation_id="req-12345678",
    )

    span_update = client.span_updates[-1]
    assert span_update["metadata"] == {
        "doc_count": 1,
        "query_preview": "Explain traces",
        "prompt_name": "day13-chat",
        "prompt_label": "production",
        "prompt_version": "3",
        "prompt_source": "langfuse",
        "prompt_fetch_error": "",
    }
    assert span_update["version"] == "3"
    assert propagated[0]["metadata"]["correlation_id"] == "req-12345678"
    assert propagated[-1]["prompt"] is client.prompt

    retrieval, generation = client.observations
    assert retrieval.creation["as_type"] == "retriever"
    assert retrieval.creation["name"] == "retrieve-context"
    assert retrieval.updates[-1]["output"]["document_count"] == 1
    assert generation.creation["as_type"] == "generation"
    assert generation.creation["name"] == "generate-response"
    assert generation.creation["model"] == "claude-sonnet-4-5"
    assert generation.creation["prompt"] is client.prompt
    assert generation.updates[-1]["usage_details"]["input"] > 0
    assert generation.updates[-1]["usage_details"]["output"] > 0
    assert generation.updates[-1]["cost_details"]["total"] > 0


def test_trace_inputs_are_scrubbed(monkeypatch) -> None:
    client = RecordingLangfuseClient()
    monkeypatch.setattr(agent_module, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(agent_module, "tracing_enabled", lambda: True)
    monkeypatch.setattr(agent_module, "propagate_attributes", lambda **_: contextmanager(lambda: (yield))())

    agent = agent_module.LabAgent()
    agent_module.LabAgent.run.__wrapped__(
        agent,
        user_id="student@example.com",
        feature="qa",
        session_id="session-01",
        message="Contact student@example.com or 0901234567",
        correlation_id="req-12345678",
    )

    recorded = repr((client.span_updates, [item.creation for item in client.observations]))
    assert "student@example.com" not in recorded
    assert "0901234567" not in recorded
    assert "REDACTED_EMAIL" in recorded
    assert "REDACTED_PHONE_VN" in recorded
