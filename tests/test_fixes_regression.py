"""Regression tests for the correctness fixes.

Each test pins a bug that was provable against the engine before the fix:

* concurrent async recording dropping interactions,
* concurrent async replay executing a frozen side effect (the headline guardrail),
* streaming silently hitting the network during offline replay,
* recorded exceptions losing their type on replay,
* small ``bytes`` being corrupted to a base64 string on round-trip,
* the matcher list being silently truncated to its first element.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agenttape import (
    StreamingReplayError,
    UnmatchedInteractionError,
    tool,
    use_cassette,
)
from agenttape.engine import Engine
from agenttape.schema import SCHEMA_VERSION, Cassette, Interaction

# -- concurrency: re-entrancy guard is per-context, not a shared counter ---- #


def test_concurrent_async_recording_captures_every_call() -> None:
    eng = Engine(recorded=Cassette(version=SCHEMA_VERSION), mode="record", cassette_existed=False)

    async def slow(tag: int) -> dict[str, int]:
        await asyncio.sleep(0.01)
        return {"tag": tag}

    async def boundary(i: int) -> object:
        return await eng.aintercept("tool", {"i": i}, boundary="t", executor=lambda: slow(i))

    async def run() -> list[object]:
        return await asyncio.gather(*[boundary(i) for i in range(5)])

    asyncio.run(run())
    # A shared-counter guard recorded only the first; each task now has its own depth.
    assert len(eng.executed) == 5
    assert sorted(i.request["i"] for i in eng.executed) == [0, 1, 2, 3, 4]


def test_concurrent_replay_does_not_execute_frozen_side_effect() -> None:
    recorded = Cassette(
        version=SCHEMA_VERSION,
        interactions=[
            Interaction(
                index=0, kind="llm", request={"m": "x"}, response={"t": "hi"}, boundary="llm"
            )
        ],
    )
    eng = Engine(recorded=recorded, mode="none", cassette_existed=True, live={"llm"})
    charged: list[str] = []

    async def real_llm() -> dict[str, str]:
        await asyncio.sleep(0.01)
        return {"t": "new"}

    def dangerous_tool() -> dict[str, bool]:
        charged.append("CHARGED")  # an irreversible real side effect
        return {"charged": True}

    async def main() -> list[object]:
        async def llm() -> object:
            return await eng.aintercept("llm", {"m": "x2"}, boundary="llm", executor=real_llm)

        async def tool_call() -> object:
            await asyncio.sleep(0.005)  # lands while the live llm is mid-flight
            return eng.intercept("tool", {"a": 1}, boundary="charge", executor=dangerous_tool)

        return await asyncio.gather(llm(), tool_call(), return_exceptions=True)

    results = asyncio.run(main())
    # The frozen tool has no recording: the guardrail must fire, not the side effect.
    assert charged == []
    assert any(isinstance(r, UnmatchedInteractionError) for r in results)


# -- streaming must never silently hit the network during offline replay ---- #


def test_streaming_raises_in_offline_replay(cassette_dir: Path) -> None:
    openai = pytest.importorskip("openai")
    httpx = pytest.importorskip("httpx")

    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(200, json={"id": "x"})

    def client() -> object:
        return openai.OpenAI(
            api_key="sk-test-x", http_client=httpx.Client(transport=httpx.MockTransport(handler))
        )

    # Record an (empty) cassette so mode="none" is a genuine offline-replay disposition.
    with use_cassette("stream", mode="record", cassette_dir=cassette_dir):
        pass
    with use_cassette("stream", mode="none", cassette_dir=cassette_dir):
        with pytest.raises(StreamingReplayError):
            client().chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
                stream=True,
            )
    assert hits["n"] == 0  # the real transport was never touched


# -- recorded exception type is preserved on replay ------------------------- #


class CustomToolError(Exception):
    """A user-defined, non-builtin exception used to test type-preserving replay."""


def test_custom_exception_type_preserved_on_replay(cassette_dir: Path) -> None:
    @tool
    def flaky() -> None:
        raise CustomToolError("db unavailable")

    with use_cassette("cerr", mode="record", cassette_dir=cassette_dir):
        with pytest.raises(CustomToolError):
            flaky()
    with use_cassette("cerr", mode="none", cassette_dir=cassette_dir):
        with pytest.raises(CustomToolError, match="db unavailable"):
            flaky()


# -- small bytes round-trip losslessly ------------------------------------- #


def test_small_bytes_roundtrip(tmp_path: Path) -> None:
    from agenttape.assets import externalize, inline

    adir = tmp_path / "c.assets"
    obj = {"blob": b"\x00\x01\x02hello", "big": b"Z" * 5000}
    restored = inline(externalize(obj, adir, threshold=4096), adir)
    assert restored["blob"] == b"\x00\x01\x02hello"
    assert isinstance(restored["blob"], bytes)
    assert restored["big"] == b"Z" * 5000  # large bytes still round-trip via the sidecar


# -- matcher fallback chain actually consults every matcher ----------------- #


def test_matcher_fallback_chain_uses_second_matcher(cassette_dir: Path) -> None:
    # Record with the default matcher.
    @tool
    def echo(payload: dict) -> dict:
        return {"echo": payload}

    with use_cassette("fb", mode="record", cassette_dir=cassette_dir):
        echo({"a": 1})

    # Replay with ("exact", "ordered"): "exact" won't match a changed payload, so the
    # engine must fall through to "ordered" and still serve the recording. Before the
    # fix only matchers[0] was ever consulted and this raised UnmatchedInteractionError.
    with use_cassette("fb", mode="none", matchers=["exact", "ordered"], cassette_dir=cassette_dir):
        assert echo({"a": 999}) == {"echo": {"a": 1}}
