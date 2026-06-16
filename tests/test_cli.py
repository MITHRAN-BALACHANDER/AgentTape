"""End-to-end CLI tests driving agenttape.cli.main()."""

from __future__ import annotations

from pathlib import Path

import pytest

import agenttape.cassette as cio
from agenttape.cli import main
from agenttape.schema import Cassette, Interaction


def _make(path: Path, content: str = "hello") -> None:
    c = Cassette(
        version="1",
        run_id="r1",
        meta={"model": "gpt-4o-mini", "freeze": {"features": ["clock"]}},
        interactions=[
            Interaction(
                index=0,
                kind="llm",
                boundary="llm",
                request={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
                response={"choices": [{"message": {"content": content}}]},
                usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                latency_ms=10.0,
            ),
            Interaction(
                index=1,
                kind="tool",
                boundary="save",
                request={"name": "save"},
                response={"ok": True},
                latency_ms=2.0,
            ),
        ],
    )
    cio.write_cassette(c, path)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "cassettes").mkdir()
    monkeypatch.chdir(tmp_path)
    _make(tmp_path / "cassettes" / "demo.yaml", "hello")
    _make(tmp_path / "cassettes" / "demo2.yaml", "goodbye")
    return tmp_path


def test_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert (tmp_path / "agenttape.toml").exists()
    assert (tmp_path / "cassettes").is_dir()
    # idempotent
    assert main(["init"]) == 0


def test_inspect(project: Path, capsys: pytest.CaptureFixture) -> None:
    assert main(["inspect", "demo"]) == 0
    out = capsys.readouterr().out
    assert "interactions" in out and "save" in out


def test_timeline(project: Path, capsys: pytest.CaptureFixture) -> None:
    assert main(["timeline", "demo"]) == 0
    assert "Timeline" in capsys.readouterr().out


def test_replay(project: Path, capsys: pytest.CaptureFixture) -> None:
    assert main(["replay", "demo"]) == 0
    assert "Reconstructed" in capsys.readouterr().out


def test_validate(project: Path, capsys: pytest.CaptureFixture) -> None:
    assert main(["validate", "demo"]) == 0
    assert "valid" in capsys.readouterr().out


def test_diff_all(project: Path, capsys: pytest.CaptureFixture) -> None:
    assert main(["diff", "demo", "demo2", "--type", "all"]) == 0
    out = capsys.readouterr().out
    assert "Run diff" in out
    assert "hello" in out and "goodbye" in out


def test_export_json(project: Path, capsys: pytest.CaptureFixture) -> None:
    assert main(["export", "demo", "--format", "json"]) == 0
    assert '"run_id"' in capsys.readouterr().out


def test_export_otel_to_file(project: Path) -> None:
    out = project / "trace.json"
    assert main(["export", "demo", "--format", "otel", "-o", str(out)]) == 0
    assert out.exists() and "resourceSpans" in out.read_text(encoding="utf-8")


def test_view(project: Path) -> None:
    assert main(["view", "demo", "-o", str(project / "v.html")]) == 0
    assert (project / "v.html").read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_view_diff(project: Path) -> None:
    assert main(["view", "demo", "demo2", "-o", str(project / "v.html")]) == 0


def test_redact(project: Path) -> None:
    path = project / "cassettes" / "secret.yaml"
    c = Cassette(
        interactions=[
            Interaction(
                index=0, kind="tool", request={}, response={"k": "sk-ABCDEFGHIJKLMNOPQRSTUVWX12"}
            )
        ]
    )
    from agenttape import yaml_io

    path.write_text(yaml_io.dump(c.to_dict()), encoding="utf-8")
    assert main(["redact", str(path)]) == 0
    assert "sk-ABCDEFGHIJ" not in path.read_text(encoding="utf-8")


def test_rm(project: Path) -> None:
    path = project / "cassettes" / "demo.yaml"
    assert path.exists()
    assert main(["rm", "demo", "-f"]) == 0
    assert not path.exists()


def test_record_entrypoint(project: Path, capsys: pytest.CaptureFixture) -> None:
    (project / "myagent.py").write_text(
        "import agenttape\n"
        "@agenttape.tool\n"
        "def step(x):\n"
        "    return {'v': x}\n"
        "def run():\n"
        "    return step(7)\n",
        encoding="utf-8",
    )
    assert main(["record", "myagent:run", "rec", "--mode", "record"]) == 0
    assert (project / "cassettes" / "rec.yaml").exists()


def test_missing_cassette_error(project: Path) -> None:
    assert main(["inspect", "does-not-exist"]) == 2


def test_no_command_shows_help() -> None:
    assert main([]) == 1


def test_validate_failure_exit_code(project: Path) -> None:
    path = project / "cassettes" / "bad.yaml"
    path.write_text("version: '999'\ninteractions: []\n", encoding="utf-8")
    assert main(["validate", str(path)]) == 1
