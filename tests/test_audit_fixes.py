"""Regression tests for the production-audit fixes (C1, H1-H4, M2-M7, L4/L6/L7).

Each test pins a concrete correctness bug found in the audit so a regression would
fail loudly. They are deliberately small and target one fix each.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import agenttape.cassette as cio
from agenttape import StreamingReplayError, tool, use_cassette
from agenttape.schema import SCHEMA_VERSION, Cassette, Interaction

# --------------------------------------------------------------------------- #
# C1 — date/timestamp *strings* must stay strings on round-trip (both YAML paths)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("force_stdlib", [True, False])
def test_date_like_string_stays_string(monkeypatch: pytest.MonkeyPatch, force_stdlib: bool) -> None:
    if force_stdlib:
        monkeypatch.setenv("AGENTTAPE_FORCE_STDLIB_YAML", "1")
    else:
        monkeypatch.delenv("AGENTTAPE_FORCE_STDLIB_YAML", raising=False)
    import agenttape.yaml_io as y

    y = importlib.reload(y)
    data = {
        "d": "2026-06-17",
        "dt": "2026-06-17T12:00:00",
        "sx": "12:30:00",  # YAML 1.1 sexagesimal
        "hex": "0x1F",
        "und": "1_000",
    }
    back = y.load(y.dump(data))
    assert back == data
    assert all(isinstance(v, str) for v in back.values())


def test_date_string_tool_response_roundtrip(cassette_dir: Path) -> None:
    @tool
    def get_date() -> dict:
        return {"day": "2024-01-15", "label": "release"}

    with use_cassette("dates", mode="record", cassette_dir=cassette_dir):
        get_date()
    with use_cassette("dates", mode="none", cassette_dir=cassette_dir):
        out = get_date()
    assert out == {"day": "2024-01-15", "label": "release"}
    assert isinstance(out["day"], str)  # not a datetime.date


# --------------------------------------------------------------------------- #
# H1 — duplicate form keys survive
# --------------------------------------------------------------------------- #


def test_form_duplicate_keys_preserved() -> None:
    from agenttape.adapters.http import _decode_body, _encode_body

    body = b"scope=read&scope=write&grant_type=client_credentials"
    enc = _encode_body(body, "application/x-www-form-urlencoded")
    assert enc["form"]["scope"] == ["read", "write"]
    assert _decode_body(enc) == body


# --------------------------------------------------------------------------- #
# H2 — JSON byte fidelity, and the verbatim copy never carries a redacted secret
# --------------------------------------------------------------------------- #


def test_json_body_byte_faithful_when_compact() -> None:
    from agenttape.adapters.http import _decode_body, _encode_body

    compact = b'{"a":1,"b":"x"}'  # no spaces -> differs from re-serialisation
    enc = _encode_body(compact, "application/json")
    assert "raw_b64" in enc
    assert _decode_body(enc) == compact


def test_raw_body_copy_dropped_when_secret_redacted() -> None:
    from agenttape.adapters.http import _decode_body, _encode_body
    from agenttape.redaction import Redactor

    enc = _encode_body(b'{"access_token":"tok-secret","ok":true}', "application/json")
    redacted = Redactor().redact({"response": enc})["response"]
    assert "raw_b64" not in redacted
    assert b"tok-secret" not in _decode_body(redacted)


def test_raw_b64_ignored_by_matching() -> None:
    from agenttape.canonical import compute_match_key

    assert compute_match_key({"url": "http://x", "json": {"a": 1}, "raw_b64": "ZZZ"}) == (
        compute_match_key({"url": "http://x", "json": {"a": 1}})
    )


# --------------------------------------------------------------------------- #
# H3 — multiple Set-Cookie headers survive and are reconstructed
# --------------------------------------------------------------------------- #


def test_multiple_set_cookie_roundtrip() -> None:
    httpx = pytest.importorskip("httpx")
    from agenttape.adapters.http import _clean_response_headers, _httpx_build

    headers = httpx.Headers(
        [
            (b"set-cookie", b"session=abc; Path=/"),
            (b"set-cookie", b"csrf=xyz; Path=/"),
            (b"content-type", b"application/json"),
        ]
    )
    captured = _clean_response_headers(headers)
    assert captured["set-cookie"] == ["session=abc; Path=/", "csrf=xyz; Path=/"]
    resp = _httpx_build(
        httpx,
        {"status_code": 200, "headers": captured, "text": "{}"},
        httpx.Request("GET", "http://x"),
    )
    assert dict(resp.cookies) == {"session": "abc", "csrf": "xyz"}


def test_requests_cookies_reconstructed() -> None:
    requests = pytest.importorskip("requests")
    from agenttape.adapters.http import _requests_build

    payload = {
        "status_code": 200,
        "headers": {"set-cookie": ["a=1", "b=2"], "content-type": "text/plain"},
        "text": "hi",
    }
    resp = _requests_build(requests, payload, requests.Request("GET", "http://x").prepare())
    assert dict(resp.cookies) == {"a": "1", "b": "2"}


# --------------------------------------------------------------------------- #
# H4 — volatile query params in the URL no longer break matching
# --------------------------------------------------------------------------- #


def test_volatile_query_param_still_matches(cassette_dir: Path) -> None:
    httpx = pytest.importorskip("httpx")
    calls = {"n": 0}

    def handler(request: Any) -> Any:
        calls["n"] += 1
        return httpx.Response(200, json={"ok": True})

    def agent(ts: str) -> dict:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        return client.get(f"https://api.example.com/data?q=hi&timestamp={ts}").json()

    with use_cassette("vq", mode="record", cassette_dir=cassette_dir):
        agent("1000")
    recorded = calls["n"]
    with use_cassette("vq", mode="none", cassette_dir=cassette_dir):
        assert agent("9999") == {"ok": True}  # only timestamp changed -> must match
    assert calls["n"] == recorded


# --------------------------------------------------------------------------- #
# M3 — raw httpx streaming raises in offline replay (never silently hits network)
# --------------------------------------------------------------------------- #


def test_raw_httpx_stream_raises_in_replay(cassette_dir: Path) -> None:
    httpx = pytest.importorskip("httpx")
    hits = {"n": 0}

    def handler(request: Any) -> Any:
        hits["n"] += 1
        return httpx.Response(200, text="data: x\n\n")

    with use_cassette("strm", mode="record", cassette_dir=cassette_dir):
        pass
    with use_cassette("strm", mode="none", cassette_dir=cassette_dir):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        with pytest.raises(StreamingReplayError):
            with client.stream("GET", "https://api.example.com/sse") as resp:
                resp.read()
    assert hits["n"] == 0


# --------------------------------------------------------------------------- #
# M4 — recorded SDK error keeps its .response/.body shape on replay
# --------------------------------------------------------------------------- #


class _HttpishError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.status_code = 429
        self.body = {"error": {"code": "rate_limit_exceeded"}}
        self.response = SimpleNamespace(status_code=429, headers={"retry-after": "5"})


def test_exception_response_body_preserved(cassette_dir: Path) -> None:
    @tool
    def call() -> None:
        raise _HttpishError("slow down")

    with use_cassette("rerr", mode="record", cassette_dir=cassette_dir):
        with pytest.raises(_HttpishError):
            call()
    with use_cassette("rerr", mode="none", cassette_dir=cassette_dir):
        with pytest.raises(_HttpishError) as excinfo:
            call()
    err = excinfo.value
    assert err.body["error"]["code"] == "rate_limit_exceeded"
    assert err.response.status_code == 429
    assert err.response.headers["retry-after"] == "5"


# --------------------------------------------------------------------------- #
# M5 — the callback object does not double-record what a transport adapter caught
# --------------------------------------------------------------------------- #


def test_callback_does_not_double_record_transport_call(cassette_dir: Path) -> None:
    from agenttape import AgentTape
    from agenttape.recorder import active_session

    cb = AgentTape()
    with use_cassette("cbdup", mode="record", cassette_dir=cassette_dir):
        cb.on_llm_start({}, ["hi"], run_id="r1")
        # A transport adapter captures the underlying call (executed grows).
        active_session().engine.intercept(
            "llm", {"m": 1}, boundary="llm", executor=lambda: {"x": 1}
        )
        cb.on_llm_end({"x": 1}, run_id="r1")
    c = cio.read_cassette(cassette_dir / "cbdup.yaml")
    assert [i.kind for i in c.interactions] == ["llm"]  # not two


def test_callback_records_when_no_transport(cassette_dir: Path) -> None:
    from agenttape import AgentTape

    cb = AgentTape()
    with use_cassette("cbsolo", mode="record", cassette_dir=cassette_dir):
        cb.on_tool_start({"name": "t"}, "input", run_id="r2")
        cb.on_tool_end("output", run_id="r2", name="t")
    c = cio.read_cassette(cassette_dir / "cbsolo.yaml")
    assert [i.kind for i in c.interactions] == ["tool"]


# --------------------------------------------------------------------------- #
# M6 — frozen now() is the recorder's *local* wall clock and reproduces on replay
# --------------------------------------------------------------------------- #


def test_frozen_now_is_local_and_reproducible(cassette_dir: Path) -> None:
    @tool
    def noop() -> int:
        return 1

    def agent() -> tuple[str, str]:
        return datetime.now().isoformat(), datetime.now(timezone.utc).isoformat()

    with use_cassette("loc", mode="record", cassette_dir=cassette_dir):
        rec_local, rec_utc = agent()
    with use_cassette("loc", mode="none", cassette_dir=cassette_dir):
        rep_local, rep_utc = agent()
    assert rec_local == rep_local  # reproduced across the offset stored in meta
    assert rec_utc == rep_utc


# --------------------------------------------------------------------------- #
# L4 — final_output prefers the agent response over a raw HTTP envelope
# --------------------------------------------------------------------------- #


def test_final_output_skips_http_envelope() -> None:
    from agenttape.metrics import final_output

    c = Cassette(
        version=SCHEMA_VERSION,
        interactions=[
            Interaction(index=0, kind="llm", request={}, response={"answer": "42"}, boundary="llm"),
            Interaction(
                index=1,
                kind="http",
                request={"url": "http://x"},
                response={"status_code": 200, "headers": {}, "json": {"raw": True}},
                boundary="http",
            ),
        ],
    )
    assert final_output(c) == {"answer": "42"}


# --------------------------------------------------------------------------- #
# L6 — a missing asset raises on the replay read path (no silent truncation)
# --------------------------------------------------------------------------- #


def test_missing_asset_raises_on_read(tmp_path: Path) -> None:
    from agenttape.errors import CassetteCorruptError

    c = Cassette(
        version=SCHEMA_VERSION,
        interactions=[
            Interaction(index=0, kind="tool", request={"a": 1}, response={"big": "Z" * 6000})
        ],
    )
    path = tmp_path / "withasset.yaml"
    cio.write_cassette(c, path, redactor=None, assets_threshold=4096)
    # Wipe the sidecar so the reference dangles.
    from agenttape.assets import assets_dir_for

    for f in assets_dir_for(path).iterdir():
        f.unlink()
    with pytest.raises(CassetteCorruptError):
        cio.read_cassette(path)


# --------------------------------------------------------------------------- #
# L7 — an interaction with neither response nor error is rejected as corrupt
# --------------------------------------------------------------------------- #


def test_interaction_without_response_or_error_rejected() -> None:
    from agenttape.errors import CassetteCorruptError

    with pytest.raises(CassetteCorruptError):
        Interaction.from_dict({"index": 0, "kind": "tool", "request": {"a": 1}})
