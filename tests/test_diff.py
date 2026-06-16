"""Diff engine: run / prompt / state / output diffs."""

from __future__ import annotations

from agenttape.diff import output_diff, prompt_diff, run_diff, state_diff
from agenttape.schema import Cassette, Interaction


def _llm(content: str, response: str, model: str = "gpt-4o") -> Interaction:
    return Interaction(
        index=0,
        kind="llm",
        boundary="llm",
        request={"model": model, "messages": [{"role": "user", "content": content}]},
        response={"choices": [{"message": {"content": response}}]},
        usage={"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
    )


def _tool(name: str, value: object) -> Interaction:
    return Interaction(index=0, kind="tool", boundary=name, request={"name": name}, response=value)


def test_run_diff_detects_changes() -> None:
    a = Cassette(meta={"model": "gpt-4o"}, interactions=[_llm("hi", "A"), _tool("save", 1)])
    b = Cassette(meta={"model": "gpt-4o"}, interactions=[_llm("hi changed", "B"), _tool("save", 1)])
    d = run_diff(a, b)
    assert d.changed
    assert any(s.status == "changed" for s in d.steps)
    text = d.render()
    assert "Run diff" in text
    assert "tokens:" in text


def test_run_diff_added_removed_steps() -> None:
    a = Cassette(interactions=[_llm("hi", "A")])
    b = Cassette(interactions=[_llm("hi", "A"), _tool("extra", 9)])
    d = run_diff(a, b)
    statuses = {s.status for s in d.steps}
    assert "added" in statuses


def test_run_diff_unchanged() -> None:
    a = Cassette(interactions=[_llm("hi", "A")])
    b = Cassette(interactions=[_llm("hi", "A")])
    d = run_diff(a, b)
    assert not d.changed


def test_prompt_diff() -> None:
    a = Cassette(interactions=[_llm("weather in Paris", "x")])
    b = Cassette(interactions=[_llm("weather in London", "x")])
    text = prompt_diff(a, b)
    assert "Paris" in text and "London" in text
    assert text.startswith("---")


def test_prompt_diff_identical() -> None:
    a = Cassette(interactions=[_llm("same", "x")])
    assert "no prompt differences" in prompt_diff(a, a)


def test_state_diff() -> None:
    a = Cassette(
        interactions=[
            Interaction(index=0, kind="memory_write", request={}, response={"k1": 1, "k2": 2})
        ]
    )
    b = Cassette(
        interactions=[
            Interaction(index=0, kind="memory_write", request={}, response={"k2": 99, "k3": 3})
        ]
    )
    d = state_diff(a, b)
    assert d.added == {"k3": 3}
    assert d.removed == {"k1": 1}
    assert d.changed == {"k2": (2, 99)}
    assert "State/memory diff" in d.render()


def test_state_diff_empty() -> None:
    a = Cassette(interactions=[])
    assert state_diff(a, a).empty
    assert "no state" in state_diff(a, a).render()


def test_output_diff() -> None:
    a = Cassette(interactions=[_tool("final", {"answer": "yes"})])
    b = Cassette(interactions=[_tool("final", {"answer": "no"})])
    d = output_diff(a, b)
    assert d.changed
    assert d.field_diffs
    assert "Output diff" in d.render()


def test_output_diff_identical() -> None:
    a = Cassette(interactions=[_tool("final", {"answer": "yes"})])
    assert "identical" in output_diff(a, a).render()
