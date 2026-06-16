"""Engine modes, mixed replay, side-effect guardrail and record-back."""

from __future__ import annotations

from pathlib import Path

import pytest

import agenttape
from agenttape import UnmatchedInteractionError, tool, use_cassette


@pytest.fixture
def spy() -> dict[str, int]:
    return {"calls": 0}


def make_tool(spy: dict[str, int]):
    @tool
    def do_thing(x: int) -> dict[str, int]:
        spy["calls"] += 1
        return {"result": x * 2}

    return do_thing


def test_record_then_replay_no_side_effect(cassette_dir: Path, spy: dict[str, int]) -> None:
    do_thing = make_tool(spy)
    with use_cassette("t", mode="record", cassette_dir=cassette_dir):
        assert do_thing(5) == {"result": 10}
    assert spy["calls"] == 1
    with use_cassette("t", mode="none", cassette_dir=cassette_dir):
        assert do_thing(5) == {"result": 10}
    assert spy["calls"] == 1  # tool did NOT execute during replay


def test_guardrail_raises_on_unmatched(cassette_dir: Path, spy: dict[str, int]) -> None:
    do_thing = make_tool(spy)
    with use_cassette("t", mode="record", cassette_dir=cassette_dir):
        do_thing(5)
    with use_cassette("t", mode="none", cassette_dir=cassette_dir):
        with pytest.raises(UnmatchedInteractionError) as exc:
            do_thing(999)
    msg = str(exc.value)
    assert "No recorded tool interaction" in msg
    assert "How to fix" in msg
    assert exc.value.field_diffs  # closest match diff present


def test_once_mode_records_then_replays(cassette_dir: Path, spy: dict[str, int]) -> None:
    do_thing = make_tool(spy)
    with use_cassette("t", mode="once", cassette_dir=cassette_dir):
        do_thing(3)
    assert spy["calls"] == 1
    with use_cassette("t", mode="once", cassette_dir=cassette_dir):
        do_thing(3)
    assert spy["calls"] == 1  # replayed, not re-executed


def test_all_mode_always_records(cassette_dir: Path, spy: dict[str, int]) -> None:
    do_thing = make_tool(spy)
    with use_cassette("t", mode="record", cassette_dir=cassette_dir):
        do_thing(3)
    with use_cassette("t", mode="all", cassette_dir=cassette_dir):
        do_thing(3)
    assert spy["calls"] == 2  # 'all' ignores the existing recording


def test_new_episodes_appends(cassette_dir: Path, spy: dict[str, int]) -> None:
    do_thing = make_tool(spy)
    with use_cassette("t", mode="record", cassette_dir=cassette_dir):
        do_thing(1)
    with use_cassette("t", mode="new_episodes", cassette_dir=cassette_dir):
        do_thing(1)  # replayed
        do_thing(2)  # new -> recorded
    assert spy["calls"] == 2
    import agenttape.cassette as cio

    c = cio.read_cassette(cassette_dir / "t.yaml")
    args = sorted(i.request["args"]["x"] for i in c.interactions)
    assert args == [1, 2]


def test_mixed_replay_live_tool_executes_others_frozen(
    cassette_dir: Path, spy: dict[str, int]
) -> None:
    live_spy = {"calls": 0}
    frozen_spy = {"calls": 0}

    @tool
    def live_tool(x: int) -> int:
        live_spy["calls"] += 1
        return x + 100

    @tool
    def frozen_tool(x: int) -> int:
        frozen_spy["calls"] += 1
        return x + 1

    def agent() -> tuple[int, int]:
        return frozen_tool(1), live_tool(1)

    with use_cassette("mix", mode="record", cassette_dir=cassette_dir):
        agent()
    assert live_spy["calls"] == 1 and frozen_spy["calls"] == 1

    with use_cassette("mix", mode="none", live={"live_tool"}, cassette_dir=cassette_dir):
        agent()
    assert live_spy["calls"] == 2  # ran live
    assert frozen_spy["calls"] == 1  # stayed frozen
    assert (cassette_dir / "mix.derived.yaml").exists()


def test_frozen_set_is_inverse_of_live(cassette_dir: Path) -> None:
    a_spy = {"n": 0}
    b_spy = {"n": 0}

    @tool
    def a(x: int) -> int:
        a_spy["n"] += 1
        return x

    @tool
    def b(x: int) -> int:
        b_spy["n"] += 1
        return x

    with use_cassette("fr", mode="record", cassette_dir=cassette_dir):
        a(1), b(1)
    # frozen={"a"} => only a is replayed, b runs live
    with use_cassette("fr", mode="none", frozen={"a"}, cassette_dir=cassette_dir):
        a(1), b(1)
    assert a_spy["n"] == 1
    assert b_spy["n"] == 2


def test_live_and_frozen_together_is_error(cassette_dir: Path) -> None:
    with pytest.raises(ValueError):
        with use_cassette("x", mode="none", live={"a"}, frozen={"b"}, cassette_dir=cassette_dir):
            pass


def test_recorded_error_is_replayed(cassette_dir: Path) -> None:
    @tool
    def flaky() -> None:
        raise ValueError("boom")

    with use_cassette("err", mode="record", cassette_dir=cassette_dir):
        with pytest.raises(ValueError):
            flaky()
    with use_cassette("err", mode="none", cassette_dir=cassette_dir):
        with pytest.raises(ValueError, match="boom"):
            flaky()


def test_ordered_matcher(cassette_dir: Path) -> None:
    seq = []

    @tool
    def step(payload: dict) -> dict:
        seq.append(payload)
        return {"echo": payload}

    with use_cassette("ord", mode="record", matchers=["ordered"], cassette_dir=cassette_dir):
        step({"a": 1})
        step({"a": 2})
    with use_cassette("ord", mode="none", matchers=["ordered"], cassette_dir=cassette_dir):
        assert step({"different": "x"}) == {"echo": {"a": 1}}
        assert step({"other": "y"}) == {"echo": {"a": 2}}


def test_retrieval_and_memory_boundaries(cassette_dir: Path) -> None:
    @agenttape.retrieval
    def search(q: str) -> list[str]:
        return [f"doc about {q}"]

    @agenttape.memory_write
    def remember(key: str, value: str) -> dict:
        return {key: value}

    with use_cassette("rm", mode="record", cassette_dir=cassette_dir):
        search("cats")
        remember("name", "alice")
    import agenttape.cassette as cio

    c = cio.read_cassette(cassette_dir / "rm.yaml")
    kinds = {i.kind for i in c.interactions}
    assert kinds == {"retrieval", "memory_write"}


def test_boundary_passthrough_without_session() -> None:
    calls = {"n": 0}

    @tool
    def t() -> int:
        calls["n"] += 1
        return 1

    assert t() == 1  # no active session -> just runs
    assert calls["n"] == 1


def test_json_format(cassette_dir: Path) -> None:
    @tool
    def t(x: int) -> int:
        return x

    with use_cassette("j", mode="record", format="json", cassette_dir=cassette_dir):
        t(5)
    assert (cassette_dir / "j.json").exists()
    with use_cassette("j", mode="none", format="json", cassette_dir=cassette_dir):
        assert t(5) == 5
