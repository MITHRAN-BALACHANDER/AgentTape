"""Tests for the stdlib YAML subset reader/writer (both PyYAML and stdlib paths)."""

from __future__ import annotations

import importlib
from typing import Any

import pytest


def _reload_yaml(monkeypatch: pytest.MonkeyPatch, force_stdlib: bool) -> Any:
    if force_stdlib:
        monkeypatch.setenv("AGENTTAPE_FORCE_STDLIB_YAML", "1")
    else:
        monkeypatch.delenv("AGENTTAPE_FORCE_STDLIB_YAML", raising=False)
    import agenttape.yaml_io as y

    return importlib.reload(y)


SAMPLE: dict[str, Any] = {
    "version": "1",
    "string": "plain",
    "quoted": "has: colon # and hash",
    "empty_str": "",
    "multiline": "line1\nline2\nline3",
    "trailing_nl": "ends with newline\n",
    "int": 42,
    "neg": -7,
    "float": 3.14,
    "bool_t": True,
    "bool_f": False,
    "none": None,
    "ambiguous": "123",
    "ambiguous_bool": "true",
    "list": [1, "two", True, None, {"k": "v"}],
    "nested": {"a": {"b": {"c": [1, 2, 3]}}},
    "empty_dict": {},
    "empty_list": [],
}


@pytest.mark.parametrize("force_stdlib", [True, False])
def test_roundtrip(monkeypatch: pytest.MonkeyPatch, force_stdlib: bool) -> None:
    y = _reload_yaml(monkeypatch, force_stdlib)
    text = y.dump(SAMPLE)
    back = y.load(text)
    assert back == SAMPLE
    assert y.using_pyyaml() is (not force_stdlib and _pyyaml_installed())


def test_stdlib_preserves_string_types(monkeypatch: pytest.MonkeyPatch) -> None:
    y = _reload_yaml(monkeypatch, True)
    data = {"a": "123", "b": "true", "c": "null", "d": "3.5"}
    back = y.load(y.dump(data))
    assert back == data
    assert all(isinstance(v, str) for v in back.values())


def test_stdlib_block_scalar(monkeypatch: pytest.MonkeyPatch) -> None:
    y = _reload_yaml(monkeypatch, True)
    text = y.dump({"body": "a\nb\n  indented\nc"})
    assert "|-" in text
    assert y.load(text)["body"] == "a\nb\n  indented\nc"


_TRICKY_STRINGS = [
    "a\n\n",  # two trailing newlines — lost under the old clip-only emitter
    "l1\nl2\n\n\n",  # three trailing newlines
    "ends with newline\n",  # single trailing newline (clip)
    "plain\nmultiline",
    "  leading space\nb",  # leading-space first line — corrupted before the fix
    "a\n  indented\nc",  # interior leading space
    "trailing space  \nb",  # trailing whitespace on a content line
    "tab\there\nx",
    "carriage\r\nreturn",  # CRLF
    "a\n\nb",  # interior blank line
    "unicode éñ\nsecond",
    "code:\n    def f():\n        return 1\n",
]


@pytest.mark.parametrize("force_stdlib", [True, False])
@pytest.mark.parametrize("value", _TRICKY_STRINGS)
def test_tricky_string_roundtrip(
    monkeypatch: pytest.MonkeyPatch, force_stdlib: bool, value: str
) -> None:
    """Multiline strings (trailing newlines, leading spaces, CRLF) round-trip exactly.

    Both the stdlib emitter/parser and the PyYAML reader must agree byte-for-byte —
    AgentTape's core promise (invariant #3) is deterministic, lossless cassettes.
    """

    y = _reload_yaml(monkeypatch, force_stdlib)
    assert y.load(y.dump({"k": value}))["k"] == value


def test_stdlib_flow_collections(monkeypatch: pytest.MonkeyPatch) -> None:
    y = _reload_yaml(monkeypatch, True)
    assert y.load("a: [1, 2, 3]") == {"a": [1, 2, 3]}
    assert y.load("m: {x: 1, y: two}") == {"m": {"x": 1, "y": "two"}}


def test_stdlib_comments_and_blanks(monkeypatch: pytest.MonkeyPatch) -> None:
    y = _reload_yaml(monkeypatch, True)
    text = "# leading comment\nkey: value  # inline\n\nother: 2\n"
    assert y.load(text) == {"key": "value", "other": 2}


def test_empty_document(monkeypatch: pytest.MonkeyPatch) -> None:
    y = _reload_yaml(monkeypatch, True)
    assert y.load("") is None
    assert y.load("\n\n") is None


def _pyyaml_installed() -> bool:
    try:
        import yaml  # noqa: F401
    except Exception:
        return False
    return True
