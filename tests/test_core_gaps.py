"""Final coverage push for core modules: canonical, boundaries, engine, matchers."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import agenttape
from agenttape import record_call, tool, use_cassette

# -- canonical ------------------------------------------------------------- #


def test_stable_json_handles_special_types() -> None:
    from agenttape.canonical import content_hash, stable_json

    assert stable_json({1, 2, 3}) == "[1,2,3]"
    assert stable_json(b"hi") == '"hi"'

    class Model:
        def model_dump(self) -> dict:
            return {"x": 1}

    assert stable_json(Model()) == '{"x":1}'

    class Plain:
        def __init__(self) -> None:
            self.a = 1
            self._hidden = 2

    assert stable_json(Plain()) == '{"a":1}'
    assert content_hash(b"abc").startswith("sha256:")


def test_canonicalize_normalize_whitespace() -> None:
    from agenttape.canonical import canonicalize

    assert canonicalize({"a": "  x  "}, normalize_whitespace=True) == {"a": "x"}
    assert canonicalize({"a": "  x  "}, normalize_whitespace=False) == {"a": "  x  "}


# -- boundaries ------------------------------------------------------------ #


def test_tool_with_explicit_name(cassette_dir: Path) -> None:
    @tool(name="custom_name")
    def f(x: int) -> int:
        return x

    with use_cassette("named", mode="record", cassette_dir=cassette_dir):
        f(1)
    import agenttape.cassette as cio

    c = cio.read_cassette(cassette_dir / "named.yaml")
    assert c.interactions[0].boundary == "custom_name"


def test_record_call_low_level(cassette_dir: Path) -> None:
    spy = {"n": 0}

    def do() -> dict:
        spy["n"] += 1
        return {"ok": True}

    with use_cassette("rc", mode="record", cassette_dir=cassette_dir):
        out = record_call("tool", {"name": "manual"}, do, boundary="manual")
    assert out == {"ok": True} and spy["n"] == 1
    with use_cassette("rc", mode="none", cassette_dir=cassette_dir):
        out2 = record_call("tool", {"name": "manual"}, do, boundary="manual")
    assert out2 == {"ok": True} and spy["n"] == 1  # replayed


def test_record_call_outside_session() -> None:
    assert record_call("tool", {}, lambda: 42) == 42


def test_normalize_args_handles_varkw(cassette_dir: Path) -> None:
    @tool
    def f(a: int, **kw: int) -> dict:
        return {"a": a, **kw}

    with use_cassette("vk", mode="record", cassette_dir=cassette_dir):
        f(1, b=2, c=3)
    import agenttape.cassette as cio

    c = cio.read_cassette(cassette_dir / "vk.yaml")
    args = c.interactions[0].request["args"]
    assert args == {"a": 1, "b": 2, "c": 3}


# -- engine: async replay, ordered, errors --------------------------------- #


def test_async_replay_returns_recorded(cassette_dir: Path) -> None:
    spy = {"n": 0}

    @tool
    async def fetch(x: int) -> int:
        spy["n"] += 1
        return x

    with use_cassette("ar", mode="record", cassette_dir=cassette_dir):
        asyncio.run(fetch(7))
    with use_cassette("ar", mode="none", cassette_dir=cassette_dir):
        assert asyncio.run(fetch(7)) == 7
    assert spy["n"] == 1


def test_async_error_recorded_and_replayed(cassette_dir: Path) -> None:
    @tool
    async def boom() -> None:
        raise KeyError("nope")

    with use_cassette("aerr", mode="record", cassette_dir=cassette_dir):
        with pytest.raises(KeyError):
            asyncio.run(boom())
    with use_cassette("aerr", mode="none", cassette_dir=cassette_dir):
        with pytest.raises(KeyError):
            asyncio.run(boom())


def test_build_output_record_mode_empty(cassette_dir: Path) -> None:
    # Recording with no interactions still writes a valid (empty) cassette.
    with use_cassette("empty", mode="record", cassette_dir=cassette_dir):
        pass
    assert (cassette_dir / "empty.yaml").exists()
    import agenttape.cassette as cio

    assert cio.read_cassette(cassette_dir / "empty.yaml").interactions == []


def test_unmatched_no_candidates(cassette_dir: Path) -> None:
    @tool
    def a(x: int) -> int:
        return x

    @tool
    def b(x: int) -> int:
        return x

    with use_cassette("nc", mode="record", cassette_dir=cassette_dir):
        a(1)
    # b has no recording at all -> closest is None, no field diffs.
    with use_cassette("nc", mode="none", cassette_dir=cassette_dir):
        with pytest.raises(agenttape.UnmatchedInteractionError) as exc:
            b(1)
    assert exc.value.closest is None


def test_nested_boundary_passthrough(cassette_dir: Path) -> None:
    inner_spy = {"n": 0}

    @tool
    def inner(x: int) -> int:
        inner_spy["n"] += 1
        return x

    @tool
    def outer(x: int) -> int:
        return inner(x) + 1

    with use_cassette("nest", mode="record", cassette_dir=cassette_dir):
        assert outer(5) == 6
    import agenttape.cassette as cio

    c = cio.read_cassette(cassette_dir / "nest.yaml")
    # Only the outer boundary is recorded (inner runs inside its execution).
    assert [i.boundary for i in c.interactions] == ["outer"]
