"""OpenAI adapter and raw httpx/requests fallback adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import agenttape.cassette as cio
from agenttape import tool, use_cassette


def test_openai_record_replay_no_network(openai_client_factory: Any, cassette_dir: Path) -> None:
    factory, counter = openai_client_factory

    def agent() -> str:
        client = factory("It is sunny.")
        r = client.chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "user", "content": "weather?"}]
        )
        return r.choices[0].message.content

    with use_cassette("oa", mode="record", cassette_dir=cassette_dir):
        out = agent()
    assert out == "It is sunny."
    assert counter["calls"] == 1

    before = counter["calls"]
    with use_cassette("oa", mode="none", cassette_dir=cassette_dir):
        out2 = agent()
    assert out2 == out
    assert counter["calls"] == before  # zero network in replay


def test_openai_secret_redacted(openai_client_factory: Any, cassette_dir: Path) -> None:
    factory, _ = openai_client_factory

    def agent() -> str:
        client = factory()
        return client.chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}]
        ).choices[0].message.content

    with use_cassette("sec", mode="record", cassette_dir=cassette_dir):
        agent()
    text = (cassette_dir / "sec.yaml").read_text(encoding="utf-8")
    assert "sk-test-secret" not in text


def test_openai_only_one_llm_interaction(openai_client_factory: Any, cassette_dir: Path) -> None:
    """Re-entrancy guard: the internal httpx call is not double-recorded."""

    factory, _ = openai_client_factory

    def agent() -> None:
        factory().chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}]
        )

    with use_cassette("one", mode="record", cassette_dir=cassette_dir):
        agent()
    c = cio.read_cassette(cassette_dir / "one.yaml")
    assert [i.kind for i in c.interactions] == ["llm"]
    assert c.interactions[0].usage is not None


def test_openai_hand_edit_reflected(openai_client_factory: Any, cassette_dir: Path) -> None:
    factory, counter = openai_client_factory

    def agent() -> str:
        return factory("original").chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}]
        ).choices[0].message.content

    with use_cassette("edit", mode="record", cassette_dir=cassette_dir):
        agent()
    path = cassette_dir / "edit.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("original", "EDITED"), encoding="utf-8")
    calls_before = counter["calls"]
    with use_cassette("edit", mode="none", cassette_dir=cassette_dir):
        assert agent() == "EDITED"
    assert counter["calls"] == calls_before


def test_openai_mixed_replay(openai_client_factory: Any, cassette_dir: Path) -> None:
    factory, counter = openai_client_factory
    db = {"writes": 0}

    @tool
    def save(x: str) -> dict:
        db["writes"] += 1
        return {"saved": x}

    def agent(prompt: str) -> str:
        out = factory("answer").chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}]
        ).choices[0].message.content
        save("row")
        return out

    with use_cassette("mx", mode="record", cassette_dir=cassette_dir):
        agent("first")
    net0, db0 = counter["calls"], db["writes"]
    with use_cassette("mx", mode="none", live={"llm"}, cassette_dir=cassette_dir):
        agent("CHANGED prompt")
    assert counter["calls"] == net0 + 1  # llm ran live
    assert db["writes"] == db0  # tool stayed frozen
    assert (cassette_dir / "mx.derived.yaml").exists()


# -- raw httpx / requests fallback ----------------------------------------- #


def test_httpx_fallback(cassette_dir: Path) -> None:
    httpx = pytest.importorskip("httpx")
    counter = {"n": 0}

    def handler(request: Any) -> Any:
        counter["n"] += 1
        return httpx.Response(200, json={"ok": True, "echo": request.url.path})

    def agent() -> dict:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        return client.get("https://api.example.com/data").json()

    with use_cassette("hx", mode="record", cassette_dir=cassette_dir):
        out = agent()
    assert out["ok"] is True and counter["n"] == 1

    c = cio.read_cassette(cassette_dir / "hx.yaml")
    assert [i.kind for i in c.interactions] == ["http"]

    with use_cassette("hx", mode="none", cassette_dir=cassette_dir):
        out2 = agent()
    assert out2 == out
    assert counter["n"] == 1  # replayed


def test_requests_fallback_manual(cassette_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requests = pytest.importorskip("requests")
    counter = {"n": 0}

    # Patch the *original* HTTPAdapter.send via a low-level stub so no real network
    # is used while still exercising AgentTape's requests patch on top.
    from requests.adapters import HTTPAdapter

    real_send = HTTPAdapter.send

    def fake_send(self: Any, request: Any, **kwargs: Any) -> Any:
        counter["n"] += 1
        resp = requests.models.Response()
        resp.status_code = 200
        resp._content = b'{"ok": true}'
        resp.headers["Content-Type"] = "application/json"
        resp.url = request.url
        resp.request = request
        return resp

    monkeypatch.setattr(HTTPAdapter, "send", fake_send)

    def agent() -> dict:
        return requests.get("https://api.example.com/x").json()

    with use_cassette("rq", mode="record", cassette_dir=cassette_dir):
        out = agent()
    assert out == {"ok": True} and counter["n"] == 1

    c = cio.read_cassette(cassette_dir / "rq.yaml")
    assert [i.kind for i in c.interactions] == ["http"]

    with use_cassette("rq", mode="none", cassette_dir=cassette_dir):
        assert agent() == out
    assert counter["n"] == 1
