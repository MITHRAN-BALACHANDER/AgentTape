"""Regression tests for the correctness fixes.

Each test pins a bug that was provable against the engine before the fix:

* concurrent async recording dropping interactions,
* concurrent async replay executing a frozen side effect (the headline guardrail),
* streaming silently hitting the network during offline replay,
* recorded exceptions losing their type on replay,
* small ``bytes`` being corrupted to a base64 string on round-trip,
* the matcher list being silently truncated to its first element.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agenttape import (
    StreamingReplayError,
    UnmatchedInteractionError,
    tool,
    use_cassette,
)
from agenttape.engine import Engine
from agenttape.schema import SCHEMA_VERSION, Cassette, Interaction

# -- concurrency: re-entrancy guard is per-context, not a shared counter ---- #


def test_concurrent_async_recording_captures_every_call() -> None:
    eng = Engine(recorded=Cassette(version=SCHEMA_VERSION), mode="record", cassette_existed=False)

    async def slow(tag: int) -> dict[str, int]:
        await asyncio.sleep(0.01)
        return {"tag": tag}

    async def boundary(i: int) -> object:
        return await eng.aintercept("tool", {"i": i}, boundary="t", executor=lambda: slow(i))

    async def run() -> list[object]:
        return await asyncio.gather(*[boundary(i) for i in range(5)])

    asyncio.run(run())
    # A shared-counter guard recorded only the first; each task now has its own depth.
    assert len(eng.executed) == 5
    assert sorted(i.request["i"] for i in eng.executed) == [0, 1, 2, 3, 4]


def test_concurrent_replay_does_not_execute_frozen_side_effect() -> None:
    recorded = Cassette(
        version=SCHEMA_VERSION,
        interactions=[
            Interaction(
                index=0, kind="llm", request={"m": "x"}, response={"t": "hi"}, boundary="llm"
            )
        ],
    )
    eng = Engine(recorded=recorded, mode="none", cassette_existed=True, live={"llm"})
    charged: list[str] = []

    async def real_llm() -> dict[str, str]:
        await asyncio.sleep(0.01)
        return {"t": "new"}

    def dangerous_tool() -> dict[str, bool]:
        charged.append("CHARGED")  # an irreversible real side effect
        return {"charged": True}

    async def main() -> list[object]:
        async def llm() -> object:
            return await eng.aintercept("llm", {"m": "x2"}, boundary="llm", executor=real_llm)

        async def tool_call() -> object:
            await asyncio.sleep(0.005)  # lands while the live llm is mid-flight
            return eng.intercept("tool", {"a": 1}, boundary="charge", executor=dangerous_tool)

        return await asyncio.gather(llm(), tool_call(), return_exceptions=True)

    results = asyncio.run(main())
    # The frozen tool has no recording: the guardrail must fire, not the side effect.
    assert charged == []
    assert any(isinstance(r, UnmatchedInteractionError) for r in results)


# -- streaming must never silently hit the network during offline replay ---- #


def test_streaming_raises_in_offline_replay(cassette_dir: Path) -> None:
    openai = pytest.importorskip("openai")
    httpx = pytest.importorskip("httpx")

    hits = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(200, json={"id": "x"})

    def client() -> object:
        return openai.OpenAI(
            api_key="sk-test-x", http_client=httpx.Client(transport=httpx.MockTransport(handler))
        )

    # Record an (empty) cassette so mode="none" is a genuine offline-replay disposition.
    with use_cassette("stream", mode="record", cassette_dir=cassette_dir):
        pass
    with use_cassette("stream", mode="none", cassette_dir=cassette_dir):
        with pytest.raises(StreamingReplayError):
            client().chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
                stream=True,
            )
    assert hits["n"] == 0  # the real transport was never touched


# -- recorded exception type is preserved on replay ------------------------- #


class CustomToolError(Exception):
    """A user-defined, non-builtin exception used to test type-preserving replay."""


def test_custom_exception_type_preserved_on_replay(cassette_dir: Path) -> None:
    @tool
    def flaky() -> None:
        raise CustomToolError("db unavailable")

    with use_cassette("cerr", mode="record", cassette_dir=cassette_dir):
        with pytest.raises(CustomToolError):
            flaky()
    with use_cassette("cerr", mode="none", cassette_dir=cassette_dir):
        with pytest.raises(CustomToolError, match="db unavailable"):
            flaky()


# -- small bytes round-trip losslessly ------------------------------------- #


def test_small_bytes_roundtrip(tmp_path: Path) -> None:
    from agenttape.assets import externalize, inline

    adir = tmp_path / "c.assets"
    obj = {"blob": b"\x00\x01\x02hello", "big": b"Z" * 5000}
    restored = inline(externalize(obj, adir, threshold=4096), adir)
    assert restored["blob"] == b"\x00\x01\x02hello"
    assert isinstance(restored["blob"], bytes)
    assert restored["big"] == b"Z" * 5000  # large bytes still round-trip via the sidecar


# -- matcher fallback chain actually consults every matcher ----------------- #


def test_matcher_fallback_chain_uses_second_matcher(cassette_dir: Path) -> None:
    # Record with the default matcher.
    @tool
    def echo(payload: dict) -> dict:
        return {"echo": payload}

    with use_cassette("fb", mode="record", cassette_dir=cassette_dir):
        echo({"a": 1})

    # Replay with ("exact", "ordered"): "exact" won't match a changed payload, so the
    # engine must fall through to "ordered" and still serve the recording. Before the
    # fix only matchers[0] was ever consulted and this raised UnmatchedInteractionError.
    with use_cassette("fb", mode="none", matchers=["exact", "ordered"], cassette_dir=cassette_dir):
        assert echo({"a": 999}) == {"echo": {"a": 1}}


# -- HTTP: compressed responses round-trip without DecodingError ------------- #


def test_gzip_response_records_and_replays(cassette_dir: Path) -> None:
    """A gzip/deflate/br response must not be reconstructed with its wire headers.

    Before the fix the recorded ``Content-Encoding: gzip`` survived onto a body that
    httpx had already decompressed, so rebuilding the response raised ``DecodingError``
    on both record (nested under the SDK) and replay.
    """

    import gzip
    import json as _json

    httpx = pytest.importorskip("httpx")
    payload = {"ok": True, "n": 42, "msg": "hello"}
    raw = gzip.compress(_json.dumps(payload).encode("utf-8"))
    calls = {"n": 0}

    def handler(request: object) -> object:
        calls["n"] += 1
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "content-encoding": "gzip"},
            content=raw,
        )

    def agent() -> dict:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        return client.get("https://api.example.com/data").json()

    with use_cassette("gz", mode="record", cassette_dir=cassette_dir):
        assert agent() == payload
    recorded_calls = calls["n"]
    text = (cassette_dir / "gz.yaml").read_text(encoding="utf-8")
    assert "content-encoding" not in text.lower()

    with use_cassette("gz", mode="none", cassette_dir=cassette_dir):
        assert agent() == payload  # would raise httpx.DecodingError before the fix
    assert calls["n"] == recorded_calls  # zero network in replay


def test_httpx_build_drops_wire_headers_and_sets_elapsed() -> None:
    httpx = pytest.importorskip("httpx")
    from agenttape.adapters.http import _httpx_build

    request = httpx.Request("GET", "http://x")
    # A legacy/naive cassette payload that still carries the wire headers.
    payload = {
        "status_code": 200,
        "headers": {
            "content-type": "application/json",
            "content-encoding": "gzip",
            "content-length": "999",
        },
        "reason_phrase": "OK",
        "http_version": "HTTP/2",
        "text": '{"ok": true}',
    }
    resp = _httpx_build(httpx, payload, request)
    assert resp.json() == {"ok": True}
    assert "content-encoding" not in resp.headers  # the crash trigger is gone
    # httpx recomputes an accurate Content-Length from the body; the stale wire value
    # (which described the compressed size) must not survive.
    assert resp.headers.get("content-length") != "999"
    assert resp.http_version == "HTTP/2"
    assert resp.elapsed.total_seconds() == 0  # would RuntimeError if never set


def test_requests_build_reconstructs_fields() -> None:
    requests = pytest.importorskip("requests")
    from agenttape.adapters.http import _requests_build

    request = requests.Request("GET", "http://x/data").prepare()
    payload = {
        "status_code": 200,
        "headers": {"content-type": "text/plain; charset=latin-1"},
        "text": "hello",
    }
    resp = _requests_build(requests, payload, request)
    assert resp.encoding == "latin-1"
    assert resp.elapsed.total_seconds() == 0
    assert resp.history == []
    assert resp.raw.read() == b"hello"


# -- HTTP: body secrets are redacted (structured capture) -------------------- #


def test_http_body_secrets_are_redacted(cassette_dir: Path) -> None:
    httpx = pytest.importorskip("httpx")

    def handler(request: object) -> object:
        return httpx.Response(200, json={"access_token": "tok-super-secret", "ok": True})

    def login() -> dict:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        return client.post(
            "https://auth.example.com/token",
            json={"username": "bob", "password": "hunter2"},
        ).json()

    with use_cassette("auth", mode="record", cassette_dir=cassette_dir):
        login()
    text = (cassette_dir / "auth.yaml").read_text(encoding="utf-8")
    assert "hunter2" not in text  # request body secret
    assert "tok-super-secret" not in text  # response body secret
    assert "***REDACTED***" in text


# -- HTTP: form bodies are redacted yet still replay (via stored match_key) -- #


def test_http_form_body_secret_redacted_and_replays(cassette_dir: Path) -> None:
    httpx = pytest.importorskip("httpx")
    calls = {"n": 0}

    def handler(request: object) -> object:
        calls["n"] += 1
        return httpx.Response(200, json={"ok": True})

    def login() -> dict:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        # data=... sends application/x-www-form-urlencoded.
        return client.post(
            "https://api.example.com/login", data={"user": "bob", "password": "hunter2"}
        ).json()

    with use_cassette("form", mode="record", cassette_dir=cassette_dir):
        login()
    text = (cassette_dir / "form.yaml").read_text(encoding="utf-8")
    assert "hunter2" not in text
    assert "***REDACTED***" in text
    recorded = calls["n"]
    # Redaction rewrites the stored body, but the match_key was computed pre-redaction,
    # so the (unredacted) replay request still resolves to the recording.
    with use_cassette("form", mode="none", cassette_dir=cassette_dir):
        assert login() == {"ok": True}
    assert calls["n"] == recorded


# -- HTTP: the async httpx transport path records and replays ---------------- #


def test_async_httpx_record_replay(cassette_dir: Path) -> None:
    httpx = pytest.importorskip("httpx")
    calls = {"n": 0}

    def handler(request: object) -> object:
        calls["n"] += 1
        return httpx.Response(200, json={"ok": True, "path": "x"})

    async def agent() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            resp = await client.get("https://api.example.com/x")
            return resp.json()

    with use_cassette("ahx", mode="record", cassette_dir=cassette_dir):
        assert asyncio.run(agent()) == {"ok": True, "path": "x"}
    recorded = calls["n"]
    with use_cassette("ahx", mode="none", cassette_dir=cassette_dir):
        assert asyncio.run(agent()) == {"ok": True, "path": "x"}
    assert calls["n"] == recorded


# -- HTTP: multipart uploads match across random boundaries ------------------ #


def test_multipart_upload_matches_on_replay(cassette_dir: Path) -> None:
    httpx = pytest.importorskip("httpx")
    calls = {"n": 0}

    def handler(request: object) -> object:
        calls["n"] += 1
        return httpx.Response(200, json={"uploaded": True})

    def upload() -> dict:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        # httpx generates a fresh random multipart boundary on every call.
        return client.post(
            "https://api.example.com/files", files={"f": ("a.txt", b"hello world")}
        ).json()

    with use_cassette("mp", mode="record", cassette_dir=cassette_dir):
        upload()
    recorded_calls = calls["n"]
    with use_cassette("mp", mode="none", cassette_dir=cassette_dir):
        assert upload() == {"uploaded": True}  # different boundary; must still match
    assert calls["n"] == recorded_calls


# -- bytes survive the full record/replay round-trip ------------------------- #


def test_tool_bytes_response_roundtrip(cassette_dir: Path) -> None:
    png = b"\x89PNG\r\n\x1a\n\x00\xff\xfe"

    @tool
    def load_image() -> dict:
        return {"data": png, "name": "logo.png"}

    with use_cassette("img", mode="record", cassette_dir=cassette_dir):
        assert load_image()["data"] == png
    with use_cassette("img", mode="none", cassette_dir=cassette_dir):
        out = load_image()["data"]
    assert out == png and isinstance(out, bytes)


# -- _to_jsonable preserves rich scalar types and breaks cycles -------------- #


def test_to_jsonable_rich_types() -> None:
    import datetime
    import decimal
    import enum
    import uuid

    from agenttape.engine import _to_jsonable

    class Color(enum.Enum):
        RED = "red"

    assert _to_jsonable(Color.RED) == "red"
    assert _to_jsonable(decimal.Decimal("1.50")) == "1.50"
    u = uuid.uuid4()
    assert _to_jsonable(u) == str(u)
    assert _to_jsonable(datetime.date(2020, 1, 2)) == "2020-01-02"
    assert _to_jsonable(datetime.datetime(2020, 1, 2, 3, 4, 5)) == "2020-01-02T03:04:05"
    assert _to_jsonable({3, 1, 2}) == [1, 2, 3]

    cycle: dict = {}
    cycle["self"] = cycle
    assert _to_jsonable(cycle) == {"self": "<cycle>"}


# -- recorded exception attributes (status_code, …) survive replay ----------- #


class ApiError(Exception):
    """A non-builtin error with an attribute, like ``openai.RateLimitError``."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def test_exception_attrs_preserved_on_replay(cassette_dir: Path) -> None:
    @tool
    def call_api() -> None:
        raise ApiError("rate limited", status_code=429)

    with use_cassette("apierr", mode="record", cassette_dir=cassette_dir):
        with pytest.raises(ApiError):
            call_api()
    with use_cassette("apierr", mode="none", cassette_dir=cassette_dir):
        with pytest.raises(ApiError) as excinfo:
            call_api()
    assert excinfo.value.status_code == 429  # attribute reconstructed offline


# -- concurrent asyncio sessions do not cross-contaminate -------------------- #


def test_concurrent_sessions_do_not_cross_contaminate(cassette_dir: Path) -> None:
    import agenttape.cassette as cio
    from agenttape.recorder import active_session

    @tool
    async def work(label: str, x: int) -> dict:
        await asyncio.sleep(0.01)
        return {"label": label, "x": x}

    async def one(name: str) -> bool:
        async with use_cassette(name, mode="record", cassette_dir=cassette_dir) as sess:
            ok = active_session() is sess
            for i in range(3):
                await work(name, i)
                await asyncio.sleep(0.005)
                ok = ok and active_session() is sess
            return ok

    async def main() -> list[bool]:
        return await asyncio.gather(*[one(f"c{n}") for n in range(4)])

    results = asyncio.run(main())
    assert all(results)  # each task always saw *its own* session (was thread-local)
    for n in range(4):
        c = cio.read_cassette(cassette_dir / f"c{n}.yaml")
        labels = {i.request["args"]["label"] for i in c.interactions}
        assert labels == {f"c{n}"}  # no interaction leaked into the wrong cassette


# -- OpenAI embeddings endpoint is intercepted (record + offline replay) ----- #


def test_openai_embeddings_record_replay(cassette_dir: Path) -> None:
    pytest.importorskip("openai")
    httpx = pytest.importorskip("httpx")
    from openai import OpenAI

    calls = {"n": 0}
    body = {
        "object": "list",
        "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]}],
        "model": "text-embedding-3-small",
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }

    def handler(request: object) -> object:
        calls["n"] += 1
        return httpx.Response(200, json=body)

    def client() -> object:
        return OpenAI(
            api_key="sk-test-x",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )

    def agent() -> list[float]:
        resp = client().embeddings.create(model="text-embedding-3-small", input="hello")
        return list(resp.data[0].embedding)

    with use_cassette("emb", mode="record", cassette_dir=cassette_dir):
        assert agent() == [0.1, 0.2, 0.3]
    recorded = calls["n"]
    with use_cassette("emb", mode="none", cassette_dir=cassette_dir):
        assert agent() == [0.1, 0.2, 0.3]
    assert calls["n"] == recorded  # replayed offline, no network


# -- validate scans externalized asset files for leaked secrets -------------- #


def test_validate_scans_asset_files(tmp_path: Path) -> None:
    import agenttape.cassette as cio
    from agenttape.validate import validate_cassette

    secret = "AKIA" + "A" * 16  # AWS access-key-id shape
    # Secret sits past the 64-char preview window, so it lives only in the asset file.
    big = ("x" * 100) + " " + secret
    c = Cassette(
        version=SCHEMA_VERSION,
        interactions=[
            Interaction(
                index=0,
                kind="http",
                request={"url": "http://x"},
                response={"text": big},
                match_key="k",
            )
        ],
    )
    path = tmp_path / "leak.yaml"
    cio.write_cassette(c, path, redactor=None, assets_threshold=20)
    # The cassette body must not contain the secret (only a short preview).
    assert secret not in path.read_text(encoding="utf-8")
    report = validate_cassette(path)
    assert any("leaked secret" in e for e in report.errors)


# -- rm cleans up the derived cassette's assets sidecar ---------------------- #


def test_rm_removes_derived_assets(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from agenttape.cli import cmd_rm

    path = tmp_path / "c.yaml"
    path.write_text("version: '1'\n", encoding="utf-8")
    derived_assets = tmp_path / "c.derived.assets"
    derived_assets.mkdir()
    (derived_assets / "blob").write_bytes(b"data")

    cmd_rm(SimpleNamespace(cassette=str(path), force=True))
    assert not path.exists()
    assert not derived_assets.exists()
