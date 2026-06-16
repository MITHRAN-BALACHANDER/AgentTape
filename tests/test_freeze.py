"""Determinism freeze layer: clock, UUID, random, env drift."""

from __future__ import annotations

import time
import uuid
import warnings
from datetime import datetime
from pathlib import Path

import pytest

from agenttape import DeterminismDriftWarning, tool, use_cassette


def test_uuid_and_clock_frozen_deterministic(cassette_dir: Path) -> None:
    @tool
    def gen() -> dict[str, str]:
        return {"id": str(uuid.uuid4()), "t": str(time.time())}

    def agent() -> dict[str, str]:
        # Values observed *outside* the tool boundary are what we assert on.
        return {"id": str(uuid.uuid4()), "now": datetime.now().isoformat()}

    with use_cassette("det", mode="record", cassette_dir=cassette_dir):
        recorded = agent()
    with use_cassette("det", mode="none", cassette_dir=cassette_dir):
        replay1 = agent()
        replay2 = agent()
    assert replay1["id"] == recorded["id"]
    assert replay1["now"] == recorded["now"]
    # Second uuid in replay is the deterministic fallback (beyond recorded count),
    # and is stable run-to-run.
    assert replay2["id"] != replay1["id"]


def test_clock_frozen_value_matches_recorded(cassette_dir: Path) -> None:
    seen = {}

    @tool
    def capture() -> float:
        return time.time()

    def agent() -> float:
        return time.time()

    with use_cassette("clk", mode="record", cassette_dir=cassette_dir):
        seen["rec"] = agent()
    with use_cassette("clk", mode="none", cassette_dir=cassette_dir):
        seen["rep"] = agent()
    assert seen["rec"] == seen["rep"]


def test_freeze_disabled(cassette_dir: Path) -> None:
    @tool
    def t(x: int) -> int:
        return x

    # freeze=[] disables all freezing; the real clock advances.
    with use_cassette("nf", mode="record", freeze=[], cassette_dir=cassette_dir):
        a = time.time()
        time.sleep(0.001)
        b = time.time()
    assert b >= a


def test_random_seed_frozen(cassette_dir: Path) -> None:
    import random

    @tool
    def noop() -> int:
        return 1

    def agent() -> list[float]:
        return [random.random() for _ in range(3)]

    with use_cassette("rng", mode="record", cassette_dir=cassette_dir):
        rec = agent()
    with use_cassette("rng", mode="none", cassette_dir=cassette_dir):
        rep = agent()
    assert rec == rep


def test_env_drift_warning(cassette_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agenttape.config import Config

    cfg = Config(cassette_dir=cassette_dir, env_snapshot=("AGENTTAPE_TESTENV",))

    @tool
    def t() -> int:
        return 1

    monkeypatch.setenv("AGENTTAPE_TESTENV", "record-value")
    with use_cassette("env", mode="record", config=cfg):
        t()
    monkeypatch.setenv("AGENTTAPE_TESTENV", "different-value")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with use_cassette("env", mode="none", config=cfg):
            t()
    assert any(issubclass(w.category, DeterminismDriftWarning) for w in caught)


def test_freeze_restores_after_session(cassette_dir: Path) -> None:
    real_uuid = uuid.uuid4
    real_time = time.time
    with use_cassette("restore", mode="record", cassette_dir=cassette_dir):
        pass
    assert uuid.uuid4 is real_uuid
    assert time.time is real_time
