"""User-facing boundary helpers for tools, retrieval and memory.

These decorators are the "almost-no-code" way to make an arbitrary function a
recorded boundary. Wrapping a tool with :func:`tool` means that during replay the
tool is served from the cassette and **never executes for real** — the core promise
that a replayed side effect (DB write, Slack message, charge) does nothing.

Outside an active session the wrapped function behaves exactly like the original.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from .recorder import active_session

F = TypeVar("F", bound=Callable[..., Any])


def _normalize_args(fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """Bind call arguments to parameter names for a stable, matchable request."""

    try:
        sig = inspect.signature(fn)
        bound = sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        data = dict(bound.arguments)
        data.pop("self", None)
        data.pop("cls", None)
        # Expand **kwargs captured under a VAR_KEYWORD parameter.
        for name, param in sig.parameters.items():
            if param.kind is inspect.Parameter.VAR_KEYWORD and name in data:
                extra = data.pop(name)
                if isinstance(extra, dict):
                    data.update(extra)
        return data
    except (TypeError, ValueError):
        return {"args": list(args), "kwargs": kwargs}


def _make_boundary(kind: str) -> Callable[..., Any]:
    def factory(fn: F | None = None, *, name: str | None = None) -> Any:
        def decorate(f: F) -> F:
            boundary_name = name or getattr(f, "__name__", kind)

            if inspect.iscoroutinefunction(f):

                @functools.wraps(f)
                async def awrapper(*args: Any, **kwargs: Any) -> Any:
                    session = active_session()
                    if session is None:
                        return await f(*args, **kwargs)
                    request = {
                        "name": boundary_name,
                        "args": _normalize_args(f, args, kwargs),
                    }

                    async def executor() -> Any:
                        return await f(*args, **kwargs)

                    return await session.engine.aintercept(
                        kind, request, boundary=boundary_name, executor=executor
                    )

                return awrapper  # type: ignore[return-value]

            @functools.wraps(f)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                session = active_session()
                if session is None:
                    return f(*args, **kwargs)
                request = {
                    "name": boundary_name,
                    "args": _normalize_args(f, args, kwargs),
                }
                return session.engine.intercept(
                    kind,
                    request,
                    boundary=boundary_name,
                    executor=lambda: f(*args, **kwargs),
                )

            return wrapper  # type: ignore[return-value]

        if fn is not None:
            return decorate(fn)
        return decorate

    return factory


# Public decorators, one per boundary kind.
tool = _make_boundary("tool")
retrieval = _make_boundary("retrieval")
memory_read = _make_boundary("memory_read")
memory_write = _make_boundary("memory_write")


def record_call(
    kind: str,
    request: dict[str, Any],
    executor: Callable[[], Any],
    *,
    boundary: str | None = None,
    usage: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> Any:
    """Low-level manual hook: route one boundary crossing through the active session.

    Frameworks and the callback object use this to record an interaction with an
    explicit request payload. Outside a session it just calls ``executor()``.
    """

    session = active_session()
    if session is None:
        return executor()
    return session.engine.intercept(
        kind, request, boundary=boundary or kind, executor=executor, usage=usage, tags=tags
    )


__all__ = [
    "memory_read",
    "memory_write",
    "record_call",
    "retrieval",
    "tool",
]
