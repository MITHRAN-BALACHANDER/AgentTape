"""Unit tests for redaction, canonicalization, matchers, schema, assets, config."""

from __future__ import annotations

from pathlib import Path

import pytest

from agenttape.assets import assets_dir_for, externalize, inline
from agenttape.canonical import canonicalize, compute_match_key
from agenttape.config import Config, _MiniToml
from agenttape.matchers import (
    ExactMatcher,
    OrderedMatcher,
    resolve_matcher,
    resolve_matchers,
)
from agenttape.redaction import RedactionConfig, Redactor
from agenttape.schema import Cassette, Interaction

# -- redaction ------------------------------------------------------------- #


def test_redaction_denylist_and_regex() -> None:
    r = Redactor()
    data = {
        "Authorization": "Bearer abc.def.ghi",
        "nested": {"api_key": "sk-1234567890abcdefghij", "ok": "value"},
        "text": "contact me at user@example.com please",
        "openai": "sk-proj-ABCDEFGHIJKLMNOPQRSTUV",
    }
    out = r.redact(data)
    assert out["Authorization"] == "***REDACTED***"
    assert out["nested"]["api_key"] == "***REDACTED***"
    assert out["nested"]["ok"] == "value"
    assert "user@example.com" not in out["text"]
    assert "***REDACTED***" in out["text"]
    assert "sk-proj" not in out["openai"]


def test_redaction_can_be_disabled() -> None:
    r = Redactor(RedactionConfig(enabled=False))
    assert r.redact({"password": "hunter2"}) == {"password": "hunter2"}


def test_redaction_email_toggle() -> None:
    r = Redactor(RedactionConfig(redact_emails=False))
    assert r.redact("a@b.com") == "a@b.com"


def test_redaction_extra_rules() -> None:
    cfg = RedactionConfig.from_mapping(
        {"denylist": ["x-custom"], "regexes": [r"ID-\d+"]}
    )
    r = Redactor(cfg)
    out = r.redact({"x-custom": "secret", "note": "see ID-42 today"})
    assert out["x-custom"] == "***REDACTED***"
    assert "ID-42" not in out["note"]


# -- canonical / matchers -------------------------------------------------- #


def test_canonicalize_drops_volatile() -> None:
    req = {"model": "x", "timestamp": 123, "nested": {"request_id": "abc", "keep": 1}}
    canon = canonicalize(req, ["timestamp", "request_id"])
    assert "timestamp" not in canon
    assert "request_id" not in canon["nested"]
    assert canon["nested"]["keep"] == 1


def test_match_key_stable_and_order_independent() -> None:
    a = compute_match_key({"b": 2, "a": 1})
    b = compute_match_key({"a": 1, "b": 2})
    assert a == b
    assert a.startswith("sha256:")


def test_match_key_changes_with_content() -> None:
    assert compute_match_key({"a": 1}) != compute_match_key({"a": 2})


def test_resolve_matchers() -> None:
    assert isinstance(resolve_matcher("exact"), ExactMatcher)
    assert isinstance(resolve_matcher("ordered"), OrderedMatcher)
    custom = resolve_matcher(lambda req: "k")
    assert custom.key({"x": 1}, ()) == "k"
    with pytest.raises(ValueError):
        resolve_matcher("nope")
    assert len(resolve_matchers(["exact", "ignore_volatile"])) == 2


def test_exact_vs_ignore_volatile() -> None:
    req = {"model": "x", "timestamp": 1}
    exact = resolve_matcher("exact")
    vol = resolve_matcher("ignore_volatile")
    assert exact.key(req, ["timestamp"]) != vol.key(req, ["timestamp"])


# -- schema ---------------------------------------------------------------- #


def test_interaction_roundtrip() -> None:
    i = Interaction(index=0, kind="tool", request={"a": 1}, response={"b": 2}, boundary="t")
    assert Interaction.from_dict(i.to_dict()) == i


def test_interaction_rejects_bad_kind() -> None:
    with pytest.raises(Exception):
        Interaction(index=0, kind="bogus", request={})


def test_cassette_roundtrip_and_add() -> None:
    c = Cassette(run_id="r1")
    c.add(Interaction(index=99, kind="llm", request={"m": 1}, response="ok"))
    c.add(Interaction(index=99, kind="tool", request={"n": 1}, response="ok"))
    assert [i.index for i in c.interactions] == [0, 1]
    back = Cassette.from_dict(c.to_dict())
    assert back == c


def test_cassette_version_error() -> None:
    from agenttape.errors import SchemaVersionError

    with pytest.raises(SchemaVersionError):
        Cassette.from_dict({"version": "999", "interactions": []})


def test_error_interaction_roundtrip() -> None:
    i = Interaction(index=0, kind="tool", request={}, error={"type": "ValueError", "message": "x"})
    back = Interaction.from_dict(i.to_dict())
    assert back.error == {"type": "ValueError", "message": "x"}
    assert back.response is None


# -- assets ---------------------------------------------------------------- #


def test_assets_externalize_inline(tmp_path: Path) -> None:
    big = "x" * 5000
    data = {"small": "tiny", "big": big, "list": [big]}
    adir = tmp_path / "c.assets"
    out = externalize(data, adir, threshold=4096)
    assert out["small"] == "tiny"
    assert out["big"]["__agenttape_asset__"].startswith("sha256:")
    assert adir.exists()
    restored = inline(out, adir)
    assert restored["big"] == big
    assert restored["list"][0] == big


def test_assets_missing_falls_back_to_preview(tmp_path: Path) -> None:
    ref = {"__agenttape_asset__": "sha256:deadbeef", "encoding": "utf-8", "preview": "p"}
    assert inline({"x": ref}, tmp_path / "missing.assets") == {"x": "p"}


def test_assets_dir_for() -> None:
    assert assets_dir_for(Path("cassettes/hello.yaml")).name == "hello.assets"


# -- config ---------------------------------------------------------------- #


def test_config_defaults() -> None:
    cfg = Config()
    assert cfg.default_mode == "none"
    assert "ignore_volatile" in cfg.default_matchers


def test_config_from_mapping(tmp_path: Path) -> None:
    cfg = Config.from_mapping(
        {
            "cassette_dir": "tapes",
            "default_mode": "once",
            "freeze": ["clock"],
            "assets_threshold_bytes": 100,
            "redact": {"denylist": ["x"]},
        },
        base_dir=tmp_path,
    )
    assert cfg.cassette_dir == tmp_path / "tapes"
    assert cfg.default_mode == "once"
    assert cfg.freeze == ("clock",)
    assert cfg.assets_threshold_bytes == 100


def test_config_invalid_mode() -> None:
    from agenttape.errors import ConfigError

    with pytest.raises(ConfigError):
        Config.from_mapping({"default_mode": "bogus"})


def test_minitoml_parses_subset() -> None:
    text = """
    cassette_dir = "tapes"   # comment
    default_mode = "none"
    freeze = ["clock", "uuid"]
    assets_threshold_bytes = 2048
    flag = true

    [redact]
    denylist = ["a", "b"]
    """
    data = _MiniToml(text).parse()
    assert data["cassette_dir"] == "tapes"
    assert data["freeze"] == ["clock", "uuid"]
    assert data["assets_threshold_bytes"] == 2048
    assert data["flag"] is True
    assert data["redact"]["denylist"] == ["a", "b"]


def test_config_load_finds_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "agenttape.toml").write_text('cassette_dir = "mytapes"\n', encoding="utf-8")
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)
    cfg = Config.load()
    assert cfg.cassette_dir.name == "mytapes"
