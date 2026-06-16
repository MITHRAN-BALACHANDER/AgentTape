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
