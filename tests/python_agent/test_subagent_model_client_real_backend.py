from __future__ import annotations

import json

import pytest

import agent.subagents.model_client as model_client_module
from agent.subagents.model_client import SubagentModelClient


class _FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type, exc, tb
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


@pytest.mark.asyncio
async def test_subagent_model_client_can_use_real_backend_payload(monkeypatch) -> None:
    expected_payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "content": "I inspected the code and will edit next.",
                            "tool_uses": [
                                {"id": "u-1", "name": "BriefTool", "arguments": {"text": "inspect"}},
                                {"id": "u-2", "name": "UnknownTool", "arguments": {}},
                            ],
                        }
                    )
                }
            }
        ]
    }

    def fake_urlopen(request, timeout=0):
        _ = request, timeout
        return _FakeHTTPResponse(expected_payload)

    monkeypatch.setattr(model_client_module, "urlopen", fake_urlopen)
    client = SubagentModelClient(
        prompt="Read and edit code",
        metadata={
            "subagent_model_backend": "openai_chat",
            "subagent_model_api_key": "test-key",
            "subagent_model_endpoint": "https://example.invalid/v1/chat/completions",
        },
    )

    result = await client.generate([{"role": "user", "content": "run task"}], ["BriefTool", "FileReadTool"])
    assert result["content"] == "I inspected the code and will edit next."
    assert result["tool_uses"] == [{"id": "u-1", "name": "BriefTool", "arguments": {"text": "inspect"}}]


@pytest.mark.asyncio
async def test_subagent_model_client_raises_when_real_backend_fails_in_strict_mode(monkeypatch) -> None:
    def fake_urlopen(request, timeout=0):
        _ = request, timeout
        raise TimeoutError("network timeout")

    monkeypatch.setattr(model_client_module, "urlopen", fake_urlopen)
    client = SubagentModelClient(
        prompt="Read and edit code",
        metadata={
            "subagent_model_backend": "openai_chat",
            "subagent_model_api_key": "test-key",
            "subagent_model_endpoint": "https://example.invalid/v1/chat/completions",
        },
    )

    with pytest.raises(RuntimeError):
        await client.generate([{"role": "user", "content": "run task"}], ["BriefTool"])


@pytest.mark.asyncio
async def test_subagent_model_client_rejects_deterministic_fallback_mode(monkeypatch) -> None:
    def fake_urlopen(request, timeout=0):
        _ = request, timeout
        raise TimeoutError("network timeout")

    monkeypatch.setattr(model_client_module, "urlopen", fake_urlopen)
    client = SubagentModelClient(
        prompt="Read and edit code",
        metadata={
            "subagent_model_backend": "openai_chat",
            "subagent_model_api_key": "test-key",
            "subagent_model_endpoint": "https://example.invalid/v1/chat/completions",
            "subagent_model_fallback_mode": "deterministic",
        },
    )

    with pytest.raises(RuntimeError):
        await client.generate([{"role": "user", "content": "run task"}], ["BriefTool"])


@pytest.mark.asyncio
async def test_subagent_model_client_can_disable_implicit_deterministic_without_key() -> None:
    client = SubagentModelClient(
        prompt="Read and edit code",
        metadata={
            "subagent_allow_implicit_deterministic": False,
        },
    )

    with pytest.raises(RuntimeError):
        await client.generate([{"role": "user", "content": "run task"}], ["BriefTool"])


def test_subagent_model_client_rejects_explicit_mock_backend_when_disabled() -> None:
    with pytest.raises(ValueError):
        SubagentModelClient(
            prompt="Read and edit code",
            metadata={
                "subagent_model_backend": "deterministic",
                "subagent_allow_mock_backend": False,
            },
        )


def test_subagent_model_client_prod_profile_rejects_mock_backend_even_if_allowlisted() -> None:
    with pytest.raises(ValueError):
        SubagentModelClient(
            prompt="Read and edit code",
            metadata={
                "subagent_runtime_profile": "prod",
                "subagent_model_backend": "deterministic",
                "subagent_allow_mock_backend": True,
            },
        )


def test_subagent_model_client_code_change_rejects_mock_backend_even_in_test_profile() -> None:
    with pytest.raises(ValueError):
        SubagentModelClient(
            prompt="Modify code",
            metadata={
                "is_code_change": True,
                "subagent_runtime_profile": "test",
                "subagent_model_backend": "deterministic",
                "subagent_allow_mock_backend": True,
            },
        )


def test_subagent_model_client_test_profile_requires_explicit_mock_allow() -> None:
    with pytest.raises(ValueError):
        SubagentModelClient(
            prompt="Read code",
            metadata={
                "subagent_runtime_profile": "test",
                "subagent_model_backend": "deterministic",
            },
        )


def test_subagent_model_client_default_profile_is_prod_and_rejects_mock_backend(monkeypatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    with pytest.raises(ValueError):
        SubagentModelClient(
            prompt="Read code",
            metadata={
                "subagent_model_backend": "deterministic",
                "subagent_allow_mock_backend": True,
            },
        )
