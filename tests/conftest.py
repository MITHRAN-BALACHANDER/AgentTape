"""Shared pytest fixtures for the AgentTape test-suite."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def cassette_dir(tmp_path: Path) -> Path:
    d = tmp_path / "cassettes"
    d.mkdir()
    return d


@pytest.fixture
def chat_response_factory() -> Callable[..., dict[str, Any]]:
    def make(content: str = "hello world", model: str = "gpt-4o-mini") -> dict[str, Any]:
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": content},
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

    return make


@pytest.fixture
def openai_client_factory(chat_response_factory: Callable[..., dict[str, Any]]) -> Any:
    """Return (factory, counter) where factory() builds an offline OpenAI client."""

    pytest.importorskip("openai")
    pytest.importorskip("httpx")
    import httpx
    from openai import OpenAI

    counter = {"calls": 0}

    def factory(content: str = "hello world", model: str = "gpt-4o-mini") -> Any:
        def handler(request: httpx.Request) -> httpx.Response:
            counter["calls"] += 1
            return httpx.Response(200, json=chat_response_factory(content, model))

        return OpenAI(
            api_key="sk-test-secret-abcdefghijklmnopqrstuvwxyz",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    return factory, counter
