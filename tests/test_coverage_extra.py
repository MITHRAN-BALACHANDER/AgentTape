"""Targeted tests filling coverage gaps across core modules and helpers."""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

import pytest

import agenttape
from agenttape import use_cassette
from agenttape._box import box

# -- _box ------------------------------------------------------------------ #


def test_box_attribute_access_and_roundtrip() -> None:
    b = box({"a": {"b": [1, {"c": 2}]}, "n": 5})
    assert b.a.b[1].c == 2
    assert b.n == 5
    assert b["a"]["b"][0] == 1
    assert b.model_dump() == {"a": {"b": [1, {"c": 2}]}, "n": 5}
    assert b.to_dict()["n"] == 5
    with pytest.raises(AttributeError):
        _ = b.missing
    b.newattr = 9
    assert b["newattr"] == 9


# -- callbacks ------------------------------------------------------------- #


def test_agenttape_callback_records(cassette_dir: Path) -> None:
    cb = agenttape.AgentTape(tag="run1")
    with use_cassette("cb", mode="record", cassette_dir=cassette_dir) as session:
        cb.on_chain_start({}, {"input": "x"})
        cb.on_tool_start({"name": "search"}, "query", run_id=1)
        cb.on_tool_end({"docs": 3}, run_id=1, name="search")
        cb.on_llm_start({}, ["prompt"], run_id=2)
        cb.on_llm_end({"text": "answer"}, run_id=2)
        cb.on_retriever_start({}, "q", run_id=3)
        cb.on_retriever_end([{"doc": 1}], run_id=3)
        cb.on_chain_end({"output": "done"})
        kinds = [i.kind for i in session.engine.timeline]
    assert "tool" in kinds and "llm" in kinds and "retrieval" in kinds
    assert (cassette_dir / "cb.yaml").exists()
    assert any(e["event"] == "RUN_STARTED" for e in cb.events)


def test_callback_outside_session_is_noop() -> None:
    cb = agenttape.AgentTape()
    cb.on_tool_end("x", run_id=99)  # no active session, should not raise


# -- async paths ----------------------------------------------------------- #


def test_async_tool_record_replay(cassette_dir: Path) -> None:
    spy = {"n": 0}

    @agenttape.tool
    async def fetch(x: int) -> int:
        spy["n"] += 1
        return x * 3

    async def agent() -> int:
        return await fetch(4)

    with use_cassette("af", mode="record", cassette_dir=cassette_dir):
        assert asyncio.run(agent()) == 12
    assert spy["n"] == 1
    with use_cassette("af", mode="none", cassette_dir=cassette_dir):
        assert asyncio.run(agent()) == 12
    assert spy["n"] == 1  # not executed during replay


def test_async_decorator(cassette_dir: Path) -> None:
    spy = {"n": 0}

    @agenttape.tool
    async def step(x: int) -> int:
        spy["n"] += 1
        return x

    @agenttape.replay("adec", cassette_dir=cassette_dir, mode="record")
    async def run() -> int:
        return await step(2)

    assert asyncio.run(run()) == 2
    assert (cassette_dir / "adec.yaml").exists()


def test_async_unmatched_raises(cassette_dir: Path) -> None:
    @agenttape.tool
    async def step(x: int) -> int:
        return x

    with use_cassette("au", mode="record", cassette_dir=cassette_dir):
        asyncio.run(step(1))
    with use_cassette("au", mode="none", cassette_dir=cassette_dir):
        with pytest.raises(agenttape.UnmatchedInteractionError):
            asyncio.run(step(2))


# -- decorators (sync) ----------------------------------------------------- #


def test_record_and_replay_decorators(cassette_dir: Path) -> None:
    spy = {"n": 0}

    @agenttape.tool
    def t(x: int) -> int:
        spy["n"] += 1
        return x

    @agenttape.record("deco", cassette_dir=cassette_dir)
    def rec() -> int:
        return t(1)

    @agenttape.replay("deco", cassette_dir=cassette_dir)
    def rep() -> int:
        return t(1)

    assert rec() == 1
    assert spy["n"] == 1
    assert rep() == 1
    assert spy["n"] == 1


# -- config from file ------------------------------------------------------ #


def test_config_from_file(tmp_path: Path) -> None:
    from agenttape.config import Config

    (tmp_path / "agenttape.toml").write_text(
        'cassette_dir = "tapes"\ndefault_mode = "once"\nformat = "json"\n'
        'env_snapshot = ["PATH"]\nmodel_override = "gpt-4o"\n',
        encoding="utf-8",
    )
    cfg = Config.from_file(tmp_path / "agenttape.toml")
    assert cfg.default_mode == "once"
    assert cfg.format == "json"
    assert cfg.env_snapshot == ("PATH",)
    assert cfg.model_override == "gpt-4o"


def test_config_invalid_format(tmp_path: Path) -> None:
    from agenttape.config import Config
    from agenttape.errors import ConfigError

    with pytest.raises(ConfigError):
        Config.from_mapping({"format": "xml"})


# -- engine internals ------------------------------------------------------ #


def test_to_jsonable_variants() -> None:
    from agenttape.engine import _to_jsonable

    class Obj:
        def __init__(self) -> None:
            self.a = 1
            self._private = 2

    assert _to_jsonable(Obj()) == {"a": 1}
    # bytes are preserved (the I/O layer round-trips them via the assets sidecar);
    # lossily decoding them here corrupted binary tool results.
    assert _to_jsonable(b"bytes") == b"bytes"
    assert isinstance(_to_jsonable(b"\x89PNG"), bytes)
    assert _to_jsonable((1, 2)) == [1, 2]

    class Dumpable:
        def model_dump(self) -> dict:
            return {"k": "v"}

    assert _to_jsonable(Dumpable()) == {"k": "v"}


def test_diff_fields_lists_and_absent() -> None:
    from agenttape.engine import diff_fields

    diffs = diff_fields({"a": [1, 2]}, {"a": [1, 2, 3], "b": 9})
    paths = {d.path for d in diffs}
    assert any("a[2]" in p for p in paths)
    assert "b" in paths


# -- yaml stdlib parser deep branches -------------------------------------- #


@pytest.fixture
def yaml_stdlib(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENTTAPE_FORCE_STDLIB_YAML", "1")
    import agenttape.yaml_io as y

    return importlib.reload(y)


def test_yaml_double_quoted_escapes(yaml_stdlib) -> None:
    text = 'a: "line\\nbreak\\ttab \\"q\\" \\u0041"\n'
    assert yaml_stdlib.load(text) == {"a": 'line\nbreak\ttab "q" A'}


def test_yaml_folded_scalar(yaml_stdlib) -> None:
    text = "a: >\n  one two\n  three\n\n  para2\nb: 2\n"
    result = yaml_stdlib.load(text)
    assert "one two three" in result["a"]
    assert result["b"] == 2


def test_yaml_keep_and_strip_chomping(yaml_stdlib) -> None:
    keep = yaml_stdlib.load("a: |+\n  x\n\nb: 1\n")
    assert keep["a"].endswith("\n")
    strip = yaml_stdlib.load("a: |-\n  x\nb: 1\n")
    assert strip["a"] == "x"


def test_yaml_nested_sequences(yaml_stdlib) -> None:
    text = "matrix:\n  - - 1\n    - 2\n  - - 3\n    - 4\n"
    assert yaml_stdlib.load(text) == {"matrix": [[1, 2], [3, 4]]}


def test_yaml_list_of_maps(yaml_stdlib) -> None:
    text = "items:\n  - name: a\n    val: 1\n  - name: b\n    val: 2\n"
    assert yaml_stdlib.load(text) == {"items": [{"name": "a", "val": 1}, {"name": "b", "val": 2}]}


def test_yaml_quoted_keys(yaml_stdlib) -> None:
    assert yaml_stdlib.load("'a:b': 1\n") == {"a:b": 1}


def test_yaml_flow_nested(yaml_stdlib) -> None:
    assert yaml_stdlib.load("a: [{x: 1}, {y: 2}]\n") == {"a": [{"x": 1}, {"y": 2}]}


def test_yaml_special_floats(yaml_stdlib) -> None:
    import math

    assert yaml_stdlib.dump(float("inf")).strip() == ".inf"
    assert math.isnan(yaml_stdlib.load(yaml_stdlib.dump(float("nan"))))


def test_yaml_roundtrip_special_floats_in_struct(yaml_stdlib) -> None:
    data = {"pos": float("inf"), "neg": float("-inf")}
    back = yaml_stdlib.load(yaml_stdlib.dump(data))
    assert back["pos"] == float("inf")
    assert back["neg"] == float("-inf")
