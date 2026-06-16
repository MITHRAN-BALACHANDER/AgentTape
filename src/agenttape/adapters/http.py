"""Raw HTTP fallback adapters for ``httpx`` and ``requests``.

These patch the transport layer so that *any* SDK built on httpx/requests — even
ones AgentTape has no dedicated adapter for — is captured and replayed. Matching is
based on method + URL + body plus non-volatile headers; secret and volatile headers
(``Authorization``, ``Cookie``, ``User-Agent`` …) are dropped from the recorded
request so they neither leak to disk nor destabilise matching.
"""

from __future__ import annotations

import base64
import functools
from collections.abc import Callable
from typing import Any

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
        "traceparent",
    }
)


def _clean_headers(headers: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        items = headers.items()
    except AttributeError:
        items = dict(headers).items()
    for key, value in items:
        if str(key).lower() in _DROP_REQUEST_HEADERS:
            continue
        out[str(key)] = str(value)
    return out


def _encode_body(content: bytes | None) -> dict[str, Any]:
    if not content:
        return {}
    try:
        return {"text": content.decode("utf-8")}
    except UnicodeDecodeError:
        return {"body_b64": base64.b64encode(content).decode("ascii")}


def _decode_body(payload: dict[str, Any]) -> bytes:
    if "text" in payload:
        return str(payload["text"]).encode("utf-8")
    if "content" in payload:
        return str(payload["content"]).encode("utf-8")
    if "body_b64" in payload:
        return base64.b64decode(payload["body_b64"])
    return b""


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


def _httpx_request(request: Any) -> dict[str, Any]:
    body = bytes(request.content) if request.content else b""
    return {
        "method": request.method,
        "url": str(request.url),
        "headers": _clean_headers(request.headers),
        **_encode_body(body),
    }


def _httpx_dump(resp: Any) -> dict[str, Any]:
    return {
        "status_code": resp.status_code,
        "headers": dict(resp.headers),
        **_encode_body(resp.content),
    }


def _httpx_build(httpx_mod: Any, payload: dict[str, Any], request: Any) -> Any:
    return httpx_mod.Response(
        status_code=int(payload.get("status_code", 200)),
        headers=payload.get("headers", {}),
        content=_decode_body(payload),
        request=request,
    )


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
        **_encode_body(body_bytes),
    }


def _requests_dump(resp: Any) -> dict[str, Any]:
    return {
        "status_code": resp.status_code,
        "headers": dict(resp.headers),
        "reason": getattr(resp, "reason", ""),
        **_encode_body(resp.content),
    }


def _requests_build(requests_mod: Any, payload: dict[str, Any], request: Any) -> Any:
    resp = requests_mod.models.Response()
    resp.status_code = int(payload.get("status_code", 200))
    resp._content = _decode_body(payload)
    resp.headers = requests_mod.structures.CaseInsensitiveDict(payload.get("headers", {}))
    resp.url = request.url
    resp.reason = payload.get("reason", "")
    resp.request = request
    return resp


def _host_of(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return urlparse(url).hostname or "http"
    except Exception:  # pragma: no cover
        return "http"
