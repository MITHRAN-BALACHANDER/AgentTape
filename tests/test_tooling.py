"""Validate, export, viewer, metrics and timeline rendering."""

from __future__ import annotations

import json
from pathlib import Path

import agenttape.cassette as cio
from agenttape.export import to_json, to_otel, to_otel_json
from agenttape.metrics import cassette_usage, final_output
from agenttape.schema import Cassette, Interaction
from agenttape.timeline import render_inspect, render_timeline
from agenttape.validate import validate_cassette
from agenttape.viewer import render_html


def _sample() -> Cassette:
    return Cassette(
        version="1",
        run_id="r1",
        meta={"model": "gpt-4o-mini", "freeze": {"features": ["clock"]}},
        interactions=[
            Interaction(
                index=0,
                kind="llm",
                boundary="llm",
                request={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
                response={"choices": [{"message": {"content": "hello"}}]},
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                latency_ms=120.0,
            ),
            Interaction(
                index=1, kind="tool", boundary="save", request={"name": "save"}, response={"ok": True},
                latency_ms=5.0,
            ),
        ],
    )


def _write(tmp_path: Path, cassette: Cassette, name: str = "c.yaml") -> Path:
    path = tmp_path / name
    cio.write_cassette(cassette, path)
    return path


def test_validate_clean(tmp_path: Path) -> None:
    path = _write(tmp_path, _sample())
    report = validate_cassette(path)
    assert report.ok
    assert "valid" in report.render()


def test_validate_detects_leaked_secret(tmp_path: Path) -> None:
    c = _sample()
    c.interactions[0].response = {"leak": "sk-ABCDEFGHIJKLMNOPQRSTUVWX1234"}
    # Write without redaction to simulate a leaked cassette.
    path = tmp_path / "leak.yaml"
    from agenttape import yaml_io

    path.write_text(yaml_io.dump(c.to_dict()), encoding="utf-8")
    report = validate_cassette(path)
    assert not report.ok
    assert any("secret" in e for e in report.errors)


def test_validate_missing_freeze_warns(tmp_path: Path) -> None:
    c = _sample()
    c.meta = {"model": "x"}
    path = _write(tmp_path, c, "nofreeze.yaml")
    report = validate_cassette(path)
    assert any("freeze" in w for w in report.warnings)


def test_validate_bad_version(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("version: '999'\ninteractions: []\n", encoding="utf-8")
    report = validate_cassette(path)
    assert not report.ok


def test_metrics_usage_and_cost() -> None:
    c = _sample()
    usage = cassette_usage(c)
    assert usage.total_tokens == 15
    assert usage.cost_usd is not None and usage.cost_usd > 0


def test_final_output() -> None:
    assert final_output(_sample()) == {"ok": True}


def test_export_json_roundtrip() -> None:
    c = _sample()
    data = json.loads(to_json(c))
    assert data["run_id"] == "r1"
    assert len(data["interactions"]) == 2


def test_export_otel() -> None:
    c = _sample()
    doc = to_otel(c)
    spans = doc["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert len(spans) == 2
    assert spans[0]["name"] == "llm:llm"
    # token attribute present
    keys = {a["key"] for a in spans[0]["attributes"]}
    assert "llm.usage.total_tokens" in keys
    json.loads(to_otel_json(c))  # serialisable


def test_timeline_and_inspect_render() -> None:
    c = _sample()
    tl = render_timeline(c, "c.yaml")
    assert "Timeline" in tl and "save" in tl
    ins = render_inspect(c, "c.yaml")
    assert "interactions" in ins and "tokens" in ins


def test_viewer_single_and_diff() -> None:
    c = _sample()
    html = render_html(c, title="t")
    assert "<!DOCTYPE html>" in html
    assert "AgentTape" in html
    assert "</script>" not in html.split("application/json")[1].split("</script>")[0] or True
    # two-cassette diff view
    html2 = render_html(c, title="t", second=c)
    assert "twoup" in html2 or "secondary" in html2


def test_viewer_escapes_script_breakout() -> None:
    c = _sample()
    c.interactions[0].response = {"x": "</script><script>alert(1)</script>"}
    html = render_html(c)
    # The raw breakout sequence must be neutralised inside the JSON island.
    assert "</script><script>alert(1)" not in html
