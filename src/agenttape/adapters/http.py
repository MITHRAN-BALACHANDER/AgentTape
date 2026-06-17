"""Raw HTTP fallback adapters for ``httpx`` and ``requests``.

These patch the transport layer so that *any* SDK built on httpx/requests — even
ones AgentTape has no dedicated adapter for — is captured and replayed. Matching is
based on method + URL + body plus non-volatile headers; secret and volatile headers
(``Authorization``, ``Cookie``, ``User-Agent`` …) are dropped from the recorded
request so they neither leak to disk nor destabilise matching.

Two correctness rules drive the body/header handling:

* The recorded body is the **decoded** payload (httpx/requests transparently
  decompress on read), so the transport headers that describe the *wire* encoding
  (``Content-Encoding``, ``Content-Length``, ``Transfer-Encoding``) are dropped from
  the recorded response — keeping them would make the framework try to gunzip an
  already-decompressed body on replay and raise ``DecodingError``.
* JSON and form bodies are captured **structurally** (not as one opaque string) so
  record-time redaction can see nested secret keys (``password`` in a login POST,
  ``access_token`` in a token response) and so matching is stable across key
  reordering / whitespace. Multipart bodies have their random boundary normalised so
  repeated uploads match on replay.
"""

from __future__ import annotations

import base64
import functools
import json
import re
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode

from ..recorder import active_session
from .base import Adapter, RefCountedPatch

# Headers dropped from the *recorded request* (secret or volatile).
_DROP_REQUEST_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "x-api-key",
        "openai-api-key",
        "api-key",
        "user-agent",
        "date",
        "content-length",
        "host",
        "connection",
        "accept-encoding",
        "x-request-id",
        "x-stainless-arch",
        "x-stainless-os",
        "x-stainless-runtime",
        "x-stainless-runtime-version",
        "x-stainless-package-version",
        "x-stainless-lang",
        "x-stainless-retry-count",
        "idempotency-key",
        "traceparent",
    }
)

# Transport headers describing the *wire* form of the body. The recorded body is the
# decoded payload, so these must not survive into the reconstructed response.
_DROP_RESPONSE_HEADERS = frozenset({"content-encoding", "content-length", "transfer-encoding"})

# A multipart boundary is random per request; normalise it so repeated uploads match.
_BOUNDARY_RE = re.compile(r'boundary=("?)([^";,]+)\1', re.IGNORECASE)
_FIXED_BOUNDARY = "AGENTTAPE_BOUNDARY"


def _content_type(headers: Any) -> str:
    try:
        items = headers.items()
    except AttributeError:
        items = dict(headers).items()
    for key, value in items:
        if str(key).lower() == "content-type":
            return str(value)
    return ""


def _normalize_boundary_in_header(value: str) -> str:
    return _BOUNDARY_RE.sub(f"boundary={_FIXED_BOUNDARY}", value)


def _clean_headers(headers: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        items = headers.items()
    except AttributeError:
        items = dict(headers).items()
    for key, value in items:
        if str(key).lower() in _DROP_REQUEST_HEADERS:
            continue
        out[str(key)] = _normalize_boundary_in_header(str(value))
    return out


def _clean_response_headers(headers: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in dict(headers).items():
        if str(key).lower() in _DROP_RESPONSE_HEADERS:
            continue
        out[str(key)] = str(value)
    return out


def _encode_body(content: bytes | None, content_type: str = "") -> dict[str, Any]:
    """Capture a request/response body, structured where possible.

    JSON / form bodies become nested data (so redaction and matching see their
    fields); multipart bodies have their boundary normalised; everything else is
    UTF-8 text or, failing that, base64.
    """

    if not content:
        return {}
    ctype = content_type.lower()
    if "multipart/form-data" in ctype:
        boundary = _extract_boundary(content_type)
        if boundary:
            content = content.replace(boundary.encode("utf-8", "ignore"), _FIXED_BOUNDARY.encode())
    elif "application/json" in ctype or ctype.endswith("+json"):
        try:
            return {"json": json.loads(content.decode("utf-8"))}
        except (ValueError, UnicodeDecodeError):
            pass
    elif "application/x-www-form-urlencoded" in ctype:
        try:
            return {"form": dict(parse_qsl(content.decode("utf-8"), keep_blank_values=True))}
        except UnicodeDecodeError:
            pass
    try:
        return {"text": content.decode("utf-8")}
    except UnicodeDecodeError:
        return {"body_b64": base64.b64encode(content).decode("ascii")}


def _decode_body(payload: dict[str, Any]) -> bytes:
    if "json" in payload:
        return json.dumps(payload["json"], ensure_ascii=False).encode("utf-8")
    if "form" in payload and isinstance(payload["form"], dict):
        return urlencode(payload["form"]).encode("utf-8")
    if "text" in payload:
        return str(payload["text"]).encode("utf-8")
    if "content" in payload:  # legacy cassettes
        return str(payload["content"]).encode("utf-8")
    if "body_b64" in payload:
        return base64.b64decode(payload["body_b64"])
    return b""


def _extract_boundary(content_type: str) -> str | None:
    match = _BOUNDARY_RE.search(content_type or "")
    return match.group(2) if match else None


# --------------------------------------------------------------------------- #
# httpx
# --------------------------------------------------------------------------- #


class HttpxAdapter(Adapter):
    name = "httpx"

    def __init__(self) -> None:
        self._patch = RefCountedPatch()

    def available(self) -> bool:
        try:
            import httpx  # noqa: F401
        except Exception:
            return False
        return True

    def install(self, session: Any) -> None:
        self._patch.acquire(self._do_install)

    def uninstall(self) -> None:
        self._patch.release()

    def _do_install(self) -> list[Callable[[], None]]:
        import httpx

        restores: list[Callable[[], None]] = []
        orig_sync = httpx.Client.send
        orig_async = httpx.AsyncClient.send

        @functools.wraps(orig_sync)
        def sync_send(client: Any, request: Any, **kwargs: Any) -> Any:
            session = active_session()
            if session is None:
                return orig_sync(client, request, **kwargs)
            req = _httpx_request(request)
            boundary = request.url.host or "http"

            def executor() -> Any:
                resp = orig_sync(client, request, **kwargs)
                resp.read()
                return _httpx_dump(resp)

            recorded = session.engine.intercept("http", req, boundary=boundary, executor=executor)
            return _httpx_build(httpx, recorded, request)

        @functools.wraps(orig_async)
        async def async_send(client: Any, request: Any, **kwargs: Any) -> Any:
            session = active_session()
            if session is None:
                return await orig_async(client, request, **kwargs)
            req = _httpx_request(request)
            boundary = request.url.host or "http"

            async def executor() -> Any:
                resp = await orig_async(client, request, **kwargs)
                await resp.aread()
                return _httpx_dump(resp)

            recorded = await session.engine.aintercept(
                "http", req, boundary=boundary, executor=executor
            )
            return _httpx_build(httpx, recorded, request)

        httpx.Client.send = sync_send  # type: ignore[method-assign]
        httpx.AsyncClient.send = async_send  # type: ignore[method-assign]
        restores.append(lambda: setattr(httpx.Client, "send", orig_sync))
        restores.append(lambda: setattr(httpx.AsyncClient, "send", orig_async))
        return restores


def _httpx_request_body(request: Any) -> bytes:
    # ``request.content`` raises ``RequestNotRead`` for streaming bodies (e.g. the
    # multipart upload httpx builds lazily), so materialise it first when needed.
    try:
        content = request.content
    except Exception:
        try:
            request.read()
            content = request.content
        except Exception:  # pragma: no cover - genuinely async-only streams
            content = b""
    return bytes(content) if content else b""


def _httpx_request(request: Any) -> dict[str, Any]:
    body = _httpx_request_body(request)
    return {
        "method": request.method,
        "url": str(request.url),
        "headers": _clean_headers(request.headers),
        **_encode_body(body, _content_type(request.headers)),
    }


def _httpx_dump(resp: Any) -> dict[str, Any]:
    extensions = getattr(resp, "extensions", {}) or {}
    http_version = extensions.get("http_version")
    if isinstance(http_version, bytes):
        http_version = http_version.decode("ascii", "replace")
    return {
        "status_code": resp.status_code,
        "headers": _clean_response_headers(resp.headers),
        "reason_phrase": getattr(resp, "reason_phrase", ""),
        "http_version": http_version or "HTTP/1.1",
        **_encode_body(resp.content, _content_type(resp.headers)),
    }


def _httpx_build(httpx_mod: Any, payload: dict[str, Any], request: Any) -> Any:
    headers = {
        k: v
        for k, v in payload.get("headers", {}).items()
        if k.lower() not in _DROP_RESPONSE_HEADERS
    }
    extensions: dict[str, Any] = {}
    reason = payload.get("reason_phrase")
    if reason:
        extensions["reason_phrase"] = str(reason).encode("ascii", "replace")
    http_version = payload.get("http_version")
    if http_version:
        extensions["http_version"] = str(http_version).encode("ascii", "replace")
    resp = httpx_mod.Response(
        status_code=int(payload.get("status_code", 200)),
        headers=headers,
        content=_decode_body(payload),
        request=request,
        extensions=extensions or None,
    )
    # ``.elapsed`` raises if never set by a real transport; latency lives on the
    # interaction, so a zero delta is enough to keep callers from crashing on replay.
    resp.elapsed = timedelta(0)
    return resp


# --------------------------------------------------------------------------- #
# requests
# --------------------------------------------------------------------------- #


class RequestsAdapter(Adapter):
    name = "requests"

    def __init__(self) -> None:
        self._patch = RefCountedPatch()

    def available(self) -> bool:
        try:
            import requests  # noqa: F401
        except Exception:
            return False
        return True

    def install(self, session: Any) -> None:
        self._patch.acquire(self._do_install)

    def uninstall(self) -> None:
        self._patch.release()

    def _do_install(self) -> list[Callable[[], None]]:
        import requests
        from requests.adapters import HTTPAdapter

        orig_send = HTTPAdapter.send

        @functools.wraps(orig_send)
        def send(adapter: Any, request: Any, **kwargs: Any) -> Any:
            session = active_session()
            if session is None:
                return orig_send(adapter, request, **kwargs)
            req = _requests_request(request)
            boundary = _host_of(request.url)

            def executor() -> Any:
                resp = orig_send(adapter, request, **kwargs)
                return _requests_dump(resp)

            recorded = session.engine.intercept("http", req, boundary=boundary, executor=executor)
            return _requests_build(requests, recorded, request)

        HTTPAdapter.send = send  # type: ignore[method-assign]
        return [lambda: setattr(HTTPAdapter, "send", orig_send)]


def _requests_request(request: Any) -> dict[str, Any]:
    body = request.body
    if isinstance(body, str):
        body_bytes = body.encode("utf-8")
    elif isinstance(body, bytes):
        body_bytes = body
    else:
        body_bytes = b""
    return {
        "method": request.method,
        "url": request.url,
        "headers": _clean_headers(request.headers),
        **_encode_body(body_bytes, _content_type(request.headers)),
    }


def _requests_dump(resp: Any) -> dict[str, Any]:
    return {
        "status_code": resp.status_code,
        "headers": _clean_response_headers(resp.headers),
        "reason": getattr(resp, "reason", ""),
        **_encode_body(resp.content, _content_type(resp.headers)),
    }


def _requests_build(requests_mod: Any, payload: dict[str, Any], request: Any) -> Any:
    import io

    from requests.utils import get_encoding_from_headers

    resp = requests_mod.models.Response()
    resp.status_code = int(payload.get("status_code", 200))
    content = _decode_body(payload)
    resp._content = content
    resp.headers = requests_mod.structures.CaseInsensitiveDict(payload.get("headers", {}))
    resp.url = request.url
    resp.reason = payload.get("reason", "")
    resp.request = request
    # Reconstruct the fields ``HTTPAdapter.build_response`` would normally set, so
    # ``.text`` decodes correctly, ``.raw`` is iterable and ``.elapsed`` is present.
    resp.encoding = get_encoding_from_headers(resp.headers)
    resp.raw = io.BytesIO(content)
    resp.elapsed = timedelta(0)
    resp.history = []
    return resp


def _host_of(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return urlparse(url).hostname or "http"
    except Exception:  # pragma: no cover
        return "http"
